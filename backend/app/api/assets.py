import asyncio
from pathlib import Path
from uuid import UUID

from fastapi import APIRouter, Request, UploadFile
from fastapi.responses import FileResponse

from app.api.tickets import authorized_ticket
from app.core.deps import DB, Admin, CurrentUser, fail, record
from app.db.base import new_id
from app.db.models import Attachment
from app.schemas.ticket import AttachmentOut
from app.services.assets import IMAGE_MIMES, mime_type, store_attachment, thumbnail

router = APIRouter(tags=["Assets"])


@router.post("/assets/logo", status_code=201)
async def logo(file: UploadFile, request: Request, user: Admin) -> dict:
    data = await file.read(300 * 1024 + 1)
    if len(data) > 300 * 1024:
        fail(413, "Logo tối đa 300KB", "file_too_large")
    if mime_type(data) not in IMAGE_MIMES:
        fail(422, "Logo phải là ảnh PNG/JPG/WebP", "invalid_image")
    try:
        clean = await asyncio.to_thread(thumbnail, data)
    except ValueError:
        fail(422, "Ảnh không hợp lệ hoặc quá lớn", "invalid_image")
    identifier = new_id()
    folder = request.app.state.settings.data_dir.resolve() / "blobs/logos"
    await asyncio.to_thread(folder.mkdir, parents=True, exist_ok=True)
    await asyncio.to_thread((folder / f"{identifier}.png").write_bytes, clean)
    return {"logo_url": f"/api/assets/logos/{identifier}.png"}


@router.get("/assets/logos/{identifier}.png", response_class=FileResponse)
async def get_logo(identifier: UUID, request: Request, user: CurrentUser):
    path = request.app.state.settings.data_dir.resolve() / "blobs/logos" / f"{identifier}.png"
    if not await asyncio.to_thread(path.is_file):
        fail(404, "Không tìm thấy logo", "not_found")
    return FileResponse(path, media_type="image/png", headers={"X-Content-Type-Options": "nosniff"})


@router.post("/tickets/{tid}/attachments", response_model=AttachmentOut, status_code=201)
async def upload_attachment(tid: UUID, file: UploadFile, request: Request, db: DB, user: CurrentUser) -> dict:
    ticket = await authorized_ticket(db, tid, user, report=True)
    if ticket.status in {"COMPLETED", "CANCELLED"}:
        fail(409, "Ticket đã kết thúc", "invalid_ticket_status")
    row = await store_attachment(db, ticket, file, user.id, request.app.state.settings)
    return {
        "id": row.id,
        "filename": row.filename,
        "mime": row.mime,
        "size": row.size,
        "url": f"/api/attachments/{row.id}",
        "thumbnail_url": f"/api/attachments/{row.id}?thumbnail=true" if row.thumbnail_path else None,
    }


@router.get("/attachments/{identifier}", response_class=FileResponse)
async def attachment(identifier: UUID, request: Request, db: DB, user: CurrentUser, thumbnail: bool = False):
    row = await record(db, Attachment, identifier)
    await authorized_ticket(db, row.ticket_id, user)
    path = await asyncio.to_thread(
        Path(row.thumbnail_path if thumbnail and row.thumbnail_path else row.storage_path).resolve
    )
    if not path.is_relative_to(request.app.state.settings.data_dir.resolve()) or not await asyncio.to_thread(
        path.is_file
    ):
        fail(404, "Không tìm thấy tệp", "not_found")
    return FileResponse(
        path,
        media_type="image/png" if thumbnail else row.mime,
        filename=f"{row.filename}.png" if thumbnail else row.filename,
        headers={"X-Content-Type-Options": "nosniff", "Content-Security-Policy": "sandbox"},
    )


@router.delete("/attachments/{identifier}", status_code=204)
async def delete_pending_attachment(identifier: UUID, request: Request, db: DB, user: CurrentUser):
    row = await record(db, Attachment, identifier)
    await authorized_ticket(db, row.ticket_id, user, report=True)
    if row.uploaded_by != user.id or row.message_id:
        fail(409, "Chỉ gỡ tệp chờ gửi của bạn", "attachment_in_use")
    paths = [row.storage_path, row.thumbnail_path]
    await db.delete(row)
    await db.commit()
    for name in paths:
        if name:
            path = await asyncio.to_thread(Path(name).resolve)
            if path.is_relative_to(request.app.state.settings.data_dir.resolve()):
                await asyncio.to_thread(path.unlink, missing_ok=True)
