#!/usr/bin/env bash
set -euo pipefail
if ! pwd -P >/dev/null 2>&1; then
  cd -- "${HOME:?HOME is required}"
fi
if [[ "${1:-}" == '--help' ]]; then
  printf '%s\n' 'Usage: bash scripts/install/macos.sh [--admin-email EMAIL] [--workspace PATH] [--public-url URL] [--trust-native-agents] [--enable-remote-terminal] [--skip-providers] [--skip-browser] [--no-start]'
  exit 0
fi
[[ "$(uname -s)" == Darwin ]] || { printf '%s\n' 'Use the Linux or Windows installer for this OS.' >&2; exit 1; }
[[ $EUID -ne 0 ]] || { printf '%s\n' 'Run as your normal user, not sudo.' >&2; exit 1; }
repo_root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd)"
[[ -f "$repo_root/backend/uv.lock" ]] || { printf '%s\n' 'Extract the complete repository first.' >&2; exit 1; }
cd -- "$repo_root"
# Apple's developer tools supply Git and compilers; no Homebrew is required.
if ! xcode-select -p >/dev/null 2>&1; then
  xcode-select --install || true
  printf '%s\n' 'Complete the Apple Command Line Tools dialog, then press Enter to continue.'
  read -r _
fi
xcode-select -p >/dev/null
git --version
if ! command -v uv >/dev/null && [[ ! -x "$repo_root/.tools/uv/uv" ]]; then
  curl --proto '=https' --tlsv1.2 -LsSf https://astral.sh/uv/install.sh |
    env UV_INSTALL_DIR="$repo_root/.tools/uv" UV_NO_MODIFY_PATH=1 sh
fi
export PATH="$repo_root/.tools/uv:$PATH"
uv python install 3.12
exec uv run --no-project --python 3.12 "$repo_root/scripts/install/install.py" "$@"
