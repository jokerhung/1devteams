"use client";
import { useId, useRef, useState } from "react";
import { Dialog } from "@base-ui/react/dialog";
import { X, Bot, Plus, LoaderCircle } from "lucide-react";
import { toast } from "sonner";
import { apiFetch, assetUrl } from "@/lib/api";
import type { Agent, Permission } from "@/lib/types";
export const emojis = [
  "🤖",
  "🐝",
  "🛠️",
  "🧪",
  "🚀",
  "🛡️",
  "🦾",
  "🧠",
  "🔍",
  "📝",
  "🧑‍💻",
  "👾",
  "🦉",
  "🦊",
  "🐙",
  "🐞",
  "⚙️",
  "🔒",
  "📊",
  "🎯",
  "⚡",
  "🌟",
  "🧩",
  "🏗️",
];
export const colors: Record<string, string> = {
  sky: "bg-sky-100 border-sky-300 text-sky-800",
  amber: "bg-amber-100 border-amber-300 text-amber-800",
  emerald: "bg-emerald-100 border-emerald-300 text-emerald-800",
  purple: "bg-purple-100 border-purple-300 text-purple-800",
  stone: "bg-stone-100 border-stone-300 text-stone-800",
  rose: "bg-rose-100 border-rose-300 text-rose-800",
};
export const agentColorClasses = (color: string) =>
  colors[color] || colors.stone;
