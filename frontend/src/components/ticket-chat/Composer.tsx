"use client";
import { useCallback, useEffect, useRef, useState } from "react";
import { Paperclip, ArrowUp } from "lucide-react";
import { toast } from "sonner";
import type { Agent } from "@/lib/types";
import { apiFetch } from "@/lib/api";
import { clientId } from "@/lib/client-id";
import { useChatPrefs } from "@/stores/chat-prefs";
import { useChatDrafts } from "@/stores/chat-drafts";
import { MentionPicker } from "./MentionPicker";
import { AttachmentTray } from "./AttachmentTray";
import type { Attachment, Waiting } from "./types";
const emptyFiles: import("./types").DraftFile[] = [];
export function Composer({
  tid,
  userId,
  slug,
  agents,
  waiting,
  disabled,
  sendDisabled = false,
  maxFiles,
  maxMb,
  onSend,
}: {
  tid: string;
  userId: string;
  slug: string;
  agents: Agent[];
  waiting: Waiting | null;
  disabled: boolean;
  sendDisabled?: boolean;
  maxFiles: number;
  maxMb: number;
  onSend: (text: string, files: Attachment[]) => Promise<void>;
}) {
  const key = `${userId}:${tid}`;
  const files = useChatDrafts((s) => s.files[key] || emptyFiles);
  const text = useChatDrafts((s) => s.text[key] || "");
  const setText = (value: string) =>
    useChatDrafts.getState().setText(key, value);
  const prefs = useChatPrefs();
  const current = agents.find((a) => a.id === prefs.agentId);
  const [picker, setPicker] = useState(false);
  const [autocomplete, setAutocomplete] = useState(false);
  const [dragging, setDragging] = useState(false);
  const [busy, setBusy] = useState(false);
  const input = useRef<HTMLTextAreaElement>(null);
  const choose = useRef<HTMLInputElement>(null);
  const openPicker = useCallback((open: boolean) => setPicker(open), []);
  useEffect(() => {
    if (waiting?.kind === "human_input") input.current?.focus();
  }, [waiting?.kind, waiting?.node_id]);
  const update = (
    fileKey: string,
    changes: Partial<import("./types").DraftFile>,
  ) => {
    const state = useChatDrafts.getState();
    state.setFiles(
      key,
      (state.files[key] || []).map((f) =>
        f.key === fileKey ? { ...f, ...changes } : f,
      ),
    );
  };
  async function remove(fileKey: string) {
    const state = useChatDrafts.getState();
    const file = state.files[key]?.find((f) => f.key === fileKey);
    if (file?.attachment) {
      try {
        await apiFetch(`/attachments/${file.attachment.id}`, {
          method: "DELETE",
        });
      } catch (e) {
        toast.error((e as Error).message);
        return;
      }
    }
    const latest = useChatDrafts.getState();
    latest.setFiles(
      key,
      (latest.files[key] || []).filter((f) => f.key !== fileKey),
    );
  }
  function addFiles(incoming: FileList | File[]) {
    if (disabled || sendDisabled || busy) return;
    const state = useChatDrafts.getState();
    const accepted = [];
    let count = (state.files[key] || []).length;
    for (const file of Array.from(incoming)) {
      if (count >= maxFiles) {
        toast.error(`Tối đa ${maxFiles} file mỗi tin nhắn`);
        break;
      }
      if (file.size > maxMb * 1024 * 1024) {
        toast.error(`${file.name} vượt quá ${maxMb}MB`);
        continue;
      }
      accepted.push({ key: clientId(), file, progress: 0 });
      count++;
    }
    state.setFiles(key, [...(state.files[key] || []), ...accepted]);
    for (const draft of accepted) {
      const xhr = new XMLHttpRequest();
      const form = new FormData();
      form.append("file", draft.file);
      xhr.open("POST", `/api/backend/tickets/${tid}/attachments`);
      xhr.upload.onprogress = (event) => {
        if (event.lengthComputable)
          update(draft.key, {
            progress: Math.round((event.loaded / event.total) * 100),
          });
      };
      xhr.onerror = () =>
        update(draft.key, { error: "Tải lên thất bại; gỡ để thử lại" });
      xhr.onload = () => {
        let data;
        try {
          data = JSON.parse(xhr.responseText);
        } catch {
          update(draft.key, { error: "Tải lên thất bại" });
          return;
        }
        if (xhr.status >= 200 && xhr.status < 300) {
          if (
            !(useChatDrafts.getState().files[key] || []).some(
              (f) => f.key === draft.key,
            )
          ) {
            void apiFetch(`/attachments/${data.id}`, {
              method: "DELETE",
            }).catch(() => {});
            return;
          }
          update(draft.key, { attachment: data, progress: 100 });
        } else
          update(draft.key, {
            error:
              typeof data.detail === "string"
                ? data.detail
                : data.detail?.detail || "Tệp không hợp lệ",
          });
      };
      xhr.send(form);
    }
  }
  async function submit() {
    if (
      disabled ||
      sendDisabled ||
      busy ||
      files.some((f) => !f.attachment) ||
      (!text.trim() && !files.length)
    )
      return;
    const value =
      current && !/@[\w-]+/.test(text)
        ? `${current.handle} ${text}`.trim()
        : text;
    setBusy(true);
    try {
      await onSend(
        value,
        files.flatMap((f) => (f.attachment ? [f.attachment] : [])),
      );
      const state = useChatDrafts.getState();
      state.setText(key, "");
      state.setFiles(key, []);
    } catch (e) {
      // The failed message owns this payload and exposes a retry action.
      // Keep any newer edits made while the request was in flight.
      const state = useChatDrafts.getState();
      if (state.text[key] === text) state.setText(key, "");
      state.setFiles(
        key,
        (state.files[key] || []).filter(
          (f) => !files.some((sent) => sent.key === f.key),
        ),
      );
      toast.error((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  return (
    <div
      data-testid="chat-composer"
      className={`relative rounded-xl border bg-white p-3 shadow-sm focus-within:border-stone-500 ${dragging ? "border-sky-400 ring-2 ring-sky-200" : "border-stone-300"}`}
      onDragOver={(e) => {
        e.preventDefault();
        if (!disabled) setDragging(true);
      }}
      onDragLeave={(e) => {
        if (!e.currentTarget.contains(e.relatedTarget as Node))
          setDragging(false);
      }}
      onDrop={(e) => {
        e.preventDefault();
        setDragging(false);
        addFiles(e.dataTransfer.files);
      }}
    >
      <AttachmentTray files={files} onRemove={(key) => void remove(key)} />
      <textarea
        ref={input}
        aria-label="Tin nhắn"
        rows={2}
        maxLength={100000}
        disabled={disabled || busy}
        className="w-full resize-none border-0 bg-transparent text-sm outline-none placeholder:text-stone-400 disabled:opacity-50"
        value={text}
        placeholder={`Nhắn tin vào #${slug}${current ? ` — mặc định gửi tới ${current.handle}...` : " (bấm nút @ để chọn agent)..."}`}
        onChange={(e) => {
          setText(e.target.value);
          const active = /(?:^|\s)@[\w-]*$/.test(e.target.value);
          setAutocomplete(active);
          if (active) setPicker(true);
        }}
        onPaste={(e) => {
          if (e.clipboardData.files.length) {
            e.preventDefault();
            addFiles(e.clipboardData.files);
          }
        }}
        onKeyDown={(e) => {
          if (
            e.key === "Enter" &&
            !e.shiftKey &&
            !e.nativeEvent.isComposing &&
            !picker
          ) {
            e.preventDefault();
            void submit();
          }
        }}
      />
      <div className="mt-2 flex items-center justify-between">
        <div className="flex items-center gap-1.5">
          <MentionPicker
            agents={agents}
            open={picker}
            onOpen={openPicker}
            disabled={disabled || busy}
            onPick={(agent) => {
              if (autocomplete) {
                setText(text.replace(/@[\w-]*$/, `${agent.handle} `));
                setAutocomplete(false);
              }
              input.current?.focus();
            }}
          />
          <button
            type="button"
            aria-label="Đính kèm file"
            disabled={disabled || busy}
            onClick={() => choose.current?.click()}
            className="rounded-lg p-1.5 text-stone-500 hover:bg-stone-100"
          >
            <Paperclip size={16} />
          </button>
          <input
            aria-label="Chọn tệp đính kèm"
            ref={choose}
            type="file"
            multiple
            hidden
            onChange={(e) => {
              if (e.target.files) addFiles(e.target.files);
              e.target.value = "";
            }}
          />
        </div>
        <button
          type="button"
          aria-label="Gửi tin nhắn"
          disabled={
            disabled ||
            sendDisabled ||
            busy ||
            files.some((f) => !f.attachment) ||
            (!text.trim() && !files.length)
          }
          onClick={() => void submit()}
          className="rounded-full bg-stone-900 p-1.5 text-white disabled:bg-stone-300"
        >
          <ArrowUp size={17} />
        </button>
      </div>
    </div>
  );
}
