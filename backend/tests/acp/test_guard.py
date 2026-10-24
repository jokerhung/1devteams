import logging

import pytest

from app.acp.guard import DynamicPermissionGuard, pick_option
from app.acp.types import PermissionProfile


def test_ba_cannot_write(tmp_path, caplog):
    with caplog.at_level(logging.INFO):
        decision = DynamicPermissionGuard(PermissionProfile(), tmp_path, "@custom").check_write("a.txt")
    assert not decision.allowed
    assert "@custom" in caplog.text and "allowed=False" in caplog.text


@pytest.mark.parametrize(
    "command",
    [
        "git commit -m x",
        "git  commit",
        "npm test && git commit -am x",
        "git -c user.name=a commit",
        "git -C elsewhere commit",
        "GIT COMMIT",
        "echo ok;git push",
        "git status | git commit",
        "echo $(git commit)",
        "echo `git commit`",
        'cmd /c "git commit"',
        "git push\ngit status",
        "git commitment && git commit",
        "git -c alias.r=commit r",
        "git reset HEAD --hard",
    ],
)
def test_dev_git_commit_variants(tmp_path, command):
    guard = DynamicPermissionGuard(PermissionProfile(allow_terminal=True), tmp_path)
    assert not guard.check_command(command).allowed


@pytest.mark.parametrize("command", ["npm run build", "git status", "git diff"])
def test_dev_allowed(tmp_path, command):
    guard = DynamicPermissionGuard(PermissionProfile(allow_terminal=True), tmp_path)
    assert guard.check_command(command).allowed


@pytest.mark.parametrize(
    "path", ["../outside.txt", "C:\\Windows\\x", ".git/config", "file.txt:stream", "sub/../a"]
)
def test_path_escape(tmp_path, path):
    assert not DynamicPermissionGuard(PermissionProfile(allow_write=True), tmp_path).check_write(path).allowed


def test_symlink_escape(tmp_path):
    outside = tmp_path.parent / "outside-target"
    outside.mkdir(exist_ok=True)
    try:
        (tmp_path / "escape").symlink_to(outside, target_is_directory=True)
    except OSError:
        pytest.skip("OS disallows creating symlinks for this user")
    assert (
        not DynamicPermissionGuard(PermissionProfile(allow_write=True), tmp_path)
        .check_write("escape/a")
        .allowed
    )


@pytest.mark.parametrize("path", [".env", "nested/.env.local", "key.pem", "id_rsa.pub"])
def test_env_file_blocked(tmp_path, path):
    assert not DynamicPermissionGuard(PermissionProfile(), tmp_path).check_read(path).allowed


def test_pick_option():
    options = [
        {"optionId": "a2", "kind": "allow_always"},
        {"optionId": "r1", "kind": "reject_once"},
        {"optionId": "a1", "kind": "allow_once"},
    ]
    assert pick_option(options, True)["outcome"]["optionId"] == "a1"
    assert pick_option(options, False)["outcome"]["optionId"] == "r1"
    assert pick_option([], True) == {"outcome": {"outcome": "cancelled"}}


def test_unknown_and_missing_locations_deny(tmp_path):
    guard = DynamicPermissionGuard(PermissionProfile(allow_write=True), tmp_path)
    for kind in ["edit", "read", "other", "fetch", "execute"]:
        assert not guard.evaluate_permission_request({"toolCall": {"kind": kind}}).allowed
    assert not guard.evaluate_permission_request(
        {"toolCall": {"kind": "move", "locations": [{"path": "a"}, {"path": "../outside"}]}}
    ).allowed


def test_allowlist_token_boundaries(tmp_path):
    guard = DynamicPermissionGuard(
        PermissionProfile(allow_terminal=True, allowed_commands=["npm test"]), tmp_path
    )
    assert guard.check_command("npm test -- --run").allowed
    assert not guard.check_command("npm testing").allowed
