"use client";
import Link from "next/link";
import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { apiFetch, send } from "@/lib/api";
import { keys } from "@/lib/query-keys";
import type { Agent, Workflow } from "@/lib/types";
import {
  PageHeader,
  Loading,
  ErrorState,
  emojis,
  colors,
} from "@/components/ui-app/primitives";
import {
  templateOptions,
  templateGraph,
  missingRoles,
  type TemplateId,
} from "./templates";
export function suggestPrefix(name: string) {
  if (/security/i.test(name)) return "SEC";
  if (/bug/i.test(name)) return "BUG";
  const ascii = name
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "")
    .replaceAll("đ", "d")
    .replaceAll("Đ", "D");
  const words = ascii.toUpperCase().match(/[A-Z]+/g) || [];
  return (words.length > 1 ? words.map((w) => w[0]).join("") : words[0] || "WF")
    .slice(0, 10)
    .padEnd(2, "W");
}
export function CreateWorkflowWizard({ pid }: { pid: string }) {
  const router = useRouter(),
    client = useQueryClient();
  const [step, setStep] = useState(1),
    [name, setName] = useState("Fix Bug"),
    [prefix, setPrefix] = useState("BUG"),
    [prefixEdited, setPrefixEdited] = useState(false);
  const [description, setDescription] = useState(""),
    [icon, setIcon] = useState("🐛"),
    [color, setColor] = useState("sky");
  const [template, setTemplate] = useState<TemplateId | "duplicate">(
      "bugfix_default",
    ),
    [sourceId, setSourceId] = useState("");
  const [busy, setBusy] = useState(false),
    [error, setError] = useState(""),
    [created, setCreated] = useState<Workflow | null>(null);
  useEffect(() => {
    const source = new URLSearchParams(window.location.search).get("duplicate");
    if (source) {
      setTemplate("duplicate");
      setSourceId(source);
      setName("Bản sao workflow");
      setPrefix("COPY");
    }
  }, []);
  const agents = useQuery({
    queryKey: keys.effective(pid),
    queryFn: () => apiFetch<Agent[]>(`/projects/${pid}/effective-agents`),
  });
  const flows = useQuery({
    queryKey: keys.workflows(pid),
    queryFn: () =>
      apiFetch<Workflow[]>(`/projects/${pid}/workflows?include_archived=true`),
  });
  if (agents.isLoading || flows.isLoading) return <Loading />;
  if (!agents.data || !flows.data)
    return <ErrorState error={agents.error || flows.error} />;
  const duplicateName = flows.data.some(
    (w) => w.name.toLowerCase() === name.trim().toLowerCase(),
  );
  const duplicatePrefix = flows.data.some((w) => w.ticket_prefix === prefix);
  const infoValid =
    !!name.trim() &&
    name.trim().length <= 200 &&
    /^[A-Z]{2,10}$/.test(prefix) &&
    !duplicateName &&
    !duplicatePrefix;
  const missing =
    template === "duplicate" ? [] : missingRoles(template, agents.data);
  const source = flows.data.find((w) => w.id === sourceId);
  return (
    <>
      <PageHeader
        title="Tạo workflow"
        description="Thiết kế luồng xử lý cho project, rồi xuất bản để nhận ticket."
      />
      <p className="mb-5 text-xs text-stone-400">
        1. Project › <b className="text-stone-900">2. Workflow</b> › 3. Ticket ›
        4. Chat
      </p>
      <nav
        aria-label="Các bước tạo workflow"
        className="mb-6 flex gap-4 text-xs"
      >
        {["Thông tin", "Điểm bắt đầu", "Mở canvas"].map((label, i) => (
          <span
            key={label}
            aria-current={step === i + 1 ? "step" : undefined}
            className={
              step === i + 1 ? "font-bold text-stone-900" : "text-stone-400"
            }
          >
            {i + 1}. {label}
          </span>
        ))}
      </nav>
      {!agents.data.length && (
        <p className="mb-5 rounded-lg bg-amber-50 p-3 text-xs text-amber-800">
          Chưa có agent hiệu lực. Bạn vẫn có thể tạo bản nháp rồi thêm agent
          sau.{" "}
          <Link className="underline" href={`/projects/${pid}/members`}>
            Thành viên & AI Team
          </Link>
        </p>
      )}
      <form
        className="max-w-2xl space-y-4"
        onSubmit={async (e) => {
          e.preventDefault();
          setError("");
          if (step < 3) {
            setStep(step + 1);
            return;
          }
          if (!infoValid && !created) return;
          setBusy(true);
          try {
            let result = created;
            if (!result) {
              result = await send<Workflow>(
                template === "duplicate"
                  ? `/workflows/${sourceId}/duplicate`
                  : `/projects/${pid}/workflows`,
                template === "duplicate"
                  ? { name: name.trim(), ticket_prefix: prefix }
                  : {
                      name: name.trim(),
                      ticket_prefix: prefix,
                      description,
                      icon,
                      color,
                      template: "blank",
                    },
              );
              setCreated(result);
            }
            if (template === "duplicate")
              await send(
                `/workflows/${result.id}`,
                { description, icon, color },
                "PATCH",
              );
            else
              await send(
                `/workflows/${result.id}/graph`,
                templateGraph(template, agents.data!),
                "PUT",
              );
            await client.invalidateQueries({ queryKey: ["projects"] });
            toast.success(
              "Đã tạo workflow nháp. Thiết kế và xuất bản từ canvas.",
            );
            router.push(`/projects/${pid}/workflows/${result.id}/edit`);
          } catch (e) {
            setError((e as Error).message);
          } finally {
            setBusy(false);
          }
        }}
      >
        {step === 1 && (
          <fieldset className="space-y-4" disabled={!!created}>
            <label className="field">
              Tên workflow
              <input
                required
                maxLength={200}
                value={name}
                onChange={(e) => {
                  setName(e.target.value);
                  if (!prefixEdited) setPrefix(suggestPrefix(e.target.value));
                }}
              />
            </label>
            {duplicateName && (
              <p className="error">Tên workflow đã tồn tại trong project.</p>
            )}
            <label className="field">
              Prefix ticket
              <input
                required
                pattern="[A-Z]{2,10}"
                maxLength={10}
                value={prefix}
                onChange={(e) => {
                  setPrefixEdited(true);
                  setPrefix(e.target.value.toUpperCase());
                }}
              />
            </label>
            {duplicatePrefix && (
              <p className="error">Prefix {prefix} đã tồn tại trong project.</p>
            )}
            {!/^[A-Z]{2,10}$/.test(prefix) && (
              <p className="error">Prefix gồm 2–10 chữ cái A–Z.</p>
            )}
            <label className="field">
              Mô tả
              <textarea
                value={description}
                onChange={(e) => setDescription(e.target.value)}
              />
            </label>
            <div className="flex gap-4">
              <label className="field flex-1">
                Icon
                <select value={icon} onChange={(e) => setIcon(e.target.value)}>
                  {["🐛", ...emojis].map((v) => (
                    <option key={v}>{v}</option>
                  ))}
                </select>
              </label>
              <label className="field flex-1">
                Màu
                <select
                  value={color}
                  onChange={(e) => setColor(e.target.value)}
                >
                  {Object.keys(colors).map((v) => (
                    <option key={v}>{v}</option>
                  ))}
                </select>
              </label>
            </div>
          </fieldset>
        )}
        {step === 2 && (
          <fieldset className="space-y-3" disabled={!!created}>
            <legend className="mb-3 text-sm font-semibold">
              Chọn điểm bắt đầu
            </legend>
            {[
              ...templateOptions,
              { id: "duplicate", name: "Nhân bản từ workflow có sẵn" },
            ].map((t) => (
              <label
                key={t.id}
                className={`flex cursor-pointer gap-3 rounded-xl border p-4 text-xs ${template === t.id ? "border-stone-800 bg-stone-50" : "border-stone-200"}`}
              >
                <input
                  type="radio"
                  name="template"
                  value={t.id}
                  checked={template === t.id}
                  onChange={() => setTemplate(t.id as typeof template)}
                />
                {t.name}
              </label>
            ))}
            {template === "duplicate" && (
              <label className="field">
                Workflow nguồn
                <select
                  value={sourceId}
                  onChange={(e) => setSourceId(e.target.value)}
                  required
                >
                  <option value="">Chọn workflow</option>
                  {flows.data.map((w) => (
                    <option value={w.id} key={w.id}>
                      {w.name} ({w.ticket_prefix})
                    </option>
                  ))}
                </select>
              </label>
            )}
            {missing.length > 0 && (
              <p className="rounded-lg bg-amber-50 p-3 text-xs text-amber-800">
                Thiếu agent cho vai trò: {missing.join(", ")}. Node sẽ để trống
                để chọn sau.{" "}
                <Link className="underline" href={`/projects/${pid}/members`}>
                  Thêm AI Team vào project
                </Link>
              </p>
            )}
          </fieldset>
        )}
        {step === 3 && (
          <div className="space-y-3 rounded-xl border border-stone-200 bg-stone-50 p-5 text-xs">
            <h2 className="text-sm font-semibold">
              {icon} {name} ({prefix})
            </h2>
            <p>{description || "Chưa có mô tả"}</p>
            <p>
              Điểm bắt đầu:{" "}
              {template === "duplicate"
                ? `Nhân bản ${source?.name || ""}`
                : templateOptions.find((t) => t.id === template)?.name}
            </p>
            <p>
              Workflow được tạo ở trạng thái Nháp. Bạn có thể kéo thả, nối dây
              và xuất bản trên canvas.
            </p>
          </div>
        )}
        {error && (
          <p role="alert" className="error">
            {error}
            {created && " Workflow nháp đã được tạo; bấm tiếp tục để hoàn tất."}
          </p>
        )}
        <div className="flex gap-2 pt-3">
          <Link className="btn btn-light" href={`/projects/${pid}`}>
            Huỷ
          </Link>
          {step > 1 && (
            <button
              type="button"
              className="btn btn-light"
              disabled={busy || !!created}
              onClick={() => setStep(step - 1)}
            >
              Quay lại
            </button>
          )}
          <button
            className="btn btn-dark"
            disabled={
              busy ||
              (step === 1 && !infoValid) ||
              (step === 2 && template === "duplicate" && !sourceId)
            }
          >
            {busy
              ? "Đang tạo…"
              : step < 3
                ? "Tiếp tục"
                : created
                  ? "Tiếp tục & mở canvas"
                  : "Tạo & mở canvas"}
          </button>
        </div>
      </form>
    </>
  );
}
