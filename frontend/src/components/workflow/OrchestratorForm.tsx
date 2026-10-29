"use client";

import { useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { apiFetch, send } from "@/lib/api";
import { keys } from "@/lib/query-keys";
import type {
  Agent,
  Workflow,
  OrchestratorTemplate,
  OrchestratorWorker,
} from "@/lib/types";
import {
  ErrorState,
  Loading,
  PageHeader,
} from "@/components/ui-app/primitives";
import { Tabs, TabsList, TabsTrigger, TabsContent } from "@/components/ui/tabs";

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
  const [source, setSource] = useState("manual");
  const [templateId, setTemplateId] = useState("");
  const [workerSettings, setWorkerSettings] = useState<
    OrchestratorWorker[] | null
  >(existing?.workers || null);
  const templates = useQuery({
    queryKey: ["orchestrator-templates", pid],
    queryFn: () =>
      apiFetch<OrchestratorTemplate[]>(
        `/orchestrator-templates?project_id=${pid}`,
      ),
    enabled: !workflow && source === "template",
  });
  const agents = useQuery({
    queryKey: keys.effective(pid),
    queryFn: () => apiFetch<Agent[]>(`/projects/${pid}/effective-agents`),
  });
  if (agents.isPending) return <Loading />;
  if (!agents.data) return <ErrorState error={agents.error} />;
  const active = agents.data.filter(
    (a) => a.is_active && a.role_key !== "WORKFLOW",
  );
  const workers = active.filter(
    (a) =>
      a.id !== coordinator &&
      (!workerSettings || workerSettings.some((w) => w.agent_id === a.id)),
  );
  const selectedTemplate = templates.data?.find((t) => t.id === templateId);
  const form = (
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
            ...(workerSettings ? { workers: workerSettings } : {}),
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
      {!workflow && !draftId && source === "template" && (
        <section className="space-y-4 rounded-xl border p-4">
          <label className="field">
            Template Orchestrator
            <select
              value={templateId}
              disabled={templates.isPending}
              onChange={(e) => {
                const template = templates.data?.find(
                  (t) => t.id === e.target.value,
                );
                setTemplateId(e.target.value);
                setError("");
                setName(template?.name || "Orchestrator");
                setPrefix(template?.id === "add_feature" ? "FEAT" : "ORCH");
                setCoordinator(
                  template?.orchestrator?.coordinator_agent_id || "",
                );
                setInstructions(template?.instructions || "");
                setRounds(template?.max_rounds || 20);
                setWorkerSettings(template?.orchestrator?.workers || null);
              }}
            >
              <option value="">
                {templates.isPending ? "Đang tải template…" : "Chọn template"}
              </option>
              {templates.data?.map((t) => (
                <option key={t.id} value={t.id}>
                  {t.name}
                </option>
              ))}
            </select>
          </label>
          <ErrorState error={templates.error} />
          {selectedTemplate && (
            <p className="text-sm text-stone-500">
              {selectedTemplate.description}
            </p>
          )}
          {!!selectedTemplate?.missing_agents?.length && (
            <p role="alert" className="error">
              Project thiếu agent hoặc có nhiều agent trùng vai trò:{" "}
              {selectedTemplate.missing_agents.join(", ")}. Thêm đúng thành viên
              trước khi dùng template này.
            </p>
          )}
          <Link className="text-sm underline" href="/templates/orchestrators">
            Quản lý template Orchestrator
          </Link>
        </section>
      )}
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
            <option
              key={a.id}
              value={a.id}
              disabled={workerSettings?.some((w) => w.agent_id === a.id)}
            >
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
            workers.length === 0 ||
            (source === "template" && !selectedTemplate?.orchestrator)
          }
        >
          {busy ? "Đang lưu…" : "Lưu & xuất bản"}
        </button>
      </div>
    </form>
  );
  return (
    <>
      <PageHeader
        title={workflow ? "Cấu hình Orchestrator" : "Tạo Orchestrator"}
        description="Chọn agent điều phối và nhập instruction. Agent tự giao việc cho các thành viên trong project."
      />
      {workflow ? (
        form
      ) : (
        <Tabs
          value={source}
          onValueChange={(value) => {
            if (value !== "manual" && value !== "template") return;
            setSource(value);
            setTemplateId("");
            setWorkerSettings(null);
            setCoordinator("");
            setInstructions("");
            setError("");
          }}
          className="max-w-2xl gap-5"
        >
          <TabsList aria-label="Cách tạo Orchestrator">
            <TabsTrigger
              value="manual"
              disabled={busy || !!draftId}
              className="px-4"
            >
              Nhập tay
            </TabsTrigger>
            <TabsTrigger
              value="template"
              disabled={busy || !!draftId}
              className="px-4"
            >
              Từ template
            </TabsTrigger>
          </TabsList>
          <TabsContent value="manual">
            {source === "manual" && form}
          </TabsContent>
          <TabsContent value="template">
            {source === "template" && form}
          </TabsContent>
        </Tabs>
      )}
    </>
  );
}
