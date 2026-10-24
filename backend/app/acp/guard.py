"""Profile-based checks at client permission and execution boundaries.

Shell checks are a conservative admission filter, not an OS sandbox. Native adapter tools
must be routed through these boundaries before arbitrary workspace access is enabled.
"""

from __future__ import annotations

import logging
import re
import shlex
from pathlib import Path, PureWindowsPath

from pydantic import BaseModel

from app.acp.types import Json, PermissionProfile

logger = logging.getLogger(__name__)


class Decision(BaseModel):
    allowed: bool
    reason: str


def pick_option(options: list[Json], allowed: bool) -> Json:
    kinds = ("allow_once", "allow_always") if allowed else ("reject_once", "reject_always")
    for kind in kinds:
        for option in options:
            if option.get("kind") == kind and isinstance(option.get("optionId"), str):
                return {"outcome": {"outcome": "selected", "optionId": option["optionId"]}}
    return {"outcome": {"outcome": "cancelled"}}


def command_tokens(command: str) -> list[str]:
    tokens = shlex.split(command, posix=True)
    if not tokens:
        return []
    tokens = [token.lower() for token in tokens]
    tokens[0] = re.split(r"[/\\]", tokens[0])[-1].removesuffix(".exe").removesuffix(".cmd")
    if tokens[0] == "git":
        i = 1
        while i < len(tokens) and tokens[i].startswith("-"):
            if tokens[i] in ("-c", "--config-env"):
                i += 2
            elif tokens[i].startswith(("-c", "--git-dir=", "--work-tree=", "--config-env=")):
                i += 1
            elif tokens[i] in ("--git-dir", "--work-tree"):
                i += 2
            else:
                i += 1
        tokens = ["git", *tokens[i:]]
    return tokens


