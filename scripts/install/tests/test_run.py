"""Launcher URL, origin and startup checks; never start the live app or modify its config."""

import importlib.util
import io
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

spec = importlib.util.spec_from_file_location("installer_run", Path(__file__).resolve().parents[1] / "run.py")
runner = importlib.util.module_from_spec(spec)
spec.loader.exec_module(runner)


class FakeSocket:
    def __enter__(self):
        return self

    def __exit__(self, *args):
        pass

    def connect(self, address):
        pass

    def getsockname(self):
        return ("192.168.1.20", 12345)

    def bind(self, address):
        if address[0] == "203.0.113.10":
            raise OSError("Not a local address")


def test_detect_local_addresses_filters_duplicates_loopback_and_remote(monkeypatch):
    monkeypatch.setattr(runner.socket, "socket", lambda *args: FakeSocket())
    monkeypatch.setattr(
        runner.socket,
        "getaddrinfo",
        lambda *args: [
            (None, None, None, None, (address, 0))
            for address in [
                "127.0.0.1",
                "0.0.0.0",
                "169.254.1.2",
                "224.0.0.1",
                "192.168.1.20",
                "192.168.1.20",
                "10.0.0.2",
                "203.0.113.10",
                "invalid",
            ]
        ],
    )
    assert runner.local_ipv4_addresses() == ["10.0.0.2", "192.168.1.20"]


def test_discovery_offline_is_nonfatal(monkeypatch):
    def unavailable(*args):
        raise OSError("Offline")

    monkeypatch.setattr(runner.socket, "getaddrinfo", unavailable)
    monkeypatch.setattr(runner.socket, "socket", unavailable)
    assert runner.local_ipv4_addresses() == []


def test_origins_keep_custom_domain_and_use_actual_port():
    env = {"CORS_ORIGINS": "https://teams.example.com, http://localhost:3300"}
    runner.configure_origins(env, 3300, ["192.168.1.20"])
    assert env["CORS_ORIGINS"].split(",") == [
        "https://teams.example.com",
        "http://localhost:3300",
        "http://192.168.1.20:3300",
        "http://127.0.0.1:3300",
    ]
    assert "*" not in env["CORS_ORIGINS"]


def test_url_output_without_network(capsys):
    runner.print_access_urls(3300, [])
    output = capsys.readouterr().out
    assert "http://localhost:3300" in output
    assert "no usable local IPv4" in output


@pytest.mark.parametrize("healthy", [True, False])
def test_launcher_announces_urls_only_after_readiness_and_cleans_up(tmp_path, monkeypatch, capsys, healthy):
    (tmp_path / ".tools").mkdir()
    (tmp_path / ".tools/runtime.json").write_text(json.dumps({"node": "node", "git": "git"}))
    (tmp_path / ".env").write_text("FRONTEND_PORT=3300\nBACKEND_PORT=8300\n")
    (tmp_path / "backend").mkdir()
    backend_config = tmp_path / "backend/.env"
    original = "CORS_ORIGINS=https://teams.example.com\n"
    backend_config.write_text(original)
    (tmp_path / "frontend/.next-build").mkdir(parents=True)
    (tmp_path / "frontend/.next-build/BUILD_ID").write_text("test-build")
    monkeypatch.setattr(runner, "ROOT", tmp_path)
    monkeypatch.setattr(runner.sys, "argv", ["run.py", "--check"])
    monkeypatch.setattr(runner.socket, "socket", lambda *args: FakeSocket())
    monkeypatch.setattr(runner, "local_ipv4_addresses", lambda: ["192.168.1.20"])
    clock = iter([0, 100])
    monkeypatch.setattr(runner.time, "monotonic", lambda: next(clock))
    children, stopped, commands = [], [], []

    def spawn(command, **kwargs):
        commands.append((command, kwargs))
        child = SimpleNamespace(poll=lambda: None)
        children.append(child)
        return child

    def response(url, **kwargs):
        if not healthy:
            raise OSError("Not ready")
        result = io.BytesIO(b'{"status":"ok"}')
        result.status = 200
        return result

    monkeypatch.setattr(runner.subprocess, "Popen", spawn)
    monkeypatch.setattr(runner, "stop", stopped.append)
    monkeypatch.setattr(runner.urllib.request, "urlopen", response)
    if healthy:
        runner.main()
    else:
        with pytest.raises(TimeoutError):
            runner.main()
    output = capsys.readouterr().out
    assert ("Localhost: http://localhost:3300" in output) == healthy
    assert ("Network:   http://192.168.1.20:3300" in output) == healthy
    assert len(children) == len(stopped) == 2
    assert backend_config.read_text() == original
    assert "http://192.168.1.20:3300" in commands[0][1]["env"]["CORS_ORIGINS"]
    assert "127.0.0.1" in commands[0][0]
    assert "0.0.0.0" in commands[1][0]
