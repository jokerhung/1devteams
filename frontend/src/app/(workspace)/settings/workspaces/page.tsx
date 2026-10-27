"use client";

import { useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { FolderOpen, LoaderCircle, Plus, Save, Trash2 } from "lucide-react";
import { apiFetch } from "@/lib/api";

type WorkspaceRoots = { roots: string[] };
const queryKey = ["settings", "workspaces"];

export default function WorkspaceSettingsPage() {
  const client = useQueryClient();
  const settings = useQuery({
    queryKey,
    queryFn: () => apiFetch<WorkspaceRoots>("/settings/workspaces"),
    retry: false,
  });
  const [draft, setDraft] = useState<string[] | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [saved, setSaved] = useState(false);
  const roots = draft ?? settings.data?.roots ?? [];
  const changed =
    JSON.stringify(roots) !== JSON.stringify(settings.data?.roots);

  function edit(value: string[]) {
    setDraft(value);
    setSaved(false);
    setError("");
  }
  async function save() {
    if (busy) return;
    setBusy(true);
    setError("");
    setSaved(false);
    try {
      const result = await apiFetch<WorkspaceRoots>("/settings/workspaces", {
        method: "PUT",
        body: JSON.stringify({ roots }),
      });
      client.setQueryData(queryKey, result);
      setDraft(null);
      setSaved(true);
    } catch (error) {
      setError((error as Error).message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="space-y-5">
      <div>
        <h2 className="flex items-center gap-2 text-base font-semibold">
          <FolderOpen size={18} />
          Thư mục được phép truy cập
        </h2>
        <p className="mt-2 text-sm leading-6 text-stone-500">
          Cho phép chọn workspace trong các thư mục này và thư mục con trên máy
          chạy backend. Chỉ quản trị viên được thay đổi.
        </p>
      </div>
      {settings.isPending && (
        <p role="status" className="text-sm text-stone-500">
          Đang tải cấu hình…
        </p>
      )}
      {(error || settings.error) && (
        <p role="alert" className="error">
          {error || settings.error?.message}
        </p>
      )}
      {settings.data && (
        <form
          className="space-y-4"
          onSubmit={(event) => {
            event.preventDefault();
            void save();
          }}
        >
          <div className="space-y-3">
            {roots.map((root, index) => (
              <div key={index} className="flex items-center gap-2">
                <label className="min-w-0 flex-1">
                  <span className="sr-only">Thư mục {index + 1}</span>
                  <input
                    className="inp font-mono text-sm"
                    value={root}
                    placeholder="C:\hungnm\artemis"
                    maxLength={4000}
                    disabled={busy}
                    onChange={(event) =>
                      edit(
                        roots.map((value, i) =>
                          i === index ? event.target.value : value,
                        ),
                      )
                    }
                  />
                </label>
                <button
                  type="button"
                  className="btn btn-light shrink-0 !p-2"
                  aria-label={`Xóa thư mục ${index + 1}`}
                  disabled={busy}
                  onClick={() => edit(roots.filter((_, i) => i !== index))}
                >
                  <Trash2 size={16} />
                </button>
              </div>
            ))}
          </div>
          <button
            type="button"
            className="btn btn-light gap-2"
            disabled={busy || roots.length >= 100}
            onClick={() => edit([...roots, ""])}
          >
            <Plus size={15} />
            Thêm thư mục
          </button>
          <p className="text-xs leading-5 text-stone-500">
            Nhập đường dẫn tuyệt đối đến thư mục đã tồn tại, ví dụ
            C:\hungnm\artemis. Cấu hình được lưu và áp dụng ngay, không cần khởi
            động lại.
          </p>
          <div className="flex flex-wrap items-center gap-3 border-t border-stone-200 pt-4">
            <button
              type="submit"
              className="btn btn-dark gap-2"
              disabled={
                busy ||
                !changed ||
                !roots.length ||
                roots.some((root) => !root.trim())
              }
            >
              {busy ? (
                <LoaderCircle size={15} className="animate-spin" />
              ) : (
                <Save size={15} />
              )}
              Lưu cấu hình
            </button>
            {saved && (
              <p role="status" className="text-sm text-emerald-700">
                Đã lưu và áp dụng cấu hình thư mục.
              </p>
            )}
          </div>
        </form>
      )}
    </section>
  );
}
