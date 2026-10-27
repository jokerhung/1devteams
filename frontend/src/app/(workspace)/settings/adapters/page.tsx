"use client";
import { useEffect, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Check,
  CircleDashed,
  Download,
  LoaderCircle,
  LogIn,
  RefreshCw,
  Terminal,
} from "lucide-react";
import { apiFetch, send } from "@/lib/api";

type AdapterJob = {
  id: string;
  adapter: string;
  action: "install" | "login" | "update";
  status: string;
  output: string;
  exit_code: number | null;
};
const actionKey = ["settings", "adapter-action"];

type Versions = Record<
  string,
  { version: string | null; installed: boolean; latest?: string | null }
>;

export default function AdaptersPage() {
  const client = useQueryClient();
  const [starting, setStarting] = useState(false);
  const [actionError, setActionError] = useState("");
  const [code, setCode] = useState("");
  const [sendingCode, setSendingCode] = useState(false);
  const job = useQuery({
    queryKey: actionKey,
    queryFn: () => apiFetch<AdapterJob | null>("/settings/adapter-actions"),
    refetchInterval: (query) =>
      query.state.data?.status === "running" ? 1000 : false,
  });
  const [checking, setChecking] = useState(false);
  const [checkError, setCheckError] = useState("");
  const versions = useQuery({
    queryKey: ["settings", "adapters"],
    queryFn: ({ signal }) =>
      apiFetch<Versions>("/settings/adapters", { signal }),
    staleTime: 60_000,
  });
  const [updates, setUpdates] = useState<Versions | null>(null);
  useEffect(() => {
    if (job.data && job.data.status !== "running") {
      setUpdates(null);
      void client.invalidateQueries({ queryKey: ["settings", "adapters"] });
    }
  }, [client, job.data]);
  async function runAction(adapter: string, action: AdapterJob["action"]) {
    setStarting(true);
    setActionError("");
    setCode("");
    try {
      const value = await send<AdapterJob>(
        `/settings/adapters/${adapter}/actions`,
        { action },
      );
      client.setQueryData(actionKey, value);
    } catch (error) {
      setActionError((error as Error).message);
    } finally {
      setStarting(false);
    }
  }
  const busy = starting || job.data?.status === "running";
  async function checkUpdates() {
    setChecking(true);
    setCheckError("");
    try {
      setUpdates(
        await apiFetch<Versions>("/settings/adapters?check_updates=true"),
      );
    } catch (error) {
      setCheckError((error as Error).message);
    } finally {
      setChecking(false);
    }
  }
  const data = updates || versions.data;
  return (
    <section className="space-y-5">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <h2 className="text-base font-semibold">Adapter đã cài đặt</h2>
          <p className="mt-1 text-sm text-stone-500">
            Phiên bản CLI và cầu nối ACP trên máy chủ.
          </p>
        </div>
        <button
          type="button"
          className="btn btn-light gap-2"
          disabled={checking || versions.isPending}
          onClick={() => void checkUpdates()}
        >
          <RefreshCw
            size={14}
            className={checking ? "animate-spin" : ""}
            aria-hidden="true"
          />
          {checking ? "Đang kiểm tra…" : "Kiểm tra cập nhật"}
        </button>
      </div>
      {(versions.error || checkError || actionError || job.error) && (
        <p
          role="alert"
          className="rounded-xl border border-red-200 bg-red-50 p-3 text-sm text-red-700"
        >
          {actionError ||
            checkError ||
            versions.error?.message ||
            job.error?.message}
        </p>
      )}
      <div className="overflow-hidden rounded-xl border border-stone-200">
        <div className="overflow-x-auto">
          <table className="w-full min-w-[560px] text-left text-sm">
            <thead className="border-b border-stone-200 bg-stone-50 text-xs text-stone-500">
              <tr>
                {[
                  "Adapter",
                  "Trạng thái",
                  "Phiên bản local",
                  "Mới nhất",
                  "Action",
                ].map((label) => (
                  <th key={label} className="px-5 py-3 font-medium">
                    {label}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody className="divide-y divide-stone-100">
              {Object.entries(data || {}).map(([name, value]) => (
                <tr key={name} className="bg-white">
                  <td className="px-5 py-4">
                    <span className="flex items-center gap-3">
                      <Terminal
                        size={17}
                        className="text-stone-400"
                        aria-hidden="true"
                      />
                      <span className="font-mono text-xs font-medium">
                        {name}
                      </span>
                    </span>
                  </td>
                  <td className="px-5 py-4">
                    <span
                      className={`inline-flex items-center gap-1.5 whitespace-nowrap rounded-full px-2 py-1 text-xs ${value.installed ? "bg-emerald-50 text-emerald-700" : "bg-stone-100 text-stone-500"}`}
                    >
                      {value.installed ? (
                        <Check size={12} aria-hidden="true" />
                      ) : (
                        <CircleDashed size={12} aria-hidden="true" />
                      )}
                      {value.installed ? "Đã cài" : "Chưa cài"}
                    </span>
                  </td>
                  <td className="px-5 py-4 font-mono text-xs">
                    {value.version || "—"}
                  </td>
                  <td className="px-5 py-4 font-mono text-xs">
                    {value.latest || "—"}
                  </td>
                  <td className="px-5 py-4">
                    <div className="flex items-center gap-2">
                      <button
                        className="btn btn-light"
                        disabled={busy || value.installed}
                        onClick={() => void runAction(name, "install")}
                        aria-label={`Install ${name}`}
                      >
                        <Download size={13} />
                        Install
                      </button>
                      <button
                        className="btn btn-light"
                        disabled={
                          busy ||
                          !data?.[name.includes("claude") ? "claude" : "codex"]
                            ?.installed
                        }
                        onClick={() => void runAction(name, "login")}
                        aria-label={`Login ${name}`}
                        title="Đăng nhập CLI trên máy chủ; ACP dùng chung tài khoản CLI"
                      >
                        <LogIn size={13} />
                        Login
                      </button>
                      <button
                        className="btn btn-light"
                        disabled={busy || !value.installed}
                        onClick={() => void runAction(name, "update")}
                        aria-label={`Update ${name}`}
                      >
                        <RefreshCw size={13} />
                        Update
                      </button>
                    </div>
                  </td>
                </tr>
              ))}
              {versions.isPending && (
                <tr>
                  <td
                    colSpan={5}
                    role="status"
                    className="p-6 text-center text-stone-500"
                  >
                    Đang tải adapter…
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
        <p className="border-t border-stone-200 bg-stone-50/60 px-5 py-3 text-xs leading-5 text-stone-500">
          Install/Update cài phiên bản mới nhất trên máy chủ. Adapter ACP dùng
          chung tài khoản với CLI Claude/Codex.
        </p>
      </div>
      {job.data && (
        <section
          className="rounded-xl border border-stone-200 p-4 space-y-3"
          aria-label="Tiến trình adapter"
        >
          <div className="flex items-center gap-2 text-sm">
            {job.data.status === "running" && (
              <LoaderCircle size={15} className="animate-spin" />
            )}
            <b>
              {job.data.adapter} · {job.data.action}
            </b>
            <span role="status">
              {
                (
                  {
                    running: "Đang chạy…",
                    completed: "Hoàn tất",
                    failed: "Thất bại",
                    cancelled: "Đã dừng",
                  } as Record<string, string>
                )[job.data.status]
              }
            </span>
            {job.data.status === "running" && (
              <button
                className="btn btn-light ml-auto"
                onClick={async () => {
                  try {
                    await send(
                      `/settings/adapter-actions/${job.data!.id}/cancel`,
                    );
                    await job.refetch();
                  } catch (error) {
                    setActionError((error as Error).message);
                  }
                }}
              >
                Dừng
              </button>
            )}
          </div>
          {job.data.action === "login" && (
            <p className="text-xs text-stone-500">
              Làm theo hướng dẫn CLI bên dưới. Codex hiển thị link và mã xác
              thực. Claude có thể mở trình duyệt trên máy chủ; nếu yêu cầu mã
              xác thực, nhập mã ở bên dưới.
            </p>
          )}
          <pre className="max-h-80 overflow-auto whitespace-pre-wrap break-all rounded-lg bg-stone-50 p-3 text-xs">
            {job.data.output || "Đang chờ CLI…"}
          </pre>
          {job.data.action === "login" &&
            job.data.status === "running" &&
            job.data.adapter.includes("claude") && (
              <form
                className="flex gap-2"
                onSubmit={async (event) => {
                  event.preventDefault();
                  setSendingCode(true);
                  setActionError("");
                  try {
                    await send(
                      `/settings/adapter-actions/${job.data!.id}/input`,
                      { code },
                    );
                    setCode("");
                  } catch (error) {
                    setActionError((error as Error).message);
                  } finally {
                    setSendingCode(false);
                  }
                }}
              >
                <input
                  className="inp flex-1"
                  aria-label="Mã xác thực CLI"
                  autoComplete="off"
                  type="password"
                  value={code}
                  onChange={(event) => setCode(event.target.value)}
                  placeholder="Mã xác thực từ trình duyệt (nếu CLI yêu cầu)"
                />
                <button
                  className="btn btn-dark"
                  disabled={sendingCode || !code.trim()}
                >
                  Gửi mã
                </button>
              </form>
            )}
        </section>
      )}
    </section>
  );
}
