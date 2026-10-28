"""Installer checks use disposable directories/SQLite, never the running installation."""

import asyncio
import importlib.util
import socket
from pathlib import Path
from types import SimpleNamespace

import pytest


def load_helper(name):
    path = Path(__file__).resolve().parents[1] / f"{name}.py"
    spec = importlib.util.spec_from_file_location(f"installer_{name}", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


initializer = load_helper("initialize")
installer = load_helper("install")


def options(**overrides):
    return SimpleNamespace(
        **{
            **dict(
                admin_email="owner@example.com",
                frontend_port=3060,
                backend_port=8060,
                public_url="",
                workspace="",
                trust_native_agents=False,
                enable_remote_terminal=False,
            ),
            **overrides,
        }
    )


@pytest.mark.parametrize(
    ("system", "machine", "suffix"),
    [
        ("Windows", "AMD64", "win-x64.zip"),
        ("Windows", "ARM64", "win-arm64.zip"),
        ("Linux", "x86_64", "linux-x64.tar.gz"),
        ("Linux", "aarch64", "linux-arm64.tar.gz"),
        ("Darwin", "x86_64", "darwin-x64.tar.gz"),
        ("Darwin", "arm64", "darwin-arm64.tar.gz"),
    ],
)
def test_node_archive_selection(system, machine, suffix):
    name, digest = f"node-v22.22.0-{suffix}", "a" * 64
    assert installer.node_archive(system, machine, f"{digest}  {name}\n") == (name, digest)


def test_node_rejects_unknown_architecture():
    with pytest.raises(ValueError, match="Unsupported architecture"):
        installer.node_archive("Linux", "i386", "")


def test_config_round_trip_and_preserve_existing(tmp_path):
    root = tmp_path / "source with spaces"
    args = options(workspace=str(tmp_path / "O'Brien workspace"), public_url="https://teams.example.com/")
    assert initializer.configure(root, args)
    config = initializer.dotenv_values(root / "backend/.env", interpolate=False)
    assert config["ALLOWED_WORKSPACE_ROOTS"] == args.workspace
    assert "https://teams.example.com" in config["CORS_ORIGINS"]
    assert config["TRUSTED_NATIVE_ACP"] == "false"
    assert config["ENABLE_REMOTE_TERMINAL"] == "false"
    assert len(config["BOOTSTRAP_ADMIN_PASSWORD"]) >= 24
    initializer.Fernet(config["APP_SECRET_KEY"].encode())
    files = [root / name for name in (".env", "backend/.env", "frontend/.env")]
    before = {file: file.read_bytes() for file in files}
    assert not initializer.configure(root, options(frontend_port=3300, trust_native_agents=True))
    assert {file: file.read_bytes() for file in files} == before


def test_invalid_origin_does_not_create_config(tmp_path):
    with pytest.raises(ValueError, match="origin"):
        initializer.configure(tmp_path, options(public_url="https://example.com/private"))
    assert not (tmp_path / ".env").exists()


def test_explicit_permissions(tmp_path):
    initializer.configure(tmp_path, options(trust_native_agents=True, enable_remote_terminal=True))
    values = initializer.dotenv_values(tmp_path / "backend/.env")
    assert values["TRUSTED_NATIVE_ACP"] == values["ENABLE_REMOTE_TERMINAL"] == "true"


def test_settings_never_inherit_unrelated_environment(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql://unrelated-database")
    monkeypatch.setenv("CHECKPOINT_POSTGRES_URL", "postgresql://unrelated-checkpoints")
    monkeypatch.setenv("TRUSTED_NATIVE_ACP", "true")
    settings = initializer.InstallSettings(_env_file=None, jwt_secret="test-secret")
    assert settings.database_url.startswith("sqlite")
    assert settings.checkpoint_postgres_url is None
    assert not settings.trusted_native_acp


def test_existing_port_in_use_stops_preflight(tmp_path):
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        listener.listen()
        port = listener.getsockname()[1]
        initializer.write_new_env(tmp_path / ".env", {"FRONTEND_PORT": port, "BACKEND_PORT": 1})
        with pytest.raises(ValueError, match="Stop the application"):
            installer.preflight_ports(tmp_path, 3060, 8060)


def test_invalid_ports_rejected(tmp_path):
    with pytest.raises(ValueError, match="different"):
        installer.preflight_ports(tmp_path, 3060, 3060)


def test_fresh_seed_and_idempotent_rerun(tmp_path, monkeypatch):
    from app.core.security import verify_password
    from app.services.workflow_templates import configured_graph

    initializer.configure(tmp_path, options())
    env_file = tmp_path / "backend/.env"
    values = initializer.dotenv_values(env_file, interpolate=False)
    monkeypatch.setenv("DATABASE_URL", "postgresql://must-not-be-used")

    async def scenario():
        counts = await initializer.initialize(env_file)
        assert counts == {"users": 1, "agents": 9, "teams": 3, "workflow_templates": 4}
        engine, sessions = initializer.database(values["DATABASE_URL"])
        try:
            async with sessions() as db:
                user = await db.scalar(initializer.select(initializer.User))
                password_hash = user.password_hash
                assert user.system_role == "OWNER"
                assert await verify_password(values["BOOTSTRAP_ADMIN_PASSWORD"], password_hash)
                agents = list((await db.scalars(initializer.select(initializer.Agent))).all())
                templates = list((await db.scalars(initializer.select(initializer.WorkflowTemplate))).all())
                for template in templates:
                    graph = await configured_graph(db, template.key, agents)
                    assert initializer.validate_graph(graph, agents) == []
                    for node in graph.nodes:
                        if node.type in {"agent", "git_release"}:
                            assert node.data["agent_handle"]
                            assert node.data["agent_role"]
                developer = next(agent for agent in agents if agent.handle == "@developer")
                developer.system_prompt = "My customized prompt"
                team = await db.scalar(initializer.select(initializer.Team))
                team.description = "My customized team"
                template = next(item for item in templates if item.key == "bugfix_default")
                template.instructions = {"n_ba": "My customized instructions"}
                await db.commit()
                ids = (developer.id, team.id, template.id)
            assert await initializer.initialize(env_file) == counts
            async with sessions() as db:
                assert (await db.get(initializer.Agent, ids[0])).system_prompt == "My customized prompt"
                assert (await db.get(initializer.Team, ids[1])).description == "My customized team"
                assert (await db.get(initializer.WorkflowTemplate, ids[2])).instructions == {
                    "n_ba": "My customized instructions"
                }
                assert (await db.scalar(initializer.select(initializer.User))).password_hash == password_hash
        finally:
            await engine.dispose()

    asyncio.run(scenario())


def test_empty_bootstrap_password_rejected(tmp_path):
    initializer.write_new_env(
        tmp_path / ".env",
        {
            "JWT_SECRET": "test-only",
            "DATABASE_URL": "sqlite+aiosqlite:///" + (tmp_path / "empty.db").as_posix(),
            "BOOTSTRAP_ADMIN_EMAIL": "owner@example.com",
            "BOOTSTRAP_ADMIN_PASSWORD": "",
        },
    )
    with pytest.raises(ValueError, match="BOOTSTRAP_ADMIN_PASSWORD"):
        asyncio.run(initializer.initialize(tmp_path / ".env"))
