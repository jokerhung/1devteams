#!/usr/bin/env bash
# One-line entrypoint for Linux and macOS; no Git/Python/Node prerequisite.
set -euo pipefail
case "$(uname -s)" in
  Linux) installer=linux.sh ;;
  Darwin) installer=macos.sh ;;
  *) printf '%s\n' 'Unsupported OS. On Windows use install.ps1.' >&2; exit 1 ;;
esac
[[ $EUID -ne 0 ]] || { printf '%s\n' 'Run as your normal user, not sudo.' >&2; exit 1; }
install_target="${ONEDEVTEAMS_INSTALL_DIR:-$HOME/1devTeams}"
[[ "$install_target" == /* ]] || { printf '%s\n' 'ONEDEVTEAMS_INSTALL_DIR must be an absolute path.' >&2; exit 1; }
if [[ -e "$install_target" || -L "$install_target" ]]; then
  printf '%s\n' "Destination already exists: $install_target. Nothing was overwritten." "Run bash scripts/install/$installer there to retry, or set ONEDEVTEAMS_INSTALL_DIR to a new directory." >&2
  exit 1
fi
command -v curl >/dev/null || { printf '%s\n' 'curl is required to download the source.' >&2; exit 1; }
command -v tar >/dev/null || { printf '%s\n' 'tar is required to extract the source.' >&2; exit 1; }
download_root="$(mktemp -d "${TMPDIR:-/tmp}/1devteams-install.XXXXXXXX")"
cleanup() {
  # Only this invocation's mktemp directory; never the installation directory.
  case "$download_root" in
    "${TMPDIR:-/tmp}"/1devteams-install.*) rm -rf -- "$download_root" ;;
  esac
}
trap cleanup EXIT
printf '%s\n' 'Downloading 1devTeams source from github.com/jokerhung/aiTeams (main)...'
curl --proto '=https' --tlsv1.2 -fLsS --retry 3 \
  https://github.com/jokerhung/aiTeams/archive/refs/heads/main.tar.gz -o "$download_root/source.tar.gz"
tar -xzf "$download_root/source.tar.gz" -C "$download_root"
source_root="$download_root/aiTeams-main"
for required in "scripts/install/$installer" backend/uv.lock frontend/package-lock.json; do
  [[ -f "$source_root/$required" ]] || { printf '%s\n' "Downloaded archive is missing $required. Publish the complete installer to main first." >&2; exit 1; }
done
mkdir -p -- "$(dirname -- "$install_target")"
# Reserve the destination exclusively before copying the extracted source.
mkdir -- "$install_target"
cp -R "$source_root/." "$install_target/"
printf '%s\n' "Source installed at: $install_target"
# Restore interactive stdin for sudo / Apple's developer-tools prompt when piped.
if [[ -t 0 ]]; then
  bash "$install_target/scripts/install/$installer" "$@"
elif [[ -r /dev/tty ]]; then
  bash "$install_target/scripts/install/$installer" "$@" </dev/tty
else
  printf '%s\n' "Open an interactive terminal and run: bash \"$install_target/scripts/install/$installer\"" >&2
  exit 1
fi
