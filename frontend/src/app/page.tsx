"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { Activity, Check, CircleAlert, Loader2, RefreshCw, Terminal, Unplug } from "lucide-react";
import { Button } from "@/components/ui/button";
import { API_URL, getHealth, type HealthResponse } from "@/lib/api";

export default function Home() {
  const [health, setHealth] = useState<HealthResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [updatedAt, setUpdatedAt] = useState<string | null>(null);
  const activeRequest = useRef<AbortController | null>(null);

  const refresh = useCallback(async () => {
    activeRequest.current?.abort();
    const controller = new AbortController();
    activeRequest.current = controller;
    setLoading(true);
    setError(null);
    try {
      const result = await getHealth(AbortSignal.any([controller.signal, AbortSignal.timeout(10_000)]));
      if (controller.signal.aborted) return;
      setHealth(result);
      setUpdatedAt(new Date().toLocaleTimeString("vi-VN"));
    } catch (cause) {
      if (controller.signal.aborted) return;
      setHealth(null);
      setError(cause instanceof Error ? cause.message : "Không thể kết nối backend");
    } finally {
      if (!controller.signal.aborted) setLoading(false);
    }
  }, []);

  useEffect(() => {
    void refresh();
    return () => activeRequest.current?.abort();
  }, [refresh]);

  const connected = health?.acp.claude && health?.acp.codex;
  const status = loading ? "Đang kiểm tra…" : error ? "Backend Offline" : connected ? "ACP Connected" : "ACP Setup Required";

  return (
    <div className="min-h-screen bg-[#ebe9d8] p-3 text-stone-900 md:flex md:gap-3">
      <aside className="flex flex-col justify-between px-3 py-3 md:w-60 md:shrink-0">
        <div>
          <div className="mb-10 flex items-center gap-1.5" aria-hidden="true">
            {["#ff5f56", "#ffbd2e", "#27c93f"].map((color) => <span key={color} className="size-3 rounded-full border border-black/10" style={{ background: color }} />)}
          </div>
          <div className="mb-1 text-xl font-semibold tracking-tight">aiTeams<span className="text-stone-400">.</span></div>
          <p className="text-xs text-stone-500">Multi-Agent Workspace</p>
          <div className="mt-8 flex items-center gap-2 rounded-lg bg-[#d6d4c4] px-3 py-2 text-sm font-medium">
            <Activity className="size-4" /> Kiểm tra hệ thống
          </div>
        </div>
        <div role="status" aria-live="polite" className="my-5 flex items-center gap-2 font-mono text-[11px] text-stone-600">
          <span className={`size-2 rounded-full ${loading ? "animate-pulse bg-stone-400" : error ? "bg-rose-500" : connected ? "bg-emerald-500" : "bg-amber-500"}`} />
          {status}
        </div>
      </aside>

      <main className="min-h-[calc(100vh-24px)] flex-1 overflow-hidden rounded-2xl border border-stone-300/80 bg-white shadow-sm">
        <header className="flex items-center justify-between gap-4 border-b border-stone-200 px-6 py-4">
          <div className="text-xs text-stone-500">Workspace <span className="px-2 text-stone-300">/</span> Setup & Health</div>
          <span className="rounded-md border border-stone-200 px-2 py-1 font-mono text-[10px] text-stone-500">PHASE 0</span>
        </header>
        <div className="mx-auto max-w-3xl px-6 py-12 md:py-20">
          <div className="mb-6 flex size-11 items-center justify-center rounded-xl border border-stone-200 bg-stone-50"><Terminal className="size-5" /></div>
          <p className="mb-3 text-[10px] font-semibold tracking-[0.18em] text-stone-400 uppercase">Khởi tạo môi trường</p>
          <h1 className="text-3xl font-semibold tracking-tight">Sẵn sàng kết nối đội AI.</h1>
          <p className="mt-3 max-w-lg text-sm leading-6 text-stone-500">Kiểm tra backend và hai adapter ACP trước khi bắt đầu xây dựng workspace.</p>

          <section className="mt-9 rounded-xl border border-stone-200" aria-label="Trạng thái dịch vụ">
            {[
              { name: "FastAPI Backend", detail: `${API_URL}/api/health`, ready: health?.status === "ok" },
              { name: "Claude Code", detail: "claude-agent-acp", ready: health?.acp.claude },
              { name: "OpenAI Codex", detail: "codex-acp", ready: health?.acp.codex },
            ].map(({ name, detail, ready }) => (
              <div key={name} className="flex items-center justify-between gap-3 border-b border-stone-100 px-5 py-5 last:border-0">
                <div><h2 className="text-sm font-medium">{name}</h2><p className="mt-1 font-mono text-[11px] text-stone-400">{detail}</p></div>
                <span className={`flex items-center gap-1.5 rounded-full px-2.5 py-1 text-[11px] ${loading ? "bg-stone-100 text-stone-500" : ready ? "bg-emerald-50 text-emerald-700" : "bg-amber-50 text-amber-800"}`}>
                  {loading ? <Loader2 className="size-3 animate-spin" /> : ready ? <Check className="size-3" /> : <Unplug className="size-3" />}
                  {loading ? "Đang kiểm tra" : ready ? "Sẵn sàng" : error ? "Chưa xác định" : "Chưa tìm thấy"}
                </span>
              </div>
            ))}
          </section>
          {error && <div role="alert" className="mt-4 flex items-start gap-2 rounded-lg bg-rose-50 p-3 text-xs leading-5 text-rose-700"><CircleAlert className="mt-0.5 size-4 shrink-0" /><div>Không kết nối được backend. Kiểm tra dịch vụ tại {API_URL}.<br /><span className="font-mono">{error}</span></div></div>}
          <div className="mt-5 flex flex-wrap items-center justify-between gap-3">
            <p className="text-[11px] text-stone-400">{updatedAt ? `Kiểm tra lần cuối lúc ${updatedAt}` : "Đang chờ phản hồi từ backend"}</p>
            <Button variant="outline" size="sm" disabled={loading} onClick={() => void refresh()}><RefreshCw className={`size-3.5 ${loading ? "animate-spin" : ""}`} /> Kiểm tra lại</Button>
          </div>
          <p className="mt-10 border-t border-stone-100 pt-5 text-xs leading-5 text-stone-400">Trạng thái adapter xác nhận tìm thấy binary. Phiên đăng nhập và giao tiếp thực tế được xác minh riêng bằng ACP spike.</p>
        </div>
      </main>
    </div>
  );
}
