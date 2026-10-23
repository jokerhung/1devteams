"use client";
import { useState } from "react";
import { useRouter } from "next/navigation";
import { useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { send } from "@/lib/api";
import type { Project, Workspace } from "@/lib/types";
import { Modal } from "./primitives";
import { WorkspacePathField } from "./workspace-path-field";
export function ProjectDialog({ onClose }: { onClose: () => void }) {
  const router = useRouter();
  const client = useQueryClient();
  const [busy, setBusy] = useState(false);
  const [path, setPath] = useState("");
  const [branchOverride, setBranchOverride] = useState<string | null>(null);
  const [validation, setValidation] = useState<{
    path: string;
    result: Workspace;
  } | null>(null);
  const [checking, setChecking] = useState(false);
  const [error, setError] = useState("");
  async function validate(value: string) {
    if (!value.trim()) return;
    setChecking(true);
    try {
      const result = await send<Workspace>("/projects/validate-workspace", {
        path: value,
      });
      setValidation({ path: value, result });
      return result;
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setChecking(false);
    }
  }
  const current = validation?.path === path ? validation.result : null;
  const detectedBranch =
    current?.current_branch === "HEAD" ? "" : current?.current_branch || "";
  return (
    <Modal title="Tạo Project" onClose={onClose}>
      <form
        className="space-y-4"
        onSubmit={async (e) => {
          e.preventDefault();
          const form = new FormData(e.currentTarget);
          setBusy(true);
          setError("");
          try {
            const result = current || (await validate(path));
            if (
              !result?.exists ||
              !result.is_git_repo ||
              !result.within_allowed_roots
            )
              throw new Error("Chọn thư mục Git trong thư mục cho phép.");
            const project = await send<Project>(
              "/projects",
              Object.fromEntries(form),
            );
            localStorage.setItem(`sidebar.open.${project.id}`, "true");
            localStorage.setItem("lastProjectId", project.id);
            await client.invalidateQueries({ queryKey: ["projects"] });
            toast.success(
              "Đã tạo project trống. Thêm AI Team, workflow và ticket sau.",
            );
            onClose();
            router.push(`/projects/${project.id}`);
          } catch (e) {
            setError((e as Error).message);
          } finally {
            setBusy(false);
          }
        }}
      >
        <label className="field">
          Tên project
          <input name="name" required maxLength={200} autoFocus />
        </label>
        <WorkspacePathField
          label="Đường dẫn thư mục local (ACP Working Directory)"
          value={path}
          onChange={(value) => {
            setPath(value);
            setBranchOverride(null);
          }}
          onSelect={(value) => {
            void validate(value);
          }}
          onBlur={() => validate(path)}
        />
        {checking && (
          <p className="text-xs text-stone-500">Đang kiểm tra thư mục…</p>
        )}
        {current && (
          <div role="status" className="space-y-1 text-xs">
            <p className={current.exists ? "text-emerald-700" : "error"}>
              {current.exists ? "✔ Thư mục tồn tại" : "✘ Thư mục không tồn tại"}
            </p>
            <p className={current.is_git_repo ? "text-emerald-700" : "error"}>
              {current.is_git_repo ? "✔ Git repo" : "✘ Không phải Git repo"}
            </p>
            {!current.within_allowed_roots && (
              <p className="error">✘ Ngoài thư mục cho phép</p>
            )}
            {current.dirty_files_count > 0 && (
              <p className="text-amber-700">
                ⚠ {current.dirty_files_count} file đang thay đổi
              </p>
            )}
          </div>
        )}
        <label className="field">
          Nhánh Git
          <input
            name="default_branch"
            value={branchOverride ?? detectedBranch}
            onChange={(e) => setBranchOverride(e.target.value)}
            placeholder="Nhánh hiện tại của thư mục Git"
            required
          />
        </label>
        {current?.is_git_repo && !detectedBranch && (
          <p className="text-xs text-amber-700">
            Không xác định được nhánh hiện tại. Hãy nhập nhánh Git để tiếp tục.
          </p>
        )}
        {error && (
          <p role="alert" className="error">
            {error}
          </p>
        )}
        <div className="flex justify-end gap-2 pt-3">
          <button type="button" className="btn btn-light" onClick={onClose}>
            Huỷ
          </button>
          <button disabled={busy || checking} className="btn btn-dark">
            {busy ? "Đang tạo…" : "Tạo project"}
          </button>
        </div>
      </form>
    </Modal>
  );
}
