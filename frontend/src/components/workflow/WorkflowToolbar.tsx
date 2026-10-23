"use client";
import Link from "next/link";
import type { Workflow, Project } from "@/lib/types";
import { templateOptions, type TemplateId } from "./templates";
export function WorkflowToolbar({
  workflow: w,
  project,
  dirty,
  valid,
  busy,
  archived,
  view,
  lastSaved,
  canUndo,
  canRedo,
  onUndo,
  onRedo,
  onSave,
  onValidate,
  onPublish,
  onLayout,
  onTemplate,
  onView,
}: {
  workflow: Workflow;
  project: Project;
  dirty: boolean;
  valid: boolean;
  busy: boolean;
  archived: boolean;
  view: string;
  lastSaved: string;
  canUndo: boolean;
  canRedo: boolean;
  onUndo: () => void;
  onRedo: () => void;
  onSave: () => void;
  onValidate: () => void;
  onPublish: () => void;
  onLayout: () => void;
  onTemplate: (template: TemplateId) => void;
  onView: (view: "canvas" | "pipeline") => void;
}) {
  return (
    <header className="space-y-3 border-b border-stone-200 bg-white p-3">
      <div className="flex flex-wrap items-center gap-2 text-xs">
        <Link
          className="text-stone-500 hover:underline"
          href={`/projects/${project.id}`}
        >
          {project.name}
        </Link>
        <span>/</span>
        <Link
          className="font-semibold hover:underline"
          href={`/projects/${project.id}/workflows/${w.id}`}
        >
          {w.name} ({w.ticket_prefix})
        </Link>
        <span className="badge">Nháp v{w.current_version}</span>
        <span className="badge">
          {w.published_version
            ? `Xuất bản v${w.published_version}`
            : "Chưa xuất bản"}
        </span>
        {archived ? (
          <span className="badge">Đã lưu trữ · chỉ đọc</span>
        ) : dirty ? (
          <span className="text-amber-700">Chưa lưu</span>
        ) : (
          <span className="text-stone-400">
            Đã lưu {new Date(lastSaved).toLocaleTimeString("vi-VN")}
          </span>
        )}
        {w.current_version > (w.published_version || 0) && (
          <span className="badge !bg-amber-50 !text-amber-800">
            Có thay đổi chưa xuất bản
          </span>
        )}
      </div>
      <div className="flex flex-wrap items-center gap-2">
        <select
          aria-label="Tải mẫu workflow"
          className="inp !w-auto !py-1.5"
          disabled={archived || busy}
          value=""
          onChange={(e) => onTemplate(e.target.value as TemplateId)}
        >
          <option value="" disabled>
            Mẫu workflow…
          </option>
          {templateOptions.map((t) => (
            <option value={t.id} key={t.id}>
              {t.name}
            </option>
          ))}
        </select>
        <button
          className="btn btn-light"
          disabled={archived || busy || !canUndo}
          onClick={onUndo}
        >
          Hoàn tác
        </button>
        <button
          className="btn btn-light"
          disabled={archived || busy || !canRedo}
          onClick={onRedo}
        >
          Làm lại
        </button>
        <button
          className="btn btn-light"
          disabled={archived || busy}
          onClick={onLayout}
        >
          Sắp xếp
        </button>
        <button className="btn btn-light" disabled={busy} onClick={onValidate}>
          Kiểm tra
        </button>
        <span
          className={`text-[11px] ${valid ? "text-emerald-700" : "text-red-700"}`}
        >
          {valid ? "✓ Hợp lệ" : "⚠ Cần sửa lỗi"}
        </span>
        <div
          className="ml-auto flex gap-1 rounded-lg bg-stone-100 p-1"
          aria-label="Chế độ xem"
        >
          <button
            className={`rounded px-2 py-1 text-xs ${view === "canvas" ? "bg-white shadow-sm" : ""}`}
            aria-pressed={view === "canvas"}
            onClick={() => onView("canvas")}
          >
            Canvas
          </button>
          <button
            className={`rounded px-2 py-1 text-xs ${view === "pipeline" ? "bg-white shadow-sm" : ""}`}
            aria-pressed={view === "pipeline"}
            onClick={() => onView("pipeline")}
          >
            Pipeline
          </button>
        </div>
        <button
          className="btn btn-light"
          disabled={archived || busy}
          onClick={onSave}
        >
          Lưu
        </button>
        <button
          className="btn btn-dark"
          title={
            dirty
              ? "Lưu trước khi xuất bản"
              : !valid
                ? "Sửa lỗi trước khi xuất bản"
                : "Xuất bản workflow"
          }
          disabled={archived || busy || dirty || !valid}
          onClick={onPublish}
        >
          Xuất bản
        </button>
      </div>
    </header>
  );
}
