import pytest

from app.acp.guard import DynamicPermissionGuard
from app.acp.types import PermissionProfile
from app.services.git_service import GitService


async def test_git_push_failure_keeps_local_commit(engine_client):
    client = engine_client
    # A local path is used as the remote target, never an external repository.
    client.git("remote", "set-url", "origin", str(client.remote.parent / "missing.git"))
    (client.workspace / "app.txt").write_text("local repair\n")
    before = client.git("rev-parse", "HEAD").strip()
    git = GitService(client.workspace)
    with pytest.raises(RuntimeError, match="Commit local"):
        await git.commit_and_push(["app.txt"], "fix: local repair", remote="origin", branch="main")
    assert client.git("rev-parse", "HEAD").strip() != before
    assert not client.git("diff", "--name-only").strip()


async def test_git_rejects_detached_unsafe_options_and_symlink(engine_client):
    client = engine_client
    git = GitService(client.workspace)
    for args in [("reset", "--hard"), ("push", "--force", "main"), ("push", "origin"), ("clean", "-f")]:
        with pytest.raises(ValueError):
            await git.run(*args)
    (client.workspace / "app.txt").write_text("repair\n")
    for name in ["../escape", ".env", "-option", ".aiteams/attachments/file.txt", "dist/out.js", "key.pem"]:
        with pytest.raises(ValueError):
            await git.commit_and_push([name], "fix: repair", remote="origin", branch="main")
    client.git("checkout", "--detach")
    with pytest.raises(ValueError, match="Detached"):
        await git.commit_and_push(["app.txt"], "fix: repair", remote="origin", branch="main")


@pytest.mark.parametrize(
    "command",
    ["git commit -m test", "git push origin main", "git add app.txt", "git -c user.name=x push origin main"],
)
def test_no_profile_can_grant_llm_git_release(tmp_path, command):
    guard = DynamicPermissionGuard(
        PermissionProfile(allow_terminal=True, can_git_release=True, blocked_commands=[]), tmp_path, "@leader"
    )
    assert not guard.check_command(command).allowed
