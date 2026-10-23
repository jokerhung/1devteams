import asyncio
import io
import re
import warnings
from datetime import timedelta
from pathlib import Path

import filetype
from PIL import Image
from sqlalchemy import delete, func, select, update

from app.core.deps import fail
from app.db.base import new_id, now
from app.db.models import Attachment, Ticket, TicketMessage

SCRIPT_EXTENSIONS = {".exe", ".bat", ".cmd", ".ps1", ".sh", ".msi", ".com", ".scr", ".dll"}
IMAGE_MIMES = {"image/png", "image/jpeg", "image/webp"}
Image.MAX_IMAGE_PIXELS = 20_000_000


def thumbnail(data: bytes) -> bytes:
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(io.BytesIO(data)) as image:
                image.verify()
            with Image.open(io.BytesIO(data)) as image:
                image.load()
                image.thumbnail((256, 256))
                clean = Image.new("RGBA", image.size)
                clean.paste(image.convert("RGBA"))
                output = io.BytesIO()
                clean.save(output, format="PNG")
                return output.getvalue()
    except (OSError, ValueError, Image.DecompressionBombError, Image.DecompressionBombWarning):
        raise ValueError("Ảnh không hợp lệ hoặc quá lớn") from None


def mime_type(data: bytes) -> str:
    kind = filetype.guess(data)
    if kind:
        return kind.mime
    try:
        data.decode("utf-8")
        if b"\x00" not in data:
            return "text/plain"
    except UnicodeError:
        pass
    return "application/octet-stream"


def safe_name(value: str) -> str:
    value = value.replace("\\", "/").rsplit("/", 1)[-1]
    return re.sub(r"[^\w.() -]", "_", value, flags=re.UNICODE).strip(" .")[:200] or "file"


async def cleanup_pending(db, settings) -> int:
    stale = list(
        (
            await db.execute(
                delete(Attachment)
                .where(Attachment.message_id.is_(None), Attachment.created_at < now() - timedelta(hours=24))
                .returning(Attachment.storage_path, Attachment.thumbnail_path)
            )
        ).all()
    )
    await db.commit()
    root = settings.data_dir.resolve()
    for row in stale:
        for name in (row.storage_path, row.thumbnail_path):
            if name:
                path = await asyncio.to_thread(Path(name).resolve)
                if path.is_relative_to(root):
                    await asyncio.to_thread(path.unlink, missing_ok=True)
    return len(stale)


async def attach_to_message(db, ticket_id: str, message_id: str, ids: list[str], user_id: str, settings):
    if len(set(ids)) != len(ids) or len(ids) > settings.attach_max_files:
        fail(422, "Quá số tệp đính kèm cho một tin nhắn", "attachment_limit")
    message = await db.get(TicketMessage, message_id)
    if not message or message.ticket_id != ticket_id:
        fail(422, "Tin nhắn không thuộc ticket", "validation_error")
    await db.execute(
        update(Ticket).where(Ticket.id == ticket_id).values(next_message_seq=Ticket.next_message_seq)
    )
    rows = list(
        (
            await db.scalars(
                select(Attachment).where(
                    Attachment.id.in_(ids), Attachment.created_at >= now() - timedelta(hours=24)
                )
            )
        ).all()
    )
    existing = await db.scalar(
        select(func.count()).select_from(Attachment).where(Attachment.message_id == message_id)
    )
    if existing + len(rows) > settings.attach_max_files:
        fail(422, "Quá số tệp đính kèm cho một tin nhắn", "attachment_limit")
    if len(rows) != len(ids) or any(
        row.ticket_id != ticket_id or row.uploaded_by != user_id or row.message_id for row in rows
    ):
        fail(422, "Tệp không thuộc người gửi hoặc đã được sử dụng", "invalid_attachment")
    for row in rows:
        row.message_id = message_id


async def store_attachment(db, ticket: Ticket, upload, user_id: str, settings) -> Attachment:
    data = await upload.read(settings.attach_max_mb * 1024 * 1024 + 1)
    if len(data) > settings.attach_max_mb * 1024 * 1024:
        fail(413, "Tệp vượt giới hạn dung lượng", "file_too_large")
    filename = safe_name(upload.filename or "file")
    original_name = (upload.filename or "file").replace("\\", "/").rsplit("/", 1)[-1]
    mime = mime_type(data)
    executable = data.startswith((b"MZ", b"\x7fELF", b"#!"))
    if not settings.attach_allow_scripts and (
        {suffix.lower() for suffix in Path(original_name).suffixes} & SCRIPT_EXTENSIONS or executable
    ):
        fail(422, "Không cho phép tệp thực thi/script", "unsafe_file")
    thumb = None
    if mime in IMAGE_MIMES:
        try:
            thumb = await asyncio.to_thread(thumbnail, data)
        except ValueError:
            fail(422, "Ảnh không hợp lệ hoặc quá lớn", "invalid_image")
    await db.execute(
        update(Ticket).where(Ticket.id == ticket.id).values(next_message_seq=Ticket.next_message_seq)
    )
    pending = await db.scalar(
        select(func.count())
        .select_from(Attachment)
        .where(
            Attachment.ticket_id == ticket.id,
            Attachment.uploaded_by == user_id,
            Attachment.message_id.is_(None),
        )
    )
    if pending >= settings.attach_max_files:
        fail(422, "Quá số tệp chờ gửi; tối đa 5 tệp/tin nhắn", "attachment_limit")
    identifier = new_id()
    folder = settings.data_dir.resolve() / "blobs/attachments" / ticket.id
    await asyncio.to_thread(folder.mkdir, parents=True, exist_ok=True)
    path = folder / f"{identifier}_{filename}"
    thumb_path = folder / f"{identifier}.thumb.png" if thumb else None
    try:
        await asyncio.to_thread(path.write_bytes, data)
        if thumb_path:
            await asyncio.to_thread(thumb_path.write_bytes, thumb)
        row = Attachment(
            id=identifier,
            ticket_id=ticket.id,
            uploaded_by=user_id,
            filename=filename,
            mime=mime,
            size=len(data),
            storage_path=str(path),
            thumbnail_path=str(thumb_path) if thumb_path else None,
        )
        db.add(row)
        await db.commit()
        return row
    except BaseException:
        await asyncio.to_thread(path.unlink, missing_ok=True)
        if thumb_path:
            await asyncio.to_thread(thumb_path.unlink, missing_ok=True)
        raise
