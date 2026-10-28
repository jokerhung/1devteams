from pathlib import Path

from fastapi import HTTPException

from app.core.config import Settings
from app.db.models import User


def default_terminal_workspace(settings: Settings, user: User) -> Path:
    # A host-level shell has no project membership boundary; restrict it to host admins.
    if user.system_role not in {"OWNER", "ADMIN"}:
        raise HTTPException(403, "Chỉ quản trị viên được mở terminal ngoài project")
    roots = settings.workspace_roots
    if not roots:
        raise ValueError("Chưa cấu hình thư mục được phép truy cập")
    workspace = roots[0]
    if not workspace.is_dir():
        raise ValueError("Thư mục cho phép đầu tiên không tồn tại hoặc không truy cập được")
    return workspace
