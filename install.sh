#!/usr/bin/env bash
# One-line entrypoint for Linux and macOS; no Git/Python/Node prerequisite.
set -euo pipefail
# A terminal may still point at a directory deleted during a previous install.
# Recover before invoking shells, uv or Python, all of which require a valid cwd.
if ! pwd -P >/dev/null 2>&1; then
  cd -- "${HOME:?HOME is required}"
fi
case "$(uname -s)" in
  Linux) installer=linux.sh ;;
  Darwin) installer=macos.sh ;;
  *) printf '%s\n' 'Unsupported OS. On Windows use install.ps1.' >&2; exit 1 ;;
esac
[[ $EUID -ne 0 ]] || { printf '%s\n' 'Run as your normal user, not sudo.' >&2; exit 1; }
install_target="${ONEDEVTEAMS_INSTALL_DIR:-$HOME/1devTeams}"
[[ "$install_target" == /* ]] || { printf '%s\n' 'ONEDEVTEAMS_INSTALL_DIR must be an absolute path.' >&2; exit 1; }
if [[ -e "$install_target" || -L "$install_target" ]]; then
  for required in scripts/install/run.py scripts/install/install.py; do
    if [[ ! -f "$install_target/$required" ]]; then
      printf '%s\n' "Existing directory is not a complete installation: $install_target (missing $required). Nothing was overwritten." "Run bash scripts/install/$installer there to finish installing, or set ONEDEVTEAMS_INSTALL_DIR to a new directory." >&2
      exit 1
    fi
  done
  python="$install_target/backend/.venv/bin/python"
  if [[ ! -f "$install_target/backend/.env" || ! -x "$python" ]]; then
    [[ -f "$install_target/scripts/install/$installer" ]] || { printf '%s\n' "OS installer missing. Restore scripts/install/$installer to repair it." >&2; exit 1; }
    if [[ ! -f "$install_target/backend/.env" ]]; then
      # Never invent replacement encryption keys for an existing database or attachments.
      old_database="$(
        shopt -s nullglob dotglob nocaseglob
        for candidate in "$install_target"/*.db* "$install_target"/*.sqlite* \
          "$install_target/backend"/*.db* "$install_target/backend"/*.sqlite*; do
          printf '%s\n' "$candidate"; break
        done
      )"
      old_data="$(
        shopt -s nullglob dotglob
        for candidate in "$install_target/backend/data/"*; do
          printf '%s\n' "$candidate"; break
        done
      )"
      if [[ -n "$old_database" || -n "$old_data" ]]; then
        printf '%s\n' 'backend/.env is missing, but existing database/data was found. Restore the original backend/.env (especially APP_SECRET_KEY and JWT_SECRET) from backup, then rerun this command. No files were changed.' >&2
        exit 1
      fi
    fi
    printf '%s\n' "Resuming the incomplete installation at: $install_target"
    cd -- "$install_target"
    # Finish prerequisite/configuration steps using the installed OS installer,
    # then use the latest updater below before starting the server.
    if [[ -t 0 ]]; then
      bash "$install_target/scripts/install/$installer" --no-start "$@"
    elif ( : </dev/tty ) >/dev/null 2>&1; then
      bash "$install_target/scripts/install/$installer" --no-start "$@" </dev/tty
    else
      bash "$install_target/scripts/install/$installer" --no-start "$@" </dev/null
    fi
    [[ -f "$install_target/backend/.env" && -x "$python" ]] || { printf '%s\n' 'Repair did not create backend configuration/venv. Check the installer output above.' >&2; exit 1; }
  fi
  printf '%s\n' "Updating the installed version at: $install_target" 'Configuration and user data will be preserved; a recovery backup is created before updating.'
  cd -- "$install_target"
  exec "$python" - "$install_target/scripts/install/run.py" <<'STARTUP_HELPER'
import sys
import time
import urllib.request
from pathlib import Path

launcher = Path(sys.argv[1]).resolve().with_name('update.py')
sys.argv = [str(launcher)]
helper_url = f'https://raw.githubusercontent.com/jokerhung/1devteams/main/scripts/install/update.py?t={time.time_ns()}'
try:
    with urllib.request.urlopen(helper_url, timeout=20) as response:
        source = response.read().decode('utf-8')
except (OSError, UnicodeError) as error:
    sys.exit(f'Could not load the updater ({error}). No files were changed; the running server was left alone.')
else:
    # Preserve the installed project root without writing over its launcher.
    exec(compile(source, helper_url, 'exec'), {'__name__': '__main__', '__file__': str(launcher)})
STARTUP_HELPER
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
printf '%s\n' 'Downloading 1devTeams source from github.com/jokerhung/1devteams (main)...'
curl --proto '=https' --tlsv1.2 -fLsS --retry 3 \
  https://github.com/jokerhung/1devteams/archive/refs/heads/main.tar.gz -o "$download_root/source.tar.gz"
# GitHub changes the archive's top-level directory when the repository is renamed.
source_root="$download_root/source"
mkdir -- "$source_root"
tar -xzf "$download_root/source.tar.gz" --strip-components=1 -C "$source_root"
for required in "scripts/install/$installer" backend/uv.lock frontend/package-lock.json; do
  [[ -f "$source_root/$required" ]] || { printf '%s\n' "Downloaded archive is missing $required. Publish the complete installer to main first." >&2; exit 1; }
done
mkdir -p -- "$(dirname -- "$install_target")"
# Reserve the destination exclusively before copying the extracted source.
mkdir -- "$install_target"
cp -R "$source_root/." "$install_target/"
cd -- "$install_target"
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
