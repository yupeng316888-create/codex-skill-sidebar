class CodexSkillSidebar < Formula
  desc "Floating skills sidebar for the Codex terminal workflow on macOS"
  homepage "https://github.com/yupeng316888-create/codex-skill-sidebar"
  url "https://github.com/yupeng316888-create/codex-skill-sidebar/archive/refs/heads/main.tar.gz"
  version "main"
  sha256 :no_check
  license "MIT"

  depends_on :macos

  def install
    libexec.install Dir["*"]
    inreplace libexec/"bin/codex-skill-sidebar",
              "__CODEX_SIDEBAR_SOURCE_DIR__",
              libexec.to_s
    bin.install libexec/"bin/codex-skill-sidebar"
  end

  def caveats
    <<~EOS
      Finish setup with:
        codex-skill-sidebar install

      This will:
        - copy the runtime scripts into ~/.local/bin
        - add codex / CodeX wrappers to ~/.zshrc
        - set apps = false in ~/.codex/config.toml
    EOS
  end

  test do
    assert_match "codex-skill-sidebar doctor", shell_output("#{bin}/codex-skill-sidebar doctor")
  end
end
