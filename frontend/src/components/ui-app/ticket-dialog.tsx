"use client";
import { useState } from "react";
import { useRouter } from "next/navigation";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { apiFetch, send } from "@/lib/api";
import type { Workflow, Ticket } from "@/lib/types";
import { Modal } from "./primitives";
export function CreateTicketDialog({
  pid,
  wid,
  onClose,
}: {
  pid: string;
  wid: string;
  onClose: () => void;
}) {
  const router = useRouter();
  const client = useQueryClient();
  const [files, setFiles] = useState<File[]>([]);
  const [autoStart, setAutoStart] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [created, setCreated] = useState<{
    ticket: Ticket;
    chat_url: string;
  } | null>(null);
  const workflow = useQuery({
    queryKey: ["workflows", wid],
    queryFn: () => apiFetch<Workflow>(`/workflows/${wid}`),
  });
  return (
    <Modal title="Tạo Ticket" onClose={onClose}>
      <p className="mb-4 text-[11px] text-stone-400">
        1. Project › 2. Workflow › <b className="text-stone-900">3. Ticket</b> ›
        4. Chat
      </p>
      <p className="mb-4 rounded-lg bg-stone-50 p-3 text-xs">
        Workflow:{" "}
        <b>
          {workflow.data?.name} ({workflow.data?.ticket_prefix}) · v
          {workflow.data?.published_version}
        </b>
      </p>
      <form
        className="space-y-4"
        onSubmit={async (e) => {
          e.preventDefault();
          const form = new FormData(e.currentTarget);
          setBusy(true);
          setError("");
          try {
            if (workflow.data?.status !== "PUBLISHED")
              throw new Error("Xuất bản workflow trước");
            // Attachments need a ticket id. Create stopped, upload, then start so the first prompt includes files.
            const result =
              created ||
              (await send<{ ticket: Ticket; chat_url: string }>(
                `/workflows/${wid}/tickets`,
                {
                  title: form.get("title"),
                  description: form.get("description"),
                  auto_start: files.length ? false : autoStart,
                },
              ));
            setCreated(result);
            if (files.length) {
              const remaining = [...files];
              while (remaining.length) {
                const body = new FormData();
                body.append("file", remaining[0]);
                await apiFetch(`/tickets/${result.ticket.id}/attachments`, {
                  method: "POST",
                  body,
                });
                remaining.shift();
                setFiles([...remaining]);
              }
            }
            if (autoStart && (created || files.length)) {
              const latest = await apiFetch<Ticket>(
                `/tickets/${result.ticket.id}`,
              );
              if (latest.status === "OPEN")
                await send(`/tickets/${result.ticket.id}/start`);
            }
            await client.invalidateQueries({ queryKey: ["projects"] });
            await client.invalidateQueries({ queryKey: ["tickets"] });
            toast.success("Đã tạo ticket");
            onClose();
            router.push(
              result.chat_url ||
                `/projects/${pid}/workflows/${wid}/tickets/${result.ticket.id}`,
            );
          } catch (e) {
            setError((e as Error).message);
          } finally {
            setBusy(false);
          }
        }}
      >
        <label className="field">
          Tiêu đề
          <input name="title" required maxLength={200} disabled={!!created} />
        </label>
        <label className="field">
          Mô tả lỗi/yêu cầu
          <textarea name="description" disabled={!!created} />
        </label>
        <label className="field">
          Đính kèm file/ảnh (tối đa 5)
          <input
            type="file"
            multiple
            disabled={!!created}
            onChange={(e) => {
              const selected = [...(e.target.files || [])];
              if (selected.length > 5) {
                setError("Tối đa 5 file đính kèm.");
                e.target.value = "";
                return;
              }
              setFiles(selected);
            }}
          />
        </label>
        {files.map((file, i) => (
          <p key={`${file.name}-${i}`} className="text-xs text-stone-500">
            📎 {file.name}
            <button
              type="button"
              disabled={busy}
              className="ml-2 underline"
              onClick={() => setFiles(files.filter((_, index) => index !== i))}
            >
              Bỏ file
            </button>
          </p>
        ))}
        <label className="flex items-center gap-2 text-xs">
          <input
            type="checkbox"
            checked={!autoStart}
            onChange={(e) => setAutoStart(!e.target.checked)}
            disabled={!!created}
          />
          Chỉ tạo, chưa chạy
        </label>
        {error && (
          <p role="alert" className="error">
            {error}
            {created &&
              " Ticket đã được tạo; bấm tiếp tục để thử lại phần còn lại."}
          </p>
        )}
        <div className="flex justify-end gap-2">
          <button type="button" className="btn btn-light" onClick={onClose}>
            Huỷ
          </button>
          <button
            disabled={busy || workflow.data?.status !== "PUBLISHED"}
            className="btn btn-dark"
          >
            {busy
              ? "Đang tạo…"
              : created
                ? "Tiếp tục & mở chat"
                : "Tạo & mở chat"}
          </button>
        </div>
      </form>
    </Modal>
  );
}
