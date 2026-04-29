# Homebrew formula for InvokerAI MCP server.
#
# Tap: brew tap justjammin/invokerai
# Install: brew install invokerai
#
# Before publishing to a tap, run:
#   brew create https://files.pythonhosted.org/packages/.../agent_invoker-0.1.0.tar.gz
# to get the sha256, then update `url` and `sha256` below.
#
# Dependencies (resources) must match exact PyPI versions + sha256.
# Generate with: brew update-python-resources invokerai

class Invokerai < Formula
  include Language::Python::Virtualenv

  desc "Agent routing brain — MCP server for Claude Code, Cursor, Copilot"
  homepage "https://github.com/justjammin/invokerai"

  # TODO: replace with actual PyPI sdist URL + sha256 after `pip publish`
  url "https://files.pythonhosted.org/packages/source/a/agent-invoker/agent_invoker-0.1.0.tar.gz"
  sha256 "PLACEHOLDER_RUN_brew_create_TO_GET_REAL_SHA256"
  license "MIT"

  head "https://github.com/justjammin/invokerai.git", branch: "main"

  depends_on "python@3.12"

  # scikit-learn and its dependencies.
  # Generate exact versions + sha256:
  #   brew update-python-resources invokerai --print-only
  resource "scikit-learn" do
    url "https://files.pythonhosted.org/packages/source/s/scikit-learn/scikit_learn-1.4.0.tar.gz"
    sha256 "PLACEHOLDER"
  end

  resource "numpy" do
    url "https://files.pythonhosted.org/packages/source/n/numpy/numpy-1.26.4.tar.gz"
    sha256 "PLACEHOLDER"
  end

  resource "scipy" do
    url "https://files.pythonhosted.org/packages/source/s/scipy/scipy-1.12.0.tar.gz"
    sha256 "PLACEHOLDER"
  end

  resource "joblib" do
    url "https://files.pythonhosted.org/packages/source/j/joblib/joblib-1.3.2.tar.gz"
    sha256 "PLACEHOLDER"
  end

  resource "threadpoolctl" do
    url "https://files.pythonhosted.org/packages/source/t/threadpoolctl/threadpoolctl-3.3.0.tar.gz"
    sha256 "PLACEHOLDER"
  end

  def install
    virtualenv_install_with_resources
  end

  def post_install
    # Pre-build router.pkl so first run is instant
    system libexec/"bin/python", "-m", "agent_invoker.cli", "--build-router"
  rescue
    opoo "router.pkl build skipped — regex fallback will be used on first run"
  end

  test do
    # Smoke-test: server starts, responds to initialize, exits cleanly
    require "open3"
    init = '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2024-11-05","capabilities":{},"clientInfo":{"name":"test","version":"0"}}}'
    Open3.popen3("#{bin}/invoker-mcp") do |stdin, stdout, _stderr, wait|
      stdin.puts init
      stdin.close
      output = stdout.read
      wait.value
      assert_match '"result"', output
    end
  end
end