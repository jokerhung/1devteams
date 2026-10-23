"use client";
import { memo, useEffect } from "react";
import {
  Handle,
  Position,
  useUpdateNodeInternals,
  type NodeProps,
} from "@xyflow/react";
import type { Agent } from "@/lib/types";
import {
  Logo,
  RuntimeBadge,
  PermissionBadges,
} from "@/components/ui-app/primitives";
import type { FlowNode } from "../serialize";
export const nodeTitles = {
  start: "Bắt đầu",
  end: "Kết thúc",
  agent: "Agent",
  condition: "Điều kiện",
  human_input: "Hỏi người dùng",
  human_confirm: "Người dùng duyệt",
  git_release: "Git Release",
};
export const nodeIcons = {
  start: "▶",
  end: "■",
  agent: "🤖",
  condition: "⑂",
  human_input: "💬",
  human_confirm: "✋",
  git_release: "⎇",
};
export const handleLabels: Record<string, string> = {
  default: "Tiếp theo",
  ready: "Đủ STR",
  need_info: "Cần thêm thông tin",
  pass: "Pass",
  fail: "Fail",
  true: "Đúng",
  false: "Sai",
  approved: "Đồng ý",
  rejected: "Từ chối",
  success: "Thành công",
  failed: "Thất bại",
};
export function outputHandles(
  type: string,
  data: Record<string, unknown>,
): string[] {
  if (type === "end") return [];
  if (type === "condition") return ["true", "false"];
  if (type === "human_confirm") return ["approved", "rejected"];
  if (type === "git_release")
    return [data._legacyDefault ? "default" : "success", "failed"];
  if (type === "agent" && data.routing === "ba") return ["need_info", "ready"];
  if (type === "agent" && ["tester", "review"].includes(String(data.routing)))
    return ["pass", "fail"];
  return ["default"];
}
function BaseNodeComponent({ id, type, data, selected }: NodeProps<FlowNode>) {
  const agent = data._agent as Agent | undefined;
  const errors = data._errors as string[] | undefined;
  const status = String(data._status || "idle");
  const handles = outputHandles(type!, data);
  const updateNodeInternals = useUpdateNodeInternals();
  const handleKey = handles.join(",");
  useEffect(() => {
    updateNodeInternals(id);
  }, [id, handleKey, updateNodeInternals]);
  const border =
    errors?.length || status === "failed"
      ? "border-red-500"
      : status === "done"
        ? "border-emerald-500"
        : type === "start"
          ? "border-emerald-300"
          : ["human_input", "human_confirm"].includes(type!)
            ? "border-indigo-300"
            : type === "git_release"
              ? "border-purple-300"
              : "border-stone-300";
  return (
    <div
      data-testid={`flow-node-${id}`}
      title={errors?.join("\n")}
      className={`w-[250px] rounded-xl border-2 bg-white p-3 shadow-sm ${border} ${selected ? "ring-2 ring-stone-600" : ""} ${status === "running" ? "animate-pulse ring-2 ring-blue-500" : status === "waiting" ? "animate-pulse ring-2 ring-indigo-500" : ""}`}
    >
      {type !== "start" && (
        <Handle
          id="in"
          type="target"
          position={Position.Left}
          aria-label={`Vào ${id}`}
        />
      )}
      <div className="mb-2 flex items-center gap-2 text-xs font-semibold">
        {agent ? (
          <Logo entity={agent} size={24} />
        ) : (
          <span>{nodeIcons[type!]}</span>
        )}
        <span className="truncate">
          {agent?.handle || String(data.label || nodeTitles[type!])}
        </span>
        {errors?.length ? (
          <span className="ml-auto text-red-600">⚠</span>
        ) : status === "done" ? (
          <span className="ml-auto text-emerald-600">✓</span>
        ) : null}
      </div>
      {agent && (
        <>
          <RuntimeBadge runtime={agent.runtime} />
          <p className="my-1 truncate font-mono text-[10px]">
            {agent.model || "Model mặc định"}
          </p>
          <p className="mb-2 truncate text-[11px] text-stone-500">
            {agent.description || agent.display_name}
          </p>
          <PermissionBadges profile={agent.permission_profile} />
        </>
      )}
      {type === "agent" && !agent && (
        <p className="text-xs text-red-600">Chọn agent trong project</p>
      )}
      {type === "agent" && agent?.role_key === "DEVELOPER" && (
        <p className="mt-2 text-[10px] text-red-600">Cấm: git commit / push</p>
      )}
      {type === "start" && (
        <p className="text-[11px] text-stone-500">
          Người dùng tạo ticket
          <br />
          Input: title, description
        </p>
      )}
      {type === "human_input" && (
        <p className="text-[11px] text-indigo-700">Chờ người dùng trả lời</p>
      )}
      {type === "human_confirm" && (
        <>
          <span className="badge">LangGraph Interrupt</span>
          <p className="mt-2 text-[11px]">
            {String(data.message || "Bạn xác nhận lỗi đã được sửa xong?")}
          </p>
        </>
      )}
      {type === "condition" && (
        <p className="break-all font-mono text-[11px]">
          {String(data.expression || "Chưa cấu hình biểu thức")}
        </p>
      )}
      {type === "git_release" && (
        <p className="mt-2 text-[11px] text-purple-700">
          Review diff → commit{data.push !== false && " → push"}
          <br />
          {String(data._branch || "Nhánh project")}
        </p>
      )}
      {type === "end" && (
        <p className="text-[11px] text-stone-500">Hoàn thành workflow</p>
      )}
      <div className="mt-2 flex flex-wrap gap-1">
        {handles.map((handle) => (
          <span
            key={handle}
            className={`rounded bg-stone-50 px-1 text-[9px] ${["fail", "failed", "rejected"].includes(handle) ? "text-red-600" : "text-stone-500"}`}
          >
            {handleLabels[handle]}
          </span>
        ))}
      </div>
      {handles.map((handle) => (
        <Handle
          key={handle}
          id={handle}
          type="source"
          position={
            handle === "need_info"
              ? Position.Top
              : ["fail", "failed", "rejected", "false"].includes(handle)
                ? Position.Bottom
                : Position.Right
          }
          style={{
            background: ["fail", "failed", "rejected", "false"].includes(handle)
              ? "#dc2626"
              : "#059669",
          }}
          aria-label={`${handle} ${id}`}
        />
      ))}
    </div>
  );
}
export const BaseNode = memo(BaseNodeComponent);