export function TagInput({
  label,
  values,
  onChange,
}: {
  label: string;
  values: string[];
  onChange: (values: string[]) => void;
}) {
  const [draft, setDraft] = useState("");
  const add = () => {
    if (draft.trim()) onChange([...new Set([...values, draft.trim()])]);
    setDraft("");
  };
  return (
    <div>
      <label className="field">
        {label}
        <span className="flex gap-2">
          <input
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter") {
                e.preventDefault();
                add();
              }
            }}
          />
          <button className="btn btn-light" type="button" onClick={add}>
            Thêm lệnh
          </button>
        </span>
      </label>
      <div className="mt-2 flex flex-wrap gap-1">
        {values.map((value) => (
          <span className="pill font-mono" key={value}>
            {value}
            <button
              type="button"
              aria-label={`Bỏ lệnh ${value}`}
              onClick={() => onChange(values.filter((v) => v !== value))}
            >
              <X size={12} />
            </button>
          </span>
        ))}
      </div>
    </div>
  );
}
export function Logo({
  entity,
  size = 32,
}: {
  entity: { icon?: string; logo_url?: string | null };
  size?: number;
}) {
  // Authenticated assets use the same-origin cookie proxy.
  return entity.logo_url ? (
    // eslint-disable-next-line @next/next/no-img-element
    <img
      alt="Logo"
      src={assetUrl(entity.logo_url)}
      width={size}
      height={size}
      className="rounded-lg object-cover"
      style={{ width: size, height: size }}
    />
  ) : (
    <span
      className="inline-flex shrink-0 items-center justify-center"
      style={{ width: size, height: size, fontSize: size * 0.6 }}
      aria-hidden
    >
      {entity.icon || "🤖"}
    </span>
  );
}
export function AgentAvatar({ agent }: { agent: Agent }) {
  return (
    <span
      className={`inline-flex rounded-full border ${agentColorClasses(agent.color)}`}
    >
      <Logo entity={agent} />
    </span>
  );
}
export function AgentPill({
  agent,
  onMention,
}: {
  agent: Pick<Agent, "handle" | "icon" | "logo_url">;
  onMention?: (handle: string) => void;
}) {
  return (
    <button
      type="button"
      className="pill"
      onClick={() => onMention?.(agent.handle)}
    >
      <Logo entity={agent} size={16} />
      {agent.handle}
    </button>
  );
}
export function UserAvatar({ name }: { name: string }) {
  return (
    <span className="flex size-8 shrink-0 items-center justify-center rounded-full bg-stone-800 text-xs font-semibold text-white">
      {name
        .split(" ")
        .map((n) => n[0])
        .slice(0, 2)
        .join("")
        .toUpperCase()}
    </span>
  );
}
export const statuses: Record<string, string> = {
  OPEN: "Mới",
  RUNNING: "Đang chạy",
  WAITING_USER_INPUT: "Chờ trả lời",
  WAITING_USER_CONFIRM: "Chờ duyệt",
  COMPLETED: "Đã xong",
  FAILED: "Lỗi",
  CANCELLED: "Đã huỷ",
};
export function StatusBadge({ status }: { status: string }) {
  return (
    <span
      className={`badge ${status.startsWith("WAITING") ? "!bg-amber-100 !text-amber-800" : status === "FAILED" ? "!bg-red-50 !text-red-700" : status === "COMPLETED" ? "!bg-emerald-50 !text-emerald-700" : ""}`}
    >
      {statuses[status] || status}
    </span>
  );
}
export function RuntimeBadge({ runtime }: { runtime: string }) {
  return (
    <span
      className={`badge font-mono ${runtime === "openai-api" ? "!bg-sky-100 !text-sky-800" : ""}`}
    >
      {runtime === "claude-code"
        ? "Claude Code"
        : runtime === "codex"
          ? "Codex"
          : "OpenAI Custom"}
    </span>
  );
}
export function PermissionBadges({ profile }: { profile: Permission }) {
  return (
    <span className="inline-flex flex-wrap gap-1">
      <span className="badge">
        {profile.allow_write ? "Read/Write" : "Read-only"}
      </span>
      {profile.allow_terminal && <span className="badge">Run Test</span>}
      {profile.can_git_release && <span className="badge">Git Push</span>}
    </span>
  );
}
export function PageHeader({
  title,
  description,
  children,
}: {
  title: string;
  description?: string;
  children?: React.ReactNode;
}) {
  return (
    <header className="mb-6 flex flex-wrap items-start justify-between gap-3 border-b border-stone-200 pb-4">
      <div>
        <h1 className="text-base font-bold">{title}</h1>
        {description && (
          <p className="mt-1 max-w-2xl text-xs leading-relaxed text-stone-500">
            {description}
          </p>
        )}
      </div>
      <div className="flex flex-wrap gap-2">{children}</div>
    </header>
  );
}
export function EmptyState({
  children,
  action,
}: {
  children: React.ReactNode;
  action?: React.ReactNode;
}) {
  return (
    <div className="rounded-xl border border-dashed border-stone-200 bg-stone-50/50 px-6 py-12 text-center">
      <Bot className="mx-auto mb-3 size-7 text-stone-400" />
      <p className="mx-auto mb-4 max-w-md text-xs leading-relaxed text-stone-500">
        {children}
      </p>
      {action}
    </div>
  );
}
export function Loading() {
  return (
    <p
      role="status"
      className="flex items-center gap-2 py-8 text-xs text-stone-500"
    >
      <LoaderCircle className="size-4 animate-spin" />
      Đang tải…
    </p>
  );
}
export function ErrorState({ error }: { error: Error | null }) {
  return error ? (
    <p role="alert" className="error my-4 rounded-lg bg-red-50 p-3">
      {error.message}
    </p>
  ) : null;
}
export function Modal({
  title,
  children,
  onClose,
  wide = false,
}: {
  title: string;
  children: React.ReactNode;
  onClose: () => void;
  wide?: boolean;
}) {
  return (
    <Dialog.Root
      open
      onOpenChange={(open) => {
        if (!open) onClose();
      }}
    >
      <Dialog.Portal>
        <Dialog.Backdrop className="fixed inset-0 z-40 bg-stone-900/25 backdrop-blur-[2px]" />
        <Dialog.Popup
          className={`fixed top-1/2 left-1/2 z-50 max-h-[90dvh] ${wide ? "w-[min(1024px,calc(100vw-32px))]" : "w-[min(640px,calc(100vw-32px))]"} -translate-x-1/2 -translate-y-1/2 overflow-y-auto rounded-2xl border border-stone-200 bg-white p-6 shadow-xl`}
        >
          <div className="mb-5 flex items-center justify-between">
            <Dialog.Title className="text-base font-bold">{title}</Dialog.Title>
            <Dialog.Close aria-label="Đóng" className="rounded p-1">
              <X size={18} />
            </Dialog.Close>
          </div>
          {children}
        </Dialog.Popup>
      </Dialog.Portal>
    </Dialog.Root>
  );
}
export function ConfirmDialog({
  title,
  children,
  onConfirm,
  onClose,
}: {
  title: string;
  children: React.ReactNode;
  onConfirm: () => Promise<void>;
  onClose: () => void;
}) {
  const [busy, setBusy] = useState(false);
  return (
    <Modal title={title} onClose={onClose}>
      <div className="text-sm">{children}</div>
      <div className="mt-6 flex justify-end gap-2">
        <button className="btn btn-light" onClick={onClose}>
          Huỷ
        </button>
        <button
          disabled={busy}
          className="btn btn-dark"
          onClick={async () => {
            setBusy(true);
            try {
              await onConfirm();
              onClose();
            } catch (e) {
              toast.error((e as Error).message);
            } finally {
              setBusy(false);
            }
          }}
        >
          Xác nhận
        </button>
      </div>
    </Modal>
  );
}
export function LogoPicker({
  icon,
  logo_url,
  onChange,
}: {
  icon: string;
  logo_url: string | null;
  onChange: (icon: string, url: string | null) => void;
}) {
  const ref = useRef<HTMLInputElement>(null);
  const id = useId();
  const [busy, setBusy] = useState(false);
  return (
    <fieldset className="space-y-3">
      <legend className="mb-2 text-xs font-medium text-stone-600">Logo</legend>
      <div className="flex items-center gap-3">
        <span className="rounded-xl border border-stone-200 bg-stone-50">
          <Logo entity={{ icon, logo_url }} size={48} />
        </span>
        <button
          type="button"
          disabled={busy}
          onClick={() => ref.current?.click()}
          className="btn btn-light"
        >
          <Plus size={14} />
          {busy ? "Đang tải…" : "Tải ảnh lên"}
        </button>
        <span className="text-[11px] text-stone-400">
          PNG/JPG/WebP · ≤ 300 KB
        </span>
      </div>
      <input
        id={id}
        ref={ref}
        aria-label="Tải logo"
        type="file"
        accept="image/png,image/jpeg,image/webp"
        className="sr-only"
        onChange={async (e) => {
          const file = e.target.files?.[0];
          e.target.value = "";
          if (!file) return;
          if (file.size > 300 * 1024) {
            toast.error("Logo tối đa 300KB");
            return;
          }
          if (!["image/png", "image/jpeg", "image/webp"].includes(file.type)) {
            toast.error("Logo phải là ảnh PNG/JPG/WebP");
            return;
          }
          const body = new FormData();
          body.append("file", file);
          setBusy(true);
          try {
            const result = await apiFetch<{ logo_url: string }>(
              "/assets/logo",
              { method: "POST", body },
            );
            onChange(icon, result.logo_url);
          } catch (e) {
            toast.error((e as Error).message);
          } finally {
            setBusy(false);
          }
        }}
      />
      <div className="grid grid-cols-12 gap-1">
        {emojis.map((emoji) => (
          <button
            type="button"
            key={emoji}
            aria-label={`Logo ${emoji}`}
            aria-pressed={!logo_url && icon === emoji}
            onClick={() => onChange(emoji, null)}
            className={`rounded-md p-1 text-lg hover:bg-stone-100 ${!logo_url && icon === emoji ? "bg-stone-200 ring-1 ring-stone-400" : ""}`}
          >
            {emoji}
          </button>
        ))}
      </div>
    </fieldset>
  );
}
