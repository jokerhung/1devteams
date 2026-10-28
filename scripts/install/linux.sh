#!/usr/bin/env bash
set -euo pipefail
if [[ "${1:-}" == '--help' ]]; then
  printf '%s\n' 'Usage: bash scripts/install/linux.sh [--admin-email EMAIL] [--workspace PATH] [--public-url URL] [--trust-native-agents] [--enable-remote-terminal] [--skip-providers] [--skip-browser]'
  exit 0
fi
[[ "$(uname -s)" == Linux ]] || { printf '%s\n' 'Use the macOS or Windows installer for this OS.' >&2; exit 1; }
repo_root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd)"
[[ -f "$repo_root/backend/uv.lock" ]] || { printf '%s\n' 'Extract the complete repository first.' >&2; exit 1; }
[[ $EUID -ne 0 ]] || { printf '%s\n' 'Run as your normal user; sudo is used only for OS packages.' >&2; exit 1; }
if ! command -v apt-get >/dev/null; then
  printf '%s\n' 'This installer supports Ubuntu 22.04/24.04 and Debian 12/13 (apt). Other distributions require manual OS/Playwright dependencies.' >&2
  exit 1
fi
sudo apt-get update
sudo apt-get install -y ca-certificates curl git build-essential xz-utils
if ! command -v uv >/dev/null && [[ ! -x "$repo_root/.tools/uv/uv" ]]; then
  curl --proto '=https' --tlsv1.2 -LsSf https://astral.sh/uv/install.sh |
    env UV_INSTALL_DIR="$repo_root/.tools/uv" UV_NO_MODIFY_PATH=1 sh
fi
export PATH="$repo_root/.tools/uv:$PATH"
uv python install 3.12
exec uv run --no-project --python 3.12 "$repo_root/scripts/install/install.py" "$@"
