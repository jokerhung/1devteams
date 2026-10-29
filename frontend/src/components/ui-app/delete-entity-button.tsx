"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { useQueryClient } from "@tanstack/react-query";
import { LoaderCircle, Trash2 } from "lucide-react";
import { toast } from "sonner";
import { apiFetch, send } from "@/lib/api";
import { ConfirmDialog } from "./primitives";

type Preview = { ticket_count: number; workflow_count: number };

export function DeleteEntityButton({
  kind,
  id,
  name,
  redirectTo,
}: {
  kind: "project" | "workflow" | "ticket";
  id: string;
  name: string;
  redirectTo?: string;
}) {
  const router = useRouter();
  const client = useQueryClient();
  const [preview, setPreview] = useState<Preview | null>(null);
  const [loading, setLoading] = useState(false);
  const path = `/${kind}s/${id}`;
  return (
    <>
      <button
        type="button"
        className="btn btn-light shrink-0 text-red-700"
        aria-label={`Xóa ${kind} ${name}`}
        title={`Xóa vĩnh viễn ${kind}`}
        disabled={loading}
        onClick={async () => {
          setLoading(true);
          try {
            setPreview(
              kind === "ticket"
                ? { ticket_count: 0, workflow_count: 0 }
                : await apiFetch<Preview>(`${path}/deletion-preview`),
            );
          } catch (error) {
            toast.error((error as Error).message);
          } finally {
            setLoading(false);
          }
        }}
      >
        {loading ? (
          <LoaderCircle size={14} className="animate-spin" />
        ) : (
          <Trash2 size={14} />
        )}
      </button>
      {preview && (
        <ConfirmDialog
          title={`Xóa vĩnh viễn ${kind}?`}
          busyLabel="Đang xóa…"
          onClose={() => setPreview(null)}
          onConfirm={async () => {
            await send(
              `${path}${kind === "ticket" ? "" : "?cascade=true"}`,
              undefined,
              "DELETE",
            );
            if (
              kind === "project" &&
              localStorage.getItem("lastProjectId") === id
            ) {
              localStorage.removeItem("lastProjectId");
            }
            setPreview(null);
            if (redirectTo) router.replace(redirectTo);
            await Promise.all(
              ["projects", "workflows", "tickets", "notifications"].map((key) =>
                client.invalidateQueries({ queryKey: [key] }),
              ),
            );
            toast.success(`Đã xóa ${kind}`);
          }}
        >
          <p>
            Bạn có đồng ý xóa vĩnh viễn <strong>{name}</strong>?
          </p>
          {kind === "project" &&
            (preview.workflow_count > 0 || preview.ticket_count > 0) && (
              <p className="mt-3">
                Xóa kèm toàn bộ {preview.workflow_count} workflow và{" "}
                {preview.ticket_count} ticket trong project này.
              </p>
            )}
          {kind === "workflow" && preview.ticket_count > 0 && (
            <p className="mt-3">
              Xóa kèm toàn bộ {preview.ticket_count} ticket trong workflow này.
            </p>
          )}
          <p className="mt-3 text-red-700">
            Dữ liệu và lịch sử chat sẽ bị xóa hẳn, không thể khôi phục.
          </p>
        </ConfirmDialog>
      )}
    </>
  );
}
