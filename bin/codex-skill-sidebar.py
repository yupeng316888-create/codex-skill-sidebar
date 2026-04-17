#!/usr/bin/env python3

import argparse
import json
import os
import signal
import socket
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List

import tkinter as tk
from tkinter import ttk

try:
    import AppKit
except Exception:  # pragma: no cover - optional macOS bridge
    AppKit = None


DEFAULT_WIDTH = 240
DEFAULT_HEIGHT = 700
MIN_WIDTH = 200
MIN_HEIGHT = 240
DESC_PANEL_MIN_HEIGHT = 88
DESC_PANEL_MAX_HEIGHT = 260
DESC_PANEL_HEIGHT_RATIO = 0.24
FOLLOW_INTERVAL_MS = 200
TERMINAL_GAP = 0
WINDOW_MARGIN = 12
RECENT_LIMIT = 8
HISTORY_PATH = Path.home() / ".codex" / "skill-sidebar-history.json"
SEARCH_PLACEHOLDER = "在此搜索 skill"
SEARCH_TEXT_COLOR = "#f7fbff"
SEARCH_PLACEHOLDER_COLOR = "#6f8095"

GSTACK_GROUPS = {
    "Plan": {
        "autoplan",
        "office-hours",
        "plan-ceo-review",
        "plan-design-review",
        "plan-devex-review",
        "plan-eng-review",
    },
    "Browse": {
        "browse",
        "benchmark",
        "canary",
        "open-gstack-browser",
        "pair-agent",
        "setup-browser-cookies",
        "gstack",
    },
    "Design": {
        "design-consultation",
        "design-html",
        "design-review",
        "design-shotgun",
    },
    "QA": {
        "qa",
        "qa-only",
        "review",
        "devex-review",
        "cso",
        "health",
    },
    "Workflow": {
        "investigate",
        "checkpoint",
        "learn",
        "retro",
    },
    "Ship": {
        "ship",
        "land-and-deploy",
        "setup-deploy",
        "document-release",
    },
    "Safety": {
        "careful",
        "freeze",
        "guard",
        "gstack-upgrade",
        "unfreeze",
        "upgrade",
    },
}

SYSTEM_GROUPS = {
    "OpenAI": {"openai-docs"},
    "Media": {"imagegen"},
    "Builders": {"plugin-creator", "skill-creator", "skill-installer"},
}

TOP_ORDER = {
    "Recent": 0,
    "Gstack": 1,
    "System": 2,
    "Writing": 3,
    "Custom": 4,
}


@dataclass
class Skill:
    trigger: str
    label: str
    path: Path
    description: str
    top_group: str
    subgroup: str
    relative_key: str


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="CodeX skill sidebar")
    parser.add_argument(
        "--skills-dir",
        default=str(Path.home() / ".codex" / "skills"),
        help="The Codex skills directory",
    )
    parser.add_argument("--session-id", default="default", help="Session identifier")
    parser.add_argument(
        "--window-id",
        type=int,
        default=None,
        help="Front Terminal window id for macOS focus restoration",
    )
    parser.add_argument(
        "--parent-pid",
        type=int,
        default=None,
        help="Launcher process id; sidebar exits when the parent is gone",
    )
    parser.add_argument(
        "--socket-path",
        required=True,
        help="Unix datagram socket path for sending skill triggers",
    )
    return parser.parse_args()


def parse_frontmatter(lines: List[str]) -> Dict[str, str]:
    if not lines or lines[0].strip() != "---":
        return {}

    data: Dict[str, str] = {}
    index = 1

    while index < len(lines):
        raw_line = lines[index].rstrip()
        stripped = raw_line.strip()
        if stripped == "---":
            break
        if not stripped or ":" not in stripped:
            index += 1
            continue

        key, _, raw_value = stripped.partition(":")
        key = key.strip()
        value = raw_value.strip()
        if value == "|":
            index += 1
            multiline: List[str] = []
            while index < len(lines):
                line = lines[index]
                if line.strip() == "---":
                    break
                if line.startswith("  ") or line.startswith("\t"):
                    multiline.append(line.strip())
                    index += 1
                    continue
                break
            data[key] = " ".join(multiline).strip()
            continue

        data[key] = value.strip('"').strip("'")
        index += 1

    return data


