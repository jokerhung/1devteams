"use client";
import { useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { apiFetch, send } from "@/lib/api";
import type { Agent, Team, Connection, Permission } from "@/lib/types";
import { LogoPicker, Modal, colors, TagInput } from "./primitives";
type Preset = "read_only" | "developer" | "tester" | "leader" | "custom";
type Runtime = Agent["runtime"];
const readOnly: Permission = {
  allow_read: true,
  allow_write: false,
  allow_terminal: false,
  allow_fetch: false,
  can_git_release: false,
  allowed_commands: [],
  blocked_commands: ["git commit", "git push", "git reset --hard", "rm -rf"],
};
export function AgentForm({
  agent,
  teams,
  onClose,
  onRestart,
}: {
  agent?: Agent;
  teams: Team[];
  onClose: () => void;
  onRestart: (agent: Agent, pending: boolean) => void;
}) {
  const client = useQueryClient();
  const [persisted, setPersisted] = useState(agent);
  const [handle, setHandle] = useState(agent?.handle || "@");
  const [name, setName] = useState(agent?.display_name || "");
  const [runtime, setRuntime] = useState<Runtime>(
    agent?.runtime || "claude-code",
  );
  const [model, setModel] = useState(agent?.model || "");
  const [fallbackModel, setFallbackModel] = useState(
    agent?.fallback_model || "",
  );
  const [fallbackRuntime, setFallbackRuntime] = useState(
    agent?.fallback_runtime || "",
  );
  const [fallbackAgent, setFallbackAgent] = useState(
    agent?.fallback_agent_id || "",
  );
  const [baseUrl, setBaseUrl] = useState(agent?.base_url || "");
  const [apiKey, setApiKey] = useState("");
  const [preset, setPreset] = useState<Preset>(agent ? "custom" : "read_only");
  const [permission, setPermission] = useState<Permission>(
    agent?.permission_profile || readOnly,
  );
  const [prompt, setPrompt] = useState(agent?.system_prompt || "");
  const [description, setDescription] = useState(agent?.description || "");
  const [icon, setIcon] = useState(agent?.icon || "🤖");
  const [logo, setLogo] = useState(agent?.logo_url || null);
  const [color, setColor] = useState(agent?.color || "stone");
  const [selectedTeams, setSelectedTeams] = useState(
    teams
      .filter((t) => agent && t.agent_ids.includes(agent.id))
      .map((t) => t.id),
  );
  const [busy, setBusy] = useState(false);
  const [testing, setTesting] = useState(false);
  const [connection, setConnection] = useState<Connection | null>(null);
  const [error, setError] = useState("");
  const catalog = useQuery({
    queryKey: ["model-catalog"],
    queryFn: () =>
      apiFetch<Record<string, { id: string; label: string }[]>>(
        "/agents/models-catalog",
      ),
  });
  const presets = useQuery({
    queryKey: ["permission-presets"],
    queryFn: () =>
      apiFetch<Record<string, Permission>>("/agents/permission-presets"),
  });
  const usage = useQuery({
    queryKey: ["agent-usage", agent?.id],
    queryFn: () =>
      apiFetch<{ running_tickets: { id: string }[] }>(
        `/agents/${agent!.id}/usage`,
      ),
    enabled: !!agent,
  });
  const nativeModels = catalog.data?.[runtime] || [];
  const validHandle = /^@[a-z0-9_\-]{2,49}$/.test(handle);
  const custom = runtime === "openai-api";
  let validUrl = true;
  try {
    if (custom)
      validUrl = ["http:", "https:"].includes(new URL(baseUrl).protocol);
  } catch {
    validUrl = false;
  }
  function selectPreset(value: Preset) {
    setPreset(value);
    if (value !== "custom" && presets.data?.[value])
      setPermission(presets.data[value]);
    else if (value === "read_only") setPermission(readOnly);
  }
  async function testConnection() {
    setTesting(true);
    setConnection(null);
    try {
      if (custom && (!validUrl || !model || (!apiKey && !agent?.has_key)))
        throw new Error("Nhập Base URL, API key và model để kiểm tra kết nối.");
      if (
        custom &&
        !apiKey &&
        agent &&
        baseUrl.replace(/\/$/, "") === agent.base_url &&
        model === agent.model
      )
        setConnection(
          await send<Connection>(`/agents/${agent.id}/test-connection`),
        );
      else if (custom) {
        if (!apiKey)
          throw new Error("Nhập API key để kiểm tra cấu hình mới chưa lưu.");
        setConnection(
          await send<Connection>("/agents/test-connection-draft", {
            base_url: baseUrl.replace(/\/$/, ""),
            api_key: apiKey,
            model,
          }),
        );
      } else if (agent)
        setConnection(
          await send<Connection>(`/agents/${agent.id}/test-connection`),
        );
      else throw new Error("Lưu agent trước khi kiểm tra kết nối CLI.");
    } catch (e) {
      setConnection({ ok: false, error: (e as Error).message, latency_ms: 0 });
    } finally {
      setTesting(false);
    }
  }
  return (
    <Modal
      title={agent ? `Sửa ${agent.handle}` : "Tạo Agent"}
      onClose={onClose}
    >
      <form
        className="space-y-4"
        onSubmit={async (e) => {
          e.preventDefault();
          setError("");
          if (!validHandle) {
            setError("Handle cần @ và 2–49 ký tự chữ thường, số, _ hoặc -.");
            return;
          }
          if (custom && !validUrl) {
            setError("Base URL không hợp lệ (cần http:// hoặc https://)");
            return;
          }
          if (custom && !apiKey && !agent?.has_key) {
            setError("API key là bắt buộc khi tạo agent OpenAI Custom.");
            return;
          }
          if (
            custom &&
            (permission.allow_write ||
              permission.allow_terminal ||
              permission.can_git_release)
          ) {
            setError(
              "Agent API không sửa file/chạy lệnh — chọn nhóm quyền Chỉ đọc hoặc Tuỳ chỉnh",
            );
            return;
          }
          for (const team of teams)
            if (
              agent &&
              team.agent_ids.includes(agent.id) &&
              !selectedTeams.includes(team.id) &&
              team.agent_ids.length === 1
            ) {
              setError(
                `Không bỏ được: ${agent.handle} là agent duy nhất của team “${team.name}”`,
              );
              return;
            }
          setBusy(true);
          try {
            const values: Record<string, unknown> = {
              display_name: name.trim(),
              description,
              runtime,
              model: model || null,
              fallback_model: fallbackModel || null,
              fallback_runtime: fallbackRuntime || null,
              fallback_agent_id: fallbackAgent || null,
              base_url: custom ? baseUrl.replace(/\/$/, "") : null,
              system_prompt: prompt,
              permission_profile: permission,
              icon,
              logo_url: logo,
              color,
            };
            if (apiKey) values.api_key = apiKey;
            let saved: Agent;
            let restart = false;
            if (persisted) {
              const changed = Object.fromEntries(
                Object.entries(values).filter(
                  ([key, value]) =>
                    !(
                      key === "description" &&
                      !value &&
                      !persisted.description
                    ) &&
                    JSON.stringify(value) !==
                      JSON.stringify(persisted[key as keyof Agent] ?? null),
                ),
              );
              if (Object.keys(changed).length) {
                onRestart(persisted, true);
                const result = await send<{ agent: Agent; restart: boolean }>(
                  `/agents/${persisted.id}`,
                  changed,
                  "PATCH",
                );
                saved = result.agent;
                restart = result.restart;
                onRestart(saved, false);
              } else saved = persisted;
            } else
              saved = await send<Agent>("/agents", {
                ...values,
                handle,
                role_key: "CUSTOM",
              });
            setPersisted(saved);
            for (const team of teams) {
              const has = team.agent_ids.includes(saved.id);
              const wants = selectedTeams.includes(team.id);
              if (has !== wants)
                await send(
                  `/teams/${team.id}/agents`,
                  {
                    agent_ids: wants
                      ? [...team.agent_ids, saved.id]
                      : team.agent_ids.filter((id) => id !== saved.id),
                  },
                  "PUT",
                );
            }
            await Promise.all([
              client.invalidateQueries({ queryKey: ["agents"] }),
              client.invalidateQueries({ queryKey: ["teams"] }),
              client.invalidateQueries({ queryKey: ["projects"] }),
            ]);
            toast.success(
              agent
                ? restart
                  ? `✔ ${saved.handle} đã khởi động lại (${saved.runtime} · ${saved.model || "mặc định"})`
                  : "Không có thay đổi cấu hình agent, không cần khởi động lại"
                : "Đã tạo Agent",
            );
            onClose();
          } catch (e) {
            setError((e as Error).message);
            if (persisted) onRestart(persisted, false);
            client.invalidateQueries({ queryKey: ["agents"] });
            client.invalidateQueries({ queryKey: ["teams"] });
            client.invalidateQueries({ queryKey: ["projects"] });
          } finally {
            setBusy(false);
          }
        }}
      >
        {agent && (
          <div className="rounded-lg border border-amber-200 bg-amber-50 p-3 text-xs leading-relaxed text-amber-900">
            ↻ Lưu thay đổi sẽ khởi động lại agent. Tiến trình ACP hiện tại bị
            đóng và một session mới được tạo với cấu hình mới.
            {!!usage.data?.running_tickets.length && (
              <p className="mt-2">
                Hiện có <b>{usage.data.running_tickets.length} ticket</b> đang
                dùng {agent.handle}; lượt đang chạy sẽ bị dừng và chạy lại từ
                đầu bước đó.
              </p>
            )}
          </div>
        )}
        <LogoPicker
          icon={icon}
          logo_url={logo}
          onChange={(i, l) => {
            setIcon(i);
            setLogo(l);
          }}
        />
        <div className="grid grid-cols-2 gap-3">
          <label className="field">
            Tên Agent (Handle)
            <input
              value={handle}
              disabled={!!persisted}
              onChange={(e) =>
                setHandle("@" + e.target.value.replace(/^@/, "").toLowerCase())
              }
              required
              aria-invalid={!validHandle}
            />
          </label>
          <label className="field">
            Vai trò
            <input
              required
              value={name}
              onChange={(e) => setName(e.target.value)}
            />
          </label>
        </div>
        {!validHandle && handle !== "@" && (
          <p className="error">
            Handle không hợp lệ: dùng chữ thường, số, _ hoặc - (2–49 ký tự).
          </p>
        )}
        <label className="field">
          Loại Agent
          <select
            value={runtime}
            onChange={(e) => {
              const value = e.target.value as Runtime;
              setRuntime(value);
              setModel("");
              setConnection(null);
              if (value === "openai-api") {
                setPreset("read_only");
                setPermission(readOnly);
              }
            }}
          >
            <option value="claude-code">Claude Code (claude-agent-acp)</option>
            <option value="codex">OpenAI Codex (codex-acp)</option>
            <option value="openai-api">
              OpenAI Custom (OpenAI-compatible, URL tuỳ chỉnh)
            </option>
          </select>
        </label>
        <label className="field">
          Nhóm quyền
          <select
            value={preset}
            onChange={(e) => selectPreset(e.target.value as Preset)}
          >
            <option value="read_only">Chỉ đọc</option>
            <option value="developer" disabled={custom}>
              Đọc/Ghi không commit
            </option>
            <option value="tester" disabled={custom}>
              Đọc + chạy test
            </option>
            {agent?.is_builtin && (
              <option value="leader" disabled={custom}>
                Preset Leader
              </option>
            )}
            <option value="custom">Tuỳ chỉnh</option>
          </select>
        </label>
        {custom ? (
          <div className="space-y-3 rounded-xl border border-sky-200 bg-sky-50 p-4">
            <p className="text-xs leading-relaxed text-sky-900">
              Agent gọi OpenAI Custom qua endpoint tương thích OpenAI
              (/chat/completions) với URL tuỳ chỉnh (OpenAI, Azure, OpenRouter,
              LiteLLM, Ollama, vLLM…). Agent loại này chỉ trả lời văn bản: không
              tự đọc/sửa file hay chạy lệnh trong workspace — hợp với vai trò
              BA, review, tóm tắt, giải thích.
            </p>
            <label className="field">
              Base URL
              <input
                className="font-mono"
                value={baseUrl}
                placeholder="https://api.openai.com/v1"
                onChange={(e) => setBaseUrl(e.target.value)}
                onBlur={() => setBaseUrl(baseUrl.replace(/\/$/, ""))}
                required
              />
            </label>
            {!validUrl && baseUrl && (
              <p className="error">
                Base URL không hợp lệ (cần http:// hoặc https://)
              </p>
            )}
            <label className="field">
              API Key
              <input
                type="password"
                autoComplete="off"
                value={apiKey}
                onChange={(e) => setApiKey(e.target.value)}
                placeholder={
                  agent?.has_key
                    ? "•••••••• (để trống = giữ nguyên)"
                    : "API key"
                }
                required={!agent?.has_key}
              />
            </label>
            <p className="text-[11px] text-sky-700">
              API key được lưu mã hoá phía máy chủ và không bao giờ hiển thị lại
            </p>
            <label className="field">
              Model
              <input
                required
                list="api-models"
                value={model}
                onChange={(e) => setModel(e.target.value)}
              />
              <datalist id="api-models">
                {Array.from(
                  new Set([
                    "gpt-5",
                    "gpt-5-mini",
                    "gpt-4.1",
                    ...(connection?.models || []).map((m) =>
                      String((m as { id?: string }).id || ""),
                    ),
                  ]),
                )
                  .filter(Boolean)
                  .map((id) => (
                    <option key={id} value={id} />
                  ))}
              </datalist>
            </label>
            <button
              type="button"
              disabled={testing}
              onClick={testConnection}
              className="btn btn-light"
            >
              {testing ? "Đang kiểm tra…" : "Kiểm tra kết nối"}
            </button>
          </div>
        ) : (
          <label className="field">
            Model
            <select
              aria-label="Model ACP"
              value={model}
              onChange={(e) => setModel(e.target.value)}
            >
              <option value="">Mặc định runtime</option>
              {model && !nativeModels.some((m) => m.id === model) && (
                <option value={model}>{model}</option>
              )}
              {nativeModels.map((m) => (
                <option key={m.id} value={m.id}>
                  {m.label}
                </option>
              ))}
            </select>
          </label>
        )}
        <details className="rounded border border-stone-200 p-3 text-sm">
          <summary className="cursor-pointer">
            Fallback khi model quá tải
          </summary>
          <p className="my-2 text-xs text-stone-500">
            Thử lại sau 30s, 60s rồi chuyển cấu hình dự phòng. Bỏ trống để tắt
            fallback.
          </p>
          <label className="field">
            Model dự phòng
            <input
              value={fallbackModel}
              onChange={(e) => setFallbackModel(e.target.value)}
            />
          </label>
          <label className="field">
            Runtime dự phòng
            <select
              value={fallbackRuntime}
              onChange={(e) => setFallbackRuntime(e.target.value)}
            >
              <option value="">Cùng runtime</option>
              <option value="claude-code">Claude Code</option>
              <option value="codex">Codex</option>
              <option value="openai-api">OpenAI API (cần agent riêng)</option>
            </select>
          </label>
          <label className="field">
            ID agent API dự phòng
            <input
              value={fallbackAgent}
              onChange={(e) => setFallbackAgent(e.target.value)}
              placeholder="Chỉ dành cho vai trò text-only"
            />
          </label>
        </details>
        {connection && (
          <p
            role="status"
            className={connection.ok ? "text-xs text-emerald-700" : "error"}
          >
            {connection.ok
              ? `✔ Kết nối được ${custom ? new URL(baseUrl).host : runtime} · ${custom ? `GET /models ${connection.status}` : connection.runtime_version || "CLI sẵn sàng"} · ${connection.latency_ms} ms`
              : `✘ ${connection.error}`}
          </p>
        )}
        <label className="field">
          Mô tả
          <input
            value={description}
            onChange={(e) => setDescription(e.target.value)}
          />
        </label>
        <label className="field">
          Mô tả chi tiết vai trò (System Prompt)
          <textarea
            value={prompt}
            onChange={(e) => setPrompt(e.target.value)}
          />
        </label>
        <fieldset>
          <legend className="mb-2 text-xs font-medium">
            AI Team (tuỳ chọn)
          </legend>
          <div className="grid grid-cols-2 gap-2">
            {teams.map((t) => (
              <label key={t.id} className="flex items-center gap-2 text-xs">
                <input
                  type="checkbox"
                  checked={selectedTeams.includes(t.id)}
                  onChange={(e) =>
                    setSelectedTeams(
                      e.target.checked
                        ? [...selectedTeams, t.id]
                        : selectedTeams.filter((id) => id !== t.id),
                    )
                  }
                />
                {t.icon} {t.name}
              </label>
            ))}
          </div>
        </fieldset>
        <details className="rounded-lg border border-stone-200 p-3">
          <summary className="text-xs font-medium">Nâng cao</summary>
          <div className="mt-4 space-y-3">
            <label className="field">
              Màu
              <select value={color} onChange={(e) => setColor(e.target.value)}>
                {Object.keys(colors).map((c) => (
                  <option key={c}>{c}</option>
                ))}
              </select>
            </label>
            {(
              [
                "allow_read",
                "allow_write",
                "allow_terminal",
                "allow_fetch",
                "can_git_release",
              ] as const
            ).map((key) => (
              <label className="flex items-center gap-2 text-xs" key={key}>
                <input
                  type="checkbox"
                  checked={permission[key]}
                  disabled={
                    custom &&
                    [
                      "allow_write",
                      "allow_terminal",
                      "can_git_release",
                    ].includes(key)
                  }
                  onChange={(e) => {
                    setPreset("custom");
                    setPermission({ ...permission, [key]: e.target.checked });
                  }}
                />
                {
                  {
                    allow_read: "Đọc file",
                    allow_write: "Ghi file",
                    allow_terminal: "Chạy lệnh",
                    allow_fetch: "Truy cập mạng",
                    can_git_release: "Git release (backend)",
                  }[key]
                }
              </label>
            ))}
            {(["allowed_commands", "blocked_commands"] as const).map((key) => (
              <TagInput
                key={key}
                label={
                  key === "allowed_commands" ? "Lệnh cho phép" : "Lệnh cấm"
                }
                values={permission[key] || []}
                onChange={(commands) => {
                  setPreset("custom");
                  setPermission({
                    ...permission,
                    [key]: commands,
                  });
                }}
              />
            ))}
            {!custom && (
              <button
                type="button"
                disabled={testing || !agent}
                className="btn btn-light"
                onClick={testConnection}
              >
                Kiểm tra kết nối CLI
              </button>
            )}
          </div>
        </details>
        {error && (
          <p role="alert" className="error">
            {error}
          </p>
        )}
        <div className="flex justify-end gap-2">
          <button type="button" className="btn btn-light" onClick={onClose}>
            Huỷ
          </button>
          <button disabled={busy} className="btn btn-dark">
            {busy ? "Đang lưu…" : agent ? "Lưu & khởi động lại" : "Lưu Agent"}
          </button>
        </div>
      </form>
    </Modal>
  );
}
