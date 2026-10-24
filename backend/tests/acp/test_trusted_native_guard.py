from app.acp.guard import DynamicPermissionGuard
from app.acp.types import PermissionProfile


def test_trusted_shell_allows_heredoc_but_default_policy_does_not(tmp_path):
    profile = PermissionProfile(allow_write=True, allow_terminal=True)
    command = "python - <<'E'\nprint('test')\nE"
    assert not DynamicPermissionGuard(profile, tmp_path).check_command(command).allowed
    trusted = DynamicPermissionGuard(profile, tmp_path, trusted_native=True)
    assert trusted.check_command(command).allowed
    assert trusted.check_command("echo test > result.txt").allowed
    assert not trusted.check_command("git push origin main").allowed
    assert not trusted.check_command("git commit -m test").allowed
    assert not trusted.check_command("rm -rf temporary").allowed


def test_trusted_policy_preserves_terminal_denial_allowlist_and_paths(tmp_path):
    denied = DynamicPermissionGuard(PermissionProfile(), tmp_path, trusted_native=True)
    assert not denied.check_command("echo test > output").allowed
    limited = DynamicPermissionGuard(
        PermissionProfile(allow_terminal=True, allowed_commands=["git status"]),
        tmp_path,
        trusted_native=True,
    )
    assert limited.check_command("git status").allowed
    assert not limited.check_command("git status > output").allowed
    assert not limited.check_command("python script.py").allowed
    assert not limited.check_write("outside.txt").allowed
    assert not limited.check_read("../outside.txt").allowed