class DynamicPermissionGuard:
    def __init__(
        self,
        profile: PermissionProfile,
        workspace: Path,
        agent_handle: str = "",
        *,
        trusted_native: bool = False,
    ) -> None:
        self.profile = profile.model_copy(deep=True)
        self.workspace = workspace.resolve()
        self.agent_handle = agent_handle
        self.trusted_native = trusted_native

    def decision(self, action: str, allowed: bool, reason: str) -> Decision:
        logger.info(
            "Guard agent=%s action=%s allowed=%s reason=%s", self.agent_handle, action, allowed, reason
        )
        return Decision(allowed=allowed, reason=reason)

    def resolve_path(self, raw: str) -> Path:
        # Windows drive/UNC syntax must not become a harmless relative filename on Linux.
        if PureWindowsPath(raw).drive and not Path(raw).is_absolute():
            raise ValueError("Foreign or drive-relative path")
        parts = raw.replace("\\", "/").split("/")
        path_without_drive = raw[len(PureWindowsPath(raw).drive) :]
        if ".." in parts or ":" in path_without_drive:
            raise ValueError("Traversal or alternate stream path")
        path = (self.workspace / raw).resolve()
        if not path.is_relative_to(self.workspace):
            raise ValueError("Path outside workspace")
        if any(
            part.lower().startswith((".env", "id_rsa")) or part.lower().endswith(".pem")
            for part in path.parts
        ):
            raise ValueError("Sensitive file")
        return path

    def _check_path(self, raw: str, write: bool) -> Decision:
        action = "write" if write else "read"
        try:
            path = self.resolve_path(raw)
            if write and any(part.lower() == ".git" for part in path.relative_to(self.workspace).parts):
                raise ValueError("Git metadata is read-only")
        except (OSError, ValueError) as error:
            return self.decision(action, False, str(error))
        allowed = self.profile.allow_write if write else self.profile.allow_read
        return self.decision(
            action, allowed, "Allowed by profile" if allowed else f"Profile forbids {action}"
        )

    def check_read(self, path: str) -> Decision:
        return self._check_path(path, False)

    def check_write(self, path: str) -> Decision:
        return self._check_path(path, True)

    def check_command(self, command: str, args: list[str] | None = None) -> Decision:
        if not self.profile.allow_terminal:
            return self.decision("execute", False, "Profile forbids terminal")
        text = " ".join([command, *(args or [])])
        if self.trusted_native and not self.profile.allowed_commands:
            # Host-authorized native execution is not a sandbox. Keep best-effort
            # deny checks, but do not claim shell parsing can enforce isolation.
            if re.search(
                r"(?i)\bgit(?:\.exe)?\s+(?:-[^\s]+\s+)*(?:add|commit|push|merge|reset|clean|checkout|"
                r"rebase|cherry-pick|apply|restore|update-ref|config|init|clone)\b",
                text,
            ):
                return self.decision("execute", False, "Git mutations are reserved for backend GitService")
            for blocked in self.profile.blocked_commands:
                parts = blocked.split()
                if parts and re.search(
                    r"(?i)(?<![\w-])" + r"\s+".join(re.escape(part) for part in parts) + r"(?![\w-])",
                    text,
                ):
                    return self.decision("execute", False, f"Blocked command: {blocked}")
            return self.decision("execute", True, "Allowed by host trusted-native policy (not sandboxed)")
        if re.search(r"(?:^|\s)-c(?:\s|\S)", text):
            return self.decision("execute", False, "Inline command configuration is not permitted")
        if re.search(r"(?i)\balias\.|--exec-path|--config-env", text):
            return self.decision("execute", False, "Git command rewriting is not permitted")
        # Expansion, redirection and wrappers cannot be safely inspected as plain prefixes.
        if re.search(r"[$%`^<>]", text):
            return self.decision(
                "execute", False, "Shell expansion or redirection requires an external sandbox"
            )
        segments = [part.strip() for part in re.split(r"&&|\|\||[;|\r\n&]", text) if part.strip()]
        try:
            for segment in segments:
                tokens = command_tokens(segment)
                if not tokens or tokens[0] in {
                    "cmd",
                    "powershell",
                    "pwsh",
                    "bash",
                    "sh",
                    "env",
                    "eval",
                    "exec",
                    "call",
                    "python",
                    "python3",
                    "python3.11",
                    "python3.12",
                    "node",
                    "ruby",
                    "perl",
                    "wscript",
                    "cscript",
                    "mshta",
                    "rundll32",
                    "base64",
                    "source",
                    ".",
                    "command",
                    "sudo",
                    "doas",
                    "start",
                    "xargs",
                    "find",
                    "ssh",
                    "curl",
                    "wget",
                }:
                    return self.decision("execute", False, "Uninspectable command wrapper")
                if tokens[0] == "git" and (
                    len(tokens) < 2
                    or tokens[1]
                    not in {"status", "diff", "log", "show", "rev-parse", "ls-files", "blame", "shortlog"}
                    or any(t.startswith(("--output", "--ext-diff", "--textconv")) for t in tokens)
                ):
                    return self.decision("execute", False, "Only read-only Git inspection is permitted")
                if (
                    tokens[0] == "git"
                    and len(tokens) > 1
                    and tokens[1]
                    in {
                        "add",
                        "commit",
                        "push",
                        "merge",
                        "reset",
                        "clean",
                        "checkout",
                        "rebase",
                        "cherry-pick",
                        "apply",
                        "restore",
                        "update-ref",
                        "config",
                        "init",
                        "clone",
                    }
                ):
                    return self.decision(
                        "execute", False, "Git mutations are reserved for backend GitService"
                    )
                for blocked in self.profile.blocked_commands:
                    pattern = command_tokens(blocked)
                    matches = bool(pattern and tokens[: len(pattern)] == pattern)
                    if pattern == ["git", "reset", "--hard"] and tokens[:2] == ["git", "reset"]:
                        matches = "--hard" in tokens
                    if matches:
                        return self.decision("execute", False, f"Blocked command: {blocked}")
                if self.profile.allowed_commands and not any(
                    tokens[: len(prefix)] == prefix
                    for prefix in map(command_tokens, self.profile.allowed_commands)
                    if prefix
                ):
                    return self.decision("execute", False, "Command is not in allowlist")
        except ValueError:
            return self.decision("execute", False, "Malformed shell quoting")
        return self.decision("execute", bool(segments), "Allowed by profile" if segments else "Empty command")

    def evaluate_permission_request(self, params: Json) -> Decision:
        tool = params.get("toolCall", {})
        kind, raw = tool.get("kind"), tool.get("rawInput") or {}
        if not isinstance(raw, dict):
            return self.decision("permission", False, "Missing structured tool input")
        if kind == "execute":
            command = raw.get("command")
            if not isinstance(command, str):
                return self.decision("execute", False, "Missing command")
            return self.check_command(command, raw.get("args"))
        if kind in ("read", "search", "edit", "delete", "move"):
            paths = [item.get("path") for item in tool.get("locations", [])]
            paths += [raw[key] for key in ("path", "file_path", "source", "destination") if key in raw]
            if not paths or any(not isinstance(path, str) for path in paths):
                return self.decision("permission", False, "No authoritative paths supplied")
            for path in paths:
                decision = self.check_read(path) if kind in ("read", "search") else self.check_write(path)
                if not decision.allowed:
                    return decision
            return self.decision("permission", True, "All paths allowed")
        if kind == "fetch":
            return self.decision("fetch", self.profile.allow_fetch, "Network access policy")
        return self.decision("permission", False, "Unknown tool kind")
