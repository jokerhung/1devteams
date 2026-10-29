"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { useQueryClient } from "@tanstack/react-query";
import { LoaderCircle } from "lucide-react";
import { toast } from "sonner";
import { send } from "@/lib/api";
import { Modal } from "@/components/ui-app/primitives";

export function CreateWorkflowTemplateDialog({
  templates,
  onClose,
}: {
  templates: { id: string; name: string }[];
  onClose: () => void;
}) {
  const router = useRouter();
  const client = useQueryClient();
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [source, setSource] = useState("blank");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  return (
    <Modal
      title="Tạo template Workflow"
      onClose={() => {
        if (!busy) onClose();
      }}
    >
      <form
        className="space-y-4"
        onSubmit={async (event) => {
          event.preventDefault();
          setBusy(true);
          setError("");
          try {
            const result = await send<{ id: string }>("/workflow-templates", {
              name: name.trim(),
              description,
              source_template: source,
            });
            await client.invalidateQueries({
              queryKey: ["workflow-templates"],
            });
            toast.success("Đã tạo template Workflow");
            onClose();
            router.push(`/templates/${result.id}?edit=1`);
          } catch (err) {
            setError((err as Error).message);
          } finally {
            setBusy(false);
          }
        }}
      >
        <fieldset disabled={busy} className="space-y-4">
          <label className="field">
            Tên template
            <input
              autoFocus
              required
              maxLength={100}
              value={name}
              onChange={(e) => setName(e.target.value)}
            />
          </label>
          <label className="field">
            Mô tả
            <textarea
              maxLength={2000}
              value={description}
              onChange={(e) => setDescription(e.target.value)}
            />
          </label>
          <label className="field">
            Bắt đầu từ
            <select
              required
              value={source}
              onChange={(e) => setSource(e.target.value)}
            >
              {templates.map((template) => (
                <option key={template.id} value={template.id}>
                  {template.name}
                </option>
              ))}
            </select>
          </label>
          <p className="text-xs text-stone-500">
            Template mới là bản riêng. Bạn có thể chỉnh các bước và kết nối
            trong canvas sau khi tạo.
          </p>
          {error && (
            <p role="alert" className="error">
              {error}
            </p>
          )}
          <div className="flex justify-end gap-2">
            <button type="button" className="btn btn-light" onClick={onClose}>
              Hủy
            </button>
            <button
              className="btn btn-dark"
              disabled={
                busy || !name.trim() || !templates.some((t) => t.id === source)
              }
              aria-busy={busy}
            >
              {busy && (
                <LoaderCircle
                  size={14}
                  className="animate-spin"
                  aria-hidden="true"
                />
              )}
              {busy ? "Đang tạo…" : "Tạo template"}
            </button>
          </div>
        </fieldset>
      </form>
    </Modal>
  );
}