def first_description_line(skill_md: Path) -> str:
    try:
        lines = skill_md.read_text(encoding="utf-8").splitlines()
    except OSError:
        return "No description available."

    frontmatter = parse_frontmatter(lines)
    description = frontmatter.get("description", "")
    if description:
        return description[:180].rstrip() + ("..." if len(description) > 180 else "")

    paragraph: List[str] = []
    for raw_line in lines:
        line = raw_line.strip()
        if not line:
            if paragraph:
                break
            continue
        if line.startswith("#"):
            continue
        if line.startswith("```"):
            if paragraph:
                break
            continue
        if line.startswith("<") and line.endswith(">"):
            continue
        paragraph.append(line)
        if len(" ".join(paragraph)) >= 180:
            break

    if not paragraph:
        return "No description available."

    joined = " ".join(paragraph)
    return joined[:180].rstrip() + ("..." if len(joined) > 180 else "")


def classify_skill(relative_parts: tuple[str, ...], trigger: str) -> tuple[str, str]:
    if relative_parts and relative_parts[0] == ".system":
        top_group = "System"
        for subgroup, names in SYSTEM_GROUPS.items():
            if trigger in names:
                return top_group, subgroup
        return top_group, "Other"

    if relative_parts and (
        relative_parts[0] == "gstack" or relative_parts[0].startswith("gstack-")
    ):
        top_group = "Gstack"
        for subgroup, names in GSTACK_GROUPS.items():
            if trigger in names:
                return top_group, subgroup
        return top_group, "Other"

    if "title" in trigger or "shengcai" in trigger:
        return "Writing", "Content"

    return "Custom", "Other"


def load_skills(skills_dir: Path) -> List[Skill]:
    if not skills_dir.exists():
        return []

    skills: List[Skill] = []
    seen_triggers: set[str] = set()
    skill_files: List[Path] = []
    for root, dirs, files in os.walk(skills_dir, followlinks=True):
        root_path = Path(root)
        rel_parts = root_path.relative_to(skills_dir).parts
        dirs[:] = [
            entry
            for entry in dirs
            if not entry.startswith(".") or rel_parts == () or rel_parts == (".system",)
        ]
        if "SKILL.md" in files:
            skill_files.append(root_path / "SKILL.md")

    skill_files.sort(key=lambda path: (len(path.relative_to(skills_dir).parts), str(path).lower()))

    for skill_md in skill_files:
        relative_dir = skill_md.parent.relative_to(skills_dir)
        relative_key = "/".join(relative_dir.parts)
        try:
            lines = skill_md.read_text(encoding="utf-8").splitlines()
        except OSError:
            continue
        frontmatter = parse_frontmatter(lines)
        trigger = frontmatter.get("name", skill_md.parent.name).strip()
        if not trigger or trigger in seen_triggers:
            continue
        seen_triggers.add(trigger)

        top_group, subgroup = classify_skill(relative_dir.parts, trigger)
        skills.append(
            Skill(
                trigger=trigger,
                label=trigger,
                path=skill_md.parent,
                description=first_description_line(skill_md),
                top_group=top_group,
                subgroup=subgroup,
                relative_key=relative_key,
            )
        )

    return sorted(
        skills,
        key=lambda skill: (
            TOP_ORDER.get(skill.top_group, 99),
            skill.top_group.lower(),
            skill.subgroup.lower(),
            skill.label.lower(),
        ),
    )


def terminal_bounds(window_id: int | None) -> List[int]:
    if sys.platform != "darwin":
        return []
    if window_id is None:
        script_lines = ['tell application "Terminal" to get bounds of front window']
    else:
        script_lines = [
            'tell application "Terminal"',
            "try",
            f"get bounds of (first window whose id is {window_id})",
            "on error",
            'return ""',
            "end try",
            "end tell",
        ]
    try:
        result = subprocess.run(
            ["osascript", *sum([["-e", line] for line in script_lines], [])],
            check=False,
            capture_output=True,
            text=True,
            timeout=1,
        )
    except (OSError, subprocess.SubprocessError):
        return []

    if result.returncode != 0 or not result.stdout.strip():
        return []

    try:
        return [int(part.strip()) for part in result.stdout.split(",")]
    except ValueError:
        return []


def desktop_screen_bounds() -> List[tuple[int, int]]:
    if sys.platform != "darwin" or AppKit is None:
        return []

    bounds: List[tuple[int, int]] = []
    try:
        for screen in AppKit.NSScreen.screens():
            frame = screen.frame()
            left = int(frame.origin.x)
            right = int(frame.origin.x + frame.size.width)
            bounds.append((left, right))
    except Exception:
        return []

    return sorted(bounds)


