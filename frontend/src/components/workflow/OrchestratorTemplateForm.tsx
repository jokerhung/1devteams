"use client";

import Link from "next/link";
import { useState } from "react";
import { useRouter } from "next/navigation";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Plus, Trash2, LoaderCircle } from "lucide-react";
import { toast } from "sonner";
import { apiFetch, send } from "@/lib/api";
import { ErrorState, Loading } from "@/components/ui-app/primitives";
import type {
  OrchestratorTemplate,
  OrchestratorTemplateInput,
  Agent,
} from "@/lib/types";

function AgentSelect({
  label,
  agents,
  value,
  used,
  onChange,
}: {
  label: string;
  agents: Agent[];
  value: string;
  used: string[];
  onChange: (agent: Agent | undefined) => void;
}) {
  return (
    <label className="field">
      {label}
      <select
        required
        value={value}
        onChange={(e) => onChange(agents.find((a) => a.id === e.target.value))}
      >
        <option value="">Chọn agent có sẵn</option>
        {agents.map((agent) => (
          <option
            key={agent.id}
            value={agent.id}
            disabled={used.includes(agent.id)}
          >
            {agent.handle} · {agent.display_name}
          </option>
        ))}
      </select>
    </label>
  );
}

export function OrchestratorTemplateForm({
  template,
}: {
  template?: OrchestratorTemplate;
}) {
  const router = useRouter();
  const client = useQueryClient();
  const [value, setValue] = useState<OrchestratorTemplateInput>(() => ({
    name: template?.name || "",
    description: template?.description || "",
    coordinator_role: template?.coordinator_role || "COORDINATOR",
    coordinator_handle: template?.coordinator_handle || "@leader",
    instructions: template?.instructions || "",
    max_rounds: template?.max_rounds || 20,
    workers: template?.workers || [
      {
        role_key: "DEVELOPER",
        agent_handle: "@developer",
        instructions: "",
        document_name: null,
      },
    ],
  }));
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const agents = useQuery({
    queryKey: ["agents"],
    queryFn: () => apiFetch<Agent[]>("/agents"),
  });
  const updateWorker = (
    index: number,
    patch: Partial<OrchestratorTemplateInput["workers"][number]>,
  ) =>
    setValue({
      ...value,
      workers: value.workers.map((w, i) =>
        i === index ? { ...w, ...patch } : w,
      ),
    });
  if (agents.isPending) return <Loading />;
  if (!agents.data) return <ErrorState error={agents.error} />;
  const active = agents.data.filter(
    (a) => a.is_active && a.role_key !== "WORKFLOW",
  );
  const resolve = (role: string | undefined, handle: string | undefined) => {
    const candidates = active.filter((a) => a.role_key === role);
    return handle
      ? candidates.find((a) => a.handle === handle)
      : candidates.length === 1
        ? candidates[0]
        : undefined;
  };
  const coordinator = resolve(value.coordinator_role, value.coordinator_handle);
  const workers = value.workers.map((w) => resolve(w.role_key, w.agent_handle));
  const selectedIds = [coordinator?.id, ...workers.map((a) => a?.id)].filter(
    (id): id is string => !!id,
  );
  const validAgents =
    !!coordinator &&
    workers.every(Boolean) &&
    new Set(selectedIds).size === workers.length + 1;
  return (
    <form
      className="max-w-3xl space-y-5"
      onSubmit={async (event) => {
        event.preventDefault();
        if (!validAgents || !coordinator) return;
        setBusy(true);
        setError("");
        try {
          await send(
            `/orchestrator-templates${template ? `/${template.id}` : ""}`,
            {
              ...value,
              coordinator_role: coordinator.role_key,
              coordinator_handle: coordinator.handle,
              workers: value.workers.map((w, i) => ({
                ...w,
                role_key: workers[i]!.role_key,
                agent_handle: workers[i]!.handle,
              })),
            },
            template ? "PUT" : "POST",
          );
          await client.invalidateQueries({
            queryKey: ["orchestrator-templates"],
          });
          toast.success("Đã lưu template Orchestrator");
          router.push("/templates/orchestrators");
        } catch (err) {
          setError((err as Error).message);
        } finally {
          setBusy(false);
        }
      }}
    >
      <fieldset disabled={busy} className="space-y-5">
        <label className="field">
          Tên template
          <input
            required
            maxLength={100}
            value={value.name}
            onChange={(e) => setValue({ ...value, name: e.target.value })}
          />
        </label>
        <label className="field">
          Mô tả
          <textarea
            maxLength={2000}
            value={value.description}
            onChange={(e) =>
              setValue({ ...value, description: e.target.value })
            }
          />
        </label>
        <AgentSelect
          label="Agent điều phối"
          agents={active}
          value={coordinator?.id || ""}
          used={workers.flatMap((a) => (a ? [a.id] : []))}
          onChange={(agent) =>
            setValue({
              ...value,
              coordinator_role: agent?.role_key || "",
              coordinator_handle: agent?.handle || "",
            })
          }
        />
        {coordinator && (
          <p className="text-xs text-stone-500">
            Vai trò: {coordinator.role_key}
          </p>
        )}
        <label className="field">
          Instruction của Orchestrator
          <textarea
            required
            rows={12}
            maxLength={20000}
            value={value.instructions}
            onChange={(e) =>
              setValue({ ...value, instructions: e.target.value })
            }
          />
        </label>
        <label className="field">
          Số lượt điều phối trước khi hỏi người dùng
          <input
            type="number"
            required
            min={1}
            max={40}
            value={value.max_rounds}
            onChange={(e) =>
              setValue({ ...value, max_rounds: Number(e.target.value) })
            }
          />
        </label>
        <section className="space-y-4">
          <h2 className="font-semibold">Thành viên thực hiện</h2>
          <p className="text-sm text-stone-500">
            Chọn từ các agent đang hoạt động. Khi áp dụng template, các agent
            cần thuộc project.
          </p>
          <Link className="text-sm underline" href="/agents">
            Quản lý Agents & Teams
          </Link>
          {value.workers.map((worker, index) => (
            <fieldset key={index} className="space-y-3 rounded-xl border p-4">
              <legend className="text-sm font-medium">
                Thành viên {index + 1}
              </legend>
              <AgentSelect
                label={`Agent thực hiện ${index + 1}`}
                agents={active}
                value={workers[index]?.id || ""}
                used={[
                  ...(coordinator ? [coordinator.id] : []),
                  ...workers.flatMap((a, i) =>
                    a && i !== index ? [a.id] : [],
                  ),
                ]}
                onChange={(agent) =>
                  updateWorker(index, {
                    role_key: agent?.role_key || "",
                    agent_handle: agent?.handle || "",
                  })
                }
              />
              {workers[index] && (
                <p className="text-xs text-stone-500">
                  Vai trò: {workers[index]?.role_key}
                </p>
              )}
              <label className="field">
                Nhiệm vụ
                <textarea
                  rows={3}
                  maxLength={20000}
                  value={worker.instructions || ""}
                  onChange={(e) =>
                    updateWorker(index, { instructions: e.target.value })
                  }
                />
              </label>
              <label className="field">
                File Markdown đầu ra (tùy chọn)
                <input
                  placeholder="design.md"
                  maxLength={100}
                  pattern={"[a-zA-Z0-9_\\-][a-zA-Z0-9_.\\-]*\\.md"}
                  value={worker.document_name || ""}
                  onChange={(e) =>
                    updateWorker(index, {
                      document_name: e.target.value || null,
                    })
                  }
                />
              </label>
              <button
                type="button"
                className="btn btn-light text-red-700"
                aria-label={`Bỏ thành viên ${index + 1}`}
                disabled={value.workers.length === 1}
                onClick={() =>
                  setValue({
                    ...value,
                    workers: value.workers.filter((_, i) => i !== index),
                  })
                }
              >
                <Trash2 size={14} />
              </button>
            </fieldset>
          ))}
          <button
            type="button"
            className="btn btn-light"
            disabled={
              value.workers.length >= 30 ||
              value.workers.length + 1 >= active.length
            }
            onClick={() =>
              setValue({
                ...value,
                workers: [
                  ...value.workers,
                  {
                    role_key: "",
                    agent_handle: "",
                    instructions: "",
                    document_name: null,
                  },
                ],
              })
            }
          >
            <Plus size={14} /> Thêm thành viên
          </button>
        </section>
        <p className="text-xs text-stone-500">
          Thay đổi template chỉ áp dụng khi tạo Orchestrator mới. Các
          Orchestrator và ticket hiện có giữ nguyên cấu hình đã lưu.
        </p>
        {error && (
          <p role="alert" className="error">
            {error}
          </p>
        )}
        <div className="flex gap-2">
          <Link className="btn btn-light" href="/templates/orchestrators">
            Hủy
          </Link>
          <button className="btn btn-dark" disabled={busy || !validAgents}>
            {busy && <LoaderCircle size={14} className="animate-spin" />}
            {busy ? "Đang lưu…" : "Lưu template"}
          </button>
        </div>
      </fieldset>
    </form>
  );
}
