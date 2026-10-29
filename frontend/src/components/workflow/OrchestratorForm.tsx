"use client";

import { useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { apiFetch, send } from "@/lib/api";
import { keys } from "@/lib/query-keys";
import type { Agent, Workflow } from "@/lib/types";
import {
  ErrorState,
  Loading,
  PageHeader,
} from "@/components/ui-app/primitives";

export function OrchestratorForm({
  pid,
  workflow,
}: {
  pid: string;
  workflow?: Workflow;
}) {
  const router = useRouter(),
    client = useQueryClient();
  const existing = workflow?.graph.orchestrator;
  const [name, setName] = useState(workflow?.name || "Orchestrator");
  const [prefix, setPrefix] = useState(workflow?.ticket_prefix || "ORCH");
  const [coordinator, setCoordinator] = useState(
    existing?.coordinator_agent_id || "",
  );
  const [instructions, setInstructions] = useState(
    existing?.instructions || "",
  );
  const [rounds, setRounds] = useState(existing?.max_rounds || 20);
  const [busy, setBusy] = useState(false),
    [error, setError] = useState("");
  const [draftId, setDraftId] = useState<string | null>(null);
  const agents = useQuery({
    queryKey: keys.effective(pid),
    queryFn: () => apiFetch<Agent[]>(`/projects/${pid}/effective-agents`),
  });
  if (agents.isPending) return <Loading />;
  if (!agents.data) return <ErrorState error={agents.error} />;
  const active = agents.data.filter(
    (a) => a.is_active && a.role_key !== "WORKFLOW",
  );
  const workers = active.filter((a) => a.id !== coordinator);
  return (
    <>
      <PageHeader
        title={workflow ? "Cấu hình Orchestrator" : "Tạo Orchestrator"}
        description="Chọn agent điều phối và nhập instruction. Agent tự giao việc cho các thành viên trong project."
      />
      <form
        className="max-w-2xl space-y-4"
        onSubmit={async (e) => {
          e.preventDefault();
          setBusy(true);
          setError("");
          try {
            const orchestrator = {
              coordinator_agent_id: coordinator,
              instructions: instructions.trim(),
              max_rounds: rounds,
            };
            let result: Workflow;
            if (workflow || draftId) {
              result = await send<Workflow>(
                `/workflows/${workflow?.id || draftId}/orchestrator`,
                orchestrator,
                "PUT",
              );
            } else {
              result = await send<Workflow>(`/projects/${pid}/workflows`, {
                name: name.trim(),
                ticket_prefix: prefix,
                icon: "🧭",
                orchestrator,
              });
              setDraftId(result.id);
            }
            await send(`/workflows/${result.id}/publish`, {});
            await client.invalidateQueries({ queryKey: ["projects"] });
            await client.invalidateQueries({
              queryKey: keys.workflow(result.id),
            });
            toast.success(
              "Đã xuất bản Orchestrator. Có thể tạo ticket để bắt đầu.",
            );
            router.push(`/projects/${pid}/workflows/${result.id}`);
          } catch (err) {
            setError((err as Error).message);
          } finally {
            setBusy(false);
          }
        }}
      >
        {!workflow && (
          <fieldset disabled={!!draftId} className="space-y-4">
            <label className="field">
              Tên Orchestrator
              <input
                required
                maxLength={200}
                value={name}
                onChange={(e) => setName(e.target.value)}
              />
            </label>
            <label className="field">
              Prefix ticket
              <input
                required
                pattern="[A-Z]{2,10}"
                maxLength={10}
                value={prefix}
                onChange={(e) => setPrefix(e.target.value.toUpperCase())}
              />
            </label>
          </fieldset>
        )}
        <label className="field">
          Agent điều phối
          <select
            required
            value={coordinator}
            onChange={(e) => setCoordinator(e.target.value)}
          >
            <option value="">Chọn agent</option>
            {active.map((a) => (
              <option key={a.id} value={a.id}>
                {a.handle} · {a.display_name}
              </option>
            ))}
          </select>
        </label>
        <label className="field">
          Instruction
          <textarea
            required
            rows={9}
            maxLength={20000}
            value={instructions}
            onChange={(e) => setInstructions(e.target.value)}
            placeholder="Ví dụ: BA làm rõ yêu cầu → Planner lên kế hoạch → Developer triển khai → Tester kiểm thử. Nếu FAIL giao Developer sửa; nếu PASS tổng kết bàn giao."
          />
        </label>
        <label className="field">
          Số lượt điều phối trước khi hỏi người dùng
          <input
            type="number"
            min={1}
            max={40}
            required
            value={rounds}
            onChange={(e) => setRounds(Number(e.target.value))}
          />
        </label>
        <section className="rounded-xl border p-4 text-sm">
          <h2 className="font-semibold">Agent thực hiện</h2>
          <p className="mt-2">
            {workers.map((a) => a.handle).join(", ") ||
              "Cần thêm ít nhất một agent thực hiện vào project."}
          </p>
          <Link className="underline" href={`/projects/${pid}/members`}>
            Quản lý thành viên & AI Team
          </Link>
        </section>
        {workflow && (
          <p className="text-xs text-stone-500">
            Thay đổi áp dụng cho ticket mới. Ticket hiện có tiếp tục dùng phiên
            bản đã lưu.
          </p>
        )}
        {error && (
          <p role="alert" className="error">
            {error}
          </p>
        )}
        <div className="flex gap-2">
          <Link className="btn btn-light" href={`/projects/${pid}`}>
            Hủy
          </Link>
          <button
            className="btn btn-dark"
            disabled={
              busy ||
              !coordinator ||
              !instructions.trim() ||
              workers.length === 0
            }
          >
            {busy ? "Đang lưu…" : "Lưu & xuất bản"}
          </button>
        </div>
      </form>
    </>
  );
}