class SidebarApp:
    def __init__(
        self,
        skills_dir: Path,
        session_id: str,
        window_id: int | None,
        parent_pid: int | None,
        socket_path: str,
    ):
        self.skills_dir = skills_dir
        self.session_id = session_id
        self.window_id = window_id
        self.parent_pid = parent_pid
        self.socket_path = socket_path
        self.all_skills = load_skills(skills_dir)
        self.filtered_skills = list(self.all_skills)
        self.item_to_skill: Dict[str, Skill] = {}
        self.group_to_count: Dict[str, int] = {}
        self.last_geometry: tuple[int, int, int, int] | None = None
        self.window_chrome_top = 0
        self.screen_bounds = desktop_screen_bounds()
        if self.screen_bounds:
            self.virtual_left = min(left for left, _ in self.screen_bounds)
            self.virtual_right = max(right for _, right in self.screen_bounds)
        else:
            self.virtual_left = 0
            self.virtual_right = 0
        self.recent_triggers = self.load_recent_history()
        self.search_placeholder_active = True

        self.root = tk.Tk()
        self.root.withdraw()
        self.root.title("CodeX Skills")
        self.root.minsize(MIN_WIDTH, MIN_HEIGHT)
        self.root.resizable(False, True)
        self.root.configure(bg="#10151d")
        self.root.protocol("WM_DELETE_WINDOW", self.handle_exit)
        try:
            self.root.attributes("-topmost", True)
        except tk.TclError:
            pass
        if sys.platform == "darwin":
            try:
                self.root.tk.call(
                    "::tk::unsupported::MacWindowStyle",
                    "style",
                    self.root._w,
                    "utility",
                    "closeBox",
                )
            except tk.TclError:
                pass

        self.search_var = tk.StringVar()
        self.default_desc_text = "按分类展开 skill。双击插入，终端里回车发送。"

        self.build_ui()
        self.place_window()
        self.bind_events()
        self.refresh_tree()
        self.watch_parent()
        self.follow_terminal()
        self.root.deiconify()
        self.root.lift()
        self.root.after(150, self.restore_terminal_focus)

        signal.signal(signal.SIGTERM, self.handle_exit)
        signal.signal(signal.SIGINT, self.handle_exit)

    def load_recent_history(self) -> List[str]:
        try:
            payload = json.loads(HISTORY_PATH.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return []

        recent = payload.get("recent", [])
        if not isinstance(recent, list):
            return []

        cleaned: List[str] = []
        for entry in recent:
            if isinstance(entry, str) and entry and entry not in cleaned:
                cleaned.append(entry)
            if len(cleaned) >= RECENT_LIMIT * 2:
                break
        return cleaned

    def save_recent_history(self) -> None:
        HISTORY_PATH.parent.mkdir(parents=True, exist_ok=True)
        payload = {"recent": self.recent_triggers[: RECENT_LIMIT * 2]}
        HISTORY_PATH.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def record_recent_skill(self, skill: Skill) -> None:
        self.recent_triggers = [
            trigger for trigger in self.recent_triggers if trigger != skill.trigger
        ]
        self.recent_triggers.insert(0, skill.trigger)
        self.recent_triggers = self.recent_triggers[: RECENT_LIMIT * 2]
        try:
            self.save_recent_history()
        except OSError:
            pass

    def screen_limits_for_terminal(self, bounds: List[int]) -> tuple[int, int]:
        if not self.screen_bounds:
            return (self.virtual_left, self.virtual_right)
        if len(bounds) != 4:
            return (
                min(left for left, _ in self.screen_bounds),
                max(right for _, right in self.screen_bounds),
            )

        x1, _, x2, _ = bounds
        center = (x1 + x2) / 2
        best: tuple[int, int] | None = None
        best_overlap = -1
        best_distance = float("inf")

        for left, right in self.screen_bounds:
            overlap = max(0, min(x2, right) - max(x1, left))
            if left <= center <= right:
                distance = 0.0
            else:
                distance = min(abs(center - left), abs(center - right))
            if overlap > best_overlap or (
                overlap == best_overlap and distance < best_distance
            ):
                best = (left, right)
                best_overlap = overlap
                best_distance = distance

        if best is None:
            return (
                min(left for left, _ in self.screen_bounds),
                max(right for _, right in self.screen_bounds),
            )
        return best

    def build_ui(self) -> None:
        style = ttk.Style()
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass
        style.configure("Sidebar.TFrame", background="#10151d")
        style.configure("Sidebar.TLabel", background="#10151d", foreground="#d9e2f2")
        style.configure("SidebarDim.TLabel", background="#10151d", foreground="#8ea0b8")
        style.configure("Sidebar.TButton", padding=4)
        style.configure(
            "Sidebar.Treeview",
            background="#121a24",
            fieldbackground="#121a24",
            foreground="#f3f6fb",
            borderwidth=0,
            relief="flat",
            rowheight=16,
        )
        style.configure("Sidebar.Treeview.Heading", background="#10151d", foreground="#d9e2f2")
        style.map(
            "Sidebar.Treeview",
            background=[("selected", "#2153a6")],
            foreground=[("selected", "#ffffff")],
        )

        container = ttk.Frame(self.root, padding=10, style="Sidebar.TFrame")
        container.pack(fill=tk.BOTH, expand=True)

        search_frame = tk.Frame(
            container,
            bg="#17212d",
            highlightthickness=1,
            highlightbackground="#223043",
            highlightcolor="#4a8cff",
        )
        search_frame.pack(fill=tk.X, pady=(0, 4))

        search_icon = tk.Canvas(
            search_frame,
            width=16,
            height=16,
            bg="#17212d",
            highlightthickness=0,
            bd=0,
        )
        search_icon.create_oval(3, 3, 10, 10, outline="#6f8095", width=1)
        search_icon.create_line(9, 9, 13, 13, fill="#6f8095", width=1)
        search_icon.pack(side=tk.LEFT, padx=(6, 2), pady=3)
        self.search_icon = search_icon

        search = tk.Entry(
            search_frame,
            textvariable=self.search_var,
            relief=tk.FLAT,
            bg="#17212d",
            fg=SEARCH_PLACEHOLDER_COLOR,
            insertbackground=SEARCH_TEXT_COLOR,
            highlightthickness=0,
            font=("SF Pro Text", 10),
            insertwidth=0,
            insertontime=600,
            insertofftime=400,
        )
        search.pack(side=tk.LEFT, fill=tk.X, expand=True, ipady=2)
        self.search_entry = search
        self.search_frame = search_frame
        self.show_search_placeholder()

        list_frame = tk.Frame(container, bg="#10151d")
        list_frame.pack(fill=tk.BOTH, expand=True)

        scrollbar = tk.Scrollbar(list_frame, orient=tk.VERTICAL)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        tree = ttk.Treeview(
            list_frame,
            show="tree",
            style="Sidebar.Treeview",
            selectmode="browse",
            yscrollcommand=scrollbar.set,
        )
        tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.config(command=tree.yview)
        tree.tag_configure("top", font=("SF Pro Text", 11, "bold"), foreground="#ffffff")
        tree.tag_configure("sub", font=("SF Pro Text", 10, "bold"), foreground="#cfe0f6")
        tree.tag_configure("skill", font=("SF Mono", 10), foreground="#f3f6fb")
        self.tree = tree

        desc_frame = tk.Frame(container, bg="#10151d", height=DESC_PANEL_MIN_HEIGHT)
        desc_frame.pack(fill=tk.X, pady=(6, 4))
        desc_frame.pack_propagate(False)
        self.desc_frame = desc_frame

        desc_scrollbar = tk.Scrollbar(desc_frame, orient=tk.VERTICAL)
        desc_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        desc_text = tk.Text(
            desc_frame,
            wrap=tk.WORD,
            height=4,
            relief=tk.FLAT,
            bg="#0f1722",
            fg="#8ea0b8",
            insertbackground="#f7fbff",
            highlightthickness=1,
            highlightbackground="#223043",
            highlightcolor="#223043",
            padx=8,
            pady=6,
            font=("SF Pro Text", 10),
            yscrollcommand=desc_scrollbar.set,
            takefocus=0,
            cursor="arrow",
        )
        desc_text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        desc_scrollbar.config(command=desc_text.yview)
        self.desc_text = desc_text
        self.set_desc_text(self.default_desc_text)

        button_row = ttk.Frame(container, style="Sidebar.TFrame")
        button_row.pack(fill=tk.X, pady=(0, 0))

        insert_button = ttk.Button(
            button_row,
            text="插入 Skill",
            command=self.insert_selected,
            style="Sidebar.TButton",
        )
        insert_button.pack(side=tk.LEFT, fill=tk.X, expand=True)
        self.insert_button = insert_button

    def bind_events(self) -> None:
        self.search_var.trace_add("write", lambda *_: self.refresh_tree())
        self.search_entry.bind("<FocusIn>", self.on_search_focus_in)
        self.search_entry.bind("<FocusOut>", self.on_search_focus_out)
        self.search_frame.bind("<Button-1>", lambda _event: self.search_entry.focus_set())
        self.search_icon.bind("<Button-1>", lambda _event: self.search_entry.focus_set())
        self.search_entry.bind("<Escape>", lambda _event: self.root.destroy())
        self.search_entry.bind("<Down>", self.focus_tree)

        self.tree.bind("<<TreeviewSelect>>", self.on_select)
        self.tree.bind("<Double-Button-1>", self.on_tree_double_click)
        self.tree.bind("<Return>", self.on_tree_return)
        self.tree.bind("<Control-Return>", lambda _event: self.send_selected())
        self.tree.bind("<Escape>", lambda _event: self.root.destroy())

        self.root.bind("<Command-r>", lambda _event: self.on_refresh())
        self.root.bind("<F5>", lambda _event: self.on_refresh())

    def compute_geometry(self) -> tuple[int, int, int, int]:
        self.root.update_idletasks()
        screen_w = self.root.winfo_screenwidth()
        width = min(DEFAULT_WIDTH, max(MIN_WIDTH, screen_w // 3))
        height = DEFAULT_HEIGHT

        bounds = terminal_bounds(self.window_id)
        if len(bounds) == 4:
            x1, y1, x2, y2 = bounds
            left_limit, right_limit = self.screen_limits_for_terminal(bounds)
            if not right_limit:
                right_limit = screen_w
            available_right = right_limit - x2 - WINDOW_MARGIN
            available_left = x1 - left_limit - WINDOW_MARGIN
            desired_outer_height = max(MIN_HEIGHT, y2 - y1)
            height = max(MIN_HEIGHT, desired_outer_height - self.window_chrome_top)
            y = y1

            if available_right >= MIN_WIDTH:
                width = min(width, available_right)
                x = x2 + TERMINAL_GAP
            elif available_left >= MIN_WIDTH:
                width = min(width, available_left)
                x = x1 - width - TERMINAL_GAP
            else:
                usable_width = max(available_right, available_left, MIN_WIDTH)
                width = min(width, usable_width)
                if available_right >= available_left:
                    x = max(left_limit + WINDOW_MARGIN, right_limit - width - WINDOW_MARGIN)
                else:
                    x = max(left_limit + WINDOW_MARGIN, x1 - width - TERMINAL_GAP)
        else:
            right_limit = self.virtual_right if self.virtual_right else screen_w
            left_limit = self.virtual_left
            x = max(left_limit + WINDOW_MARGIN, right_limit - width - WINDOW_MARGIN)
            y = 40
        return width, height, x, y

    def place_window(self) -> None:
        width, height, x, y = self.compute_geometry()
        geometry = (width, height, x, y)
        if geometry == self.last_geometry:
            return
        self.last_geometry = geometry
        self.root.geometry(f"{width}x{height}+{x}+{y}")
        self.resize_detail_panel(height)
        self.root.after_idle(self.calibrate_window_chrome)

    def resize_detail_panel(self, window_height: int) -> None:
        desc_height = int(window_height * DESC_PANEL_HEIGHT_RATIO)
        desc_height = max(DESC_PANEL_MIN_HEIGHT, min(DESC_PANEL_MAX_HEIGHT, desc_height))
        try:
            self.desc_frame.configure(height=desc_height)
        except tk.TclError:
            pass

    def calibrate_window_chrome(self) -> None:
        if not self.last_geometry:
            return
        _, _, _, requested_y = self.last_geometry
        try:
            actual_root_y = self.root.winfo_rooty()
        except tk.TclError:
            return
        top_inset = max(0, actual_root_y - requested_y)
        if top_inset == self.window_chrome_top:
            return
        self.window_chrome_top = top_inset
        self.last_geometry = None
        self.place_window()

    def follow_terminal(self) -> None:
        self.place_window()
        self.root.after(FOLLOW_INTERVAL_MS, self.follow_terminal)

    def focus_tree(self, _event=None):
        top_nodes = self.tree.get_children("")
        if not top_nodes:
            return "break"
        self.tree.focus_set()
        current = self.tree.selection()
        if current:
            return "break"
        first = top_nodes[0]
        self.tree.selection_set(first)
        self.tree.focus(first)
        self.on_select()
        return "break"

    def show_search_placeholder(self) -> None:
        self.search_placeholder_active = True
        self.search_entry.configure(fg=SEARCH_PLACEHOLDER_COLOR, insertwidth=0)
        self.search_var.set(SEARCH_PLACEHOLDER)
        self.search_entry.icursor(0)

    def hide_search_placeholder(self) -> None:
        if not self.search_placeholder_active:
            self.search_entry.configure(fg=SEARCH_TEXT_COLOR, insertwidth=2)
            return
        self.search_placeholder_active = False
        self.search_entry.configure(fg=SEARCH_TEXT_COLOR, insertwidth=2)
        self.search_var.set("")

    def on_search_focus_in(self, _event=None) -> None:
        self.hide_search_placeholder()

    def on_search_focus_out(self, _event=None) -> None:
        if not self.search_var.get().strip():
            self.show_search_placeholder()

    def search_query(self) -> str:
        if self.search_placeholder_active:
            return ""
        return self.search_var.get().strip().lower()

    def restore_terminal_focus(self) -> None:
        if sys.platform != "darwin" or self.window_id is None:
            return
        script_lines = [
            'tell application "Terminal"',
            "activate",
            "try",
            f"set index of (first window whose id is {self.window_id}) to 1",
            "end try",
            "end tell",
        ]
        try:
            subprocess.run(
                ["osascript", *sum([["-e", line] for line in script_lines], [])],
                check=False,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=1,
            )
        except (OSError, subprocess.SubprocessError):
            pass

    def selected_skill(self) -> Skill | None:
        selection = self.tree.selection()
        if not selection:
            return None
        return self.item_to_skill.get(selection[0])

    def update_buttons(self) -> None:
        has_skill = self.selected_skill() is not None
        state = tk.NORMAL if has_skill else tk.DISABLED
        self.insert_button.configure(state=state)

    def set_desc_text(self, text: str) -> None:
        try:
            self.desc_text.configure(state=tk.NORMAL)
            self.desc_text.delete("1.0", tk.END)
            self.desc_text.insert("1.0", text)
            self.desc_text.yview_moveto(0)
            self.desc_text.configure(state=tk.DISABLED)
        except tk.TclError:
            pass

    def select_skill_item(self, trigger: str) -> None:
        for item_id, skill in self.item_to_skill.items():
            if skill.trigger != trigger:
                continue
            self.tree.selection_set(item_id)
            self.tree.focus(item_id)
            self.tree.see(item_id)
            self.on_select()
            return

    def refresh_tree(self, selected_trigger: str | None = None) -> None:
        query = self.search_query()
        if query:
            self.filtered_skills = [
                skill
                for skill in self.all_skills
                if query in skill.trigger.lower()
                or query in skill.label.lower()
                or query in skill.description.lower()
                or query in skill.subgroup.lower()
                or query in skill.top_group.lower()
            ]
        else:
            self.filtered_skills = list(self.all_skills)

        self.tree.delete(*self.tree.get_children())
        self.item_to_skill.clear()
        self.group_to_count = {}

        if not self.filtered_skills:
            self.set_desc_text("没有匹配到 skill。")
            self.update_buttons()
            return

        display_entries: List[tuple[str, str, Skill]] = []
        if not query and self.recent_triggers:
            skill_map = {skill.trigger: skill for skill in self.all_skills}
            for trigger in self.recent_triggers:
                skill = skill_map.get(trigger)
                if skill:
                    display_entries.append(("Recent", "Recently Used", skill))

        display_entries.extend(
            (skill.top_group, skill.subgroup, skill) for skill in self.filtered_skills
        )

        for top_key, subgroup, _skill in display_entries:
            subgroup_key = f"{top_key}/{subgroup}"
            self.group_to_count[top_key] = self.group_to_count.get(top_key, 0) + 1
            self.group_to_count[subgroup_key] = self.group_to_count.get(subgroup_key, 0) + 1

        top_nodes: Dict[str, str] = {}
        subgroup_nodes: Dict[str, str] = {}
        for top_key, subgroup, skill in display_entries:
            if top_key not in top_nodes:
                top_nodes[top_key] = self.tree.insert(
                    "",
                    tk.END,
                    text=f"{top_key} ({self.group_to_count[top_key]})",
                    open=bool(query or top_key == "Recent"),
                    tags=("top",),
                )

            subgroup_key = f"{top_key}/{subgroup}"
            if subgroup_key not in subgroup_nodes:
                subgroup_nodes[subgroup_key] = self.tree.insert(
                    top_nodes[top_key],
                    tk.END,
                    text=f"{subgroup} ({self.group_to_count[subgroup_key]})",
                    open=bool(query or top_key == "Recent"),
                    tags=("sub",),
                )

            item_id = self.tree.insert(
                subgroup_nodes[subgroup_key],
                tk.END,
                text=skill.label,
                open=False,
                tags=("skill",),
            )
            self.item_to_skill[item_id] = skill

        if selected_trigger:
            self.select_skill_item(selected_trigger)
        elif query and self.item_to_skill:
            first_skill_item = next(iter(self.item_to_skill))
            self.tree.selection_set(first_skill_item)
            self.tree.focus(first_skill_item)
            self.on_select()
        else:
            self.tree.selection_remove(self.tree.selection())
            self.set_desc_text(self.default_desc_text)
            self.update_buttons()

    def on_refresh(self) -> None:
        self.all_skills = load_skills(self.skills_dir)
        self.refresh_tree()

    def on_select(self, _event=None) -> None:
        skill = self.selected_skill()
        if not skill:
            selection = self.tree.selection()
            if selection:
                label = self.tree.item(selection[0], "text")
                self.set_desc_text(f"{label}。展开后选择具体 skill。")
            self.update_buttons()
            return
        self.set_desc_text(
            f"Trigger: ${skill.trigger}\n"
            f"分类: {skill.top_group} / {skill.subgroup}\n"
            f"{skill.description}"
        )
        self.update_buttons()

    def on_tree_double_click(self, event) -> str | None:
        item_id = self.tree.identify_row(event.y)
        if not item_id:
            return None
        if item_id in self.item_to_skill:
            self.insert_selected()
            return "break"
        self.tree.item(item_id, open=not self.tree.item(item_id, "open"))
        return "break"

    def on_tree_return(self, _event=None) -> str:
        selection = self.tree.selection()
        if not selection:
            return "break"
        item_id = selection[0]
        if item_id in self.item_to_skill:
            self.insert_selected()
        else:
            self.tree.item(item_id, open=not self.tree.item(item_id, "open"))
        return "break"

    def trigger_text(self, send: bool) -> str:
        skill = self.selected_skill()
        if not skill:
            return ""
        suffix = "\r" if send else " "
        return f"${skill.trigger}{suffix}"

    def send_to_launcher(self, text: str) -> bool:
        sock = socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM)
        try:
            sock.connect(self.socket_path)
            sock.sendall(text.encode("utf-8"))
            return True
        except OSError:
            self.set_desc_text("发送失败，CodeX 会话可能已结束。")
            return False
        finally:
            sock.close()

    def insert_selected(self) -> None:
        skill = self.selected_skill()
        if not skill:
            return
        text = self.trigger_text(send=False)
        if not text:
            return
        if self.send_to_launcher(text):
            self.record_recent_skill(skill)
            self.refresh_tree(selected_trigger=skill.trigger)

    def send_selected(self) -> None:
        skill = self.selected_skill()
        if not skill:
            return
        text = self.trigger_text(send=True)
        if not text:
            return
        if self.send_to_launcher(text):
            self.record_recent_skill(skill)
            self.refresh_tree(selected_trigger=skill.trigger)

    def handle_exit(self, *_args) -> None:
        try:
            self.root.after(0, self.root.destroy)
        except tk.TclError:
            pass

    def watch_parent(self) -> None:
        if not self.parent_pid:
            return
        self.root.after(1500, self.check_parent)

    def check_parent(self) -> None:
        if not self.parent_pid:
            return
        try:
            os.kill(self.parent_pid, 0)
        except OSError:
            self.handle_exit()
            return
        self.root.after(1500, self.check_parent)

    def run(self) -> None:
        self.root.mainloop()


def main() -> int:
    args = parse_args()
    app = SidebarApp(
        skills_dir=Path(args.skills_dir).expanduser(),
        session_id=args.session_id,
        window_id=args.window_id,
        parent_pid=args.parent_pid,
        socket_path=args.socket_path,
    )
    app.run()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
