"""Old installations load the current updater without modifying files before download."""

import io
import sys
import urllib.request
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]


def startup_code():
    shell = (ROOT / "install.sh").read_text(encoding="utf-8")
    powershell = (ROOT / "install.ps1").read_text(encoding="utf-8")
    shell_code = shell.split("<<'STARTUP_HELPER'\n", 1)[1].split("\nSTARTUP_HELPER", 1)[0]
    windows_code = powershell.split("$startupHelper = @'\n", 1)[1].split("\n'@", 1)[0]
    assert shell_code == windows_code
    return shell_code


@pytest.mark.parametrize("ref", ["main", "be155329d62ef96d8f8ab97a0b9c25e0a0de6116"])
def test_repair_stop_helper_uses_latest_code_and_installed_root(tmp_path, monkeypatch, capsys, ref):
    monkeypatch.setenv("ONEDEVTEAMS_UPDATE_REF", ref)
    shell = (ROOT / "install.sh").read_text(encoding="utf-8")
    windows = (ROOT / "install.ps1").read_text(encoding="utf-8")
    code = shell.split("<<'STOP_HELPER'\n", 1)[1].split("\nSTOP_HELPER", 1)[0]
    assert code == windows.split("$stopHelper = @'\n", 1)[1].split("\n'@", 1)[0]
    launcher = tmp_path / "scripts/install/update.py"
    monkeypatch.setattr(sys, "argv", ["-", str(launcher)])
    source = (
        b"def stop_installed():\n    print('STOP', __file__)\n"
        b"if __name__ == '__main__':\n    raise RuntimeError('Unexpected update')\n"
    )
    requests = []

    def download(url, **kwargs):
        requests.append(url)
        return io.BytesIO(source)

    monkeypatch.setattr(urllib.request, "urlopen", download)
    exec(compile(code, "repair-helper", "exec"), {})
    assert "STOP " + str(launcher) in capsys.readouterr().out
    assert f"/1devteams/{ref}/scripts/install/update.py?" in requests[0]


@pytest.mark.parametrize("offline", [False, True])
def test_update_helper_uses_installed_root_and_preserves_old_launcher(tmp_path, monkeypatch, capsys, offline):
    launcher = tmp_path / "scripts/install/run.py"
    launcher.parent.mkdir(parents=True)
    original = "print('OLD_LAUNCHER_FALLBACK')\n"
    launcher.write_text(original)
    monkeypatch.setattr(sys, "argv", ["-", str(launcher)])
    requests = []

    def download(url, timeout):
        requests.append(url)
        assert timeout == 20
        if offline:
            raise OSError("Network unavailable")
        return io.BytesIO(
            b"from pathlib import Path\n"
            b"assert __name__ == '__main__'\n"
            b"print('LATEST_HELPER_ROOT', Path(__file__).resolve().parents[2])\n"
            b"print('Localhost: http://localhost:3060; Network: http://192.168.1.20:3060')\n"
        )

    monkeypatch.setattr(urllib.request, "urlopen", download)
    if offline:
        with pytest.raises(SystemExit, match="No files were changed"):
            exec(compile(startup_code(), "bootstrap-helper", "exec"), {})
    else:
        exec(compile(startup_code(), "bootstrap-helper", "exec"), {})
    output = capsys.readouterr().out
    assert launcher.read_text() == original
    assert len(requests) == 1
    assert requests[0].split("?")[0] == (
        "https://raw.githubusercontent.com/jokerhung/1devteams/main/scripts/install/update.py"
    )
    assert "?t=" in requests[0]
    if offline:
        assert "OLD_LAUNCHER_FALLBACK" not in output
    else:
        assert str(tmp_path) in output
        assert "Localhost: http://localhost:3060; Network: http://192.168.1.20:3060" in output
        assert "OLD_LAUNCHER_FALLBACK" not in output
