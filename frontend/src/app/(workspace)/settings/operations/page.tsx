"use client";
import { useQuery } from "@tanstack/react-query";
import { Activity, ShieldCheck, Ticket, RefreshCw } from "lucide-react";
import { apiFetch } from "@/lib/api";
import { StatusBadge } from "@/components/ui-app/primitives";

type Metrics = {
  tickets: Record<string, number>;
  guard_denies: number;
  node_average_seconds: Record<string, number>;
};

export default function OperationsPage() {
  const metrics = useQuery({
    queryKey: ["settings", "metrics"],
    queryFn: ({ signal }) => apiFetch<Metrics>("/metrics", { signal }),
  });
  const data = metrics.data;
  return (
    <section className="space-y-5">
      <div className="flex items-start justify-between gap-4">
        <div>
          <h2 className="text-base font-semibold">Tổng quan vận hành</h2>
          <p className="mt-1 text-sm text-stone-500">
            Ticket, permission guard và thời gian xử lý của agent.
          </p>
        </div>
        <button
          type="button"
          className="btn btn-light shrink-0"
          aria-label="Tải lại thống kê"
          disabled={metrics.isFetching}
          onClick={() => void metrics.refetch()}
        >
          <RefreshCw
            size={14}
            className={metrics.isFetching ? "animate-spin" : ""}
            aria-hidden="true"
          />
        </button>
      </div>
      {metrics.error && (
        <p role="alert" className="error">
          {metrics.error.message}
        </p>
      )}
      {metrics.isPending && (
        <p role="status" className="text-sm text-stone-500">
          Đang tải thống kê…
        </p>
      )}
      {data && (
        <>
          <div className="grid gap-4 sm:grid-cols-3">
            {[
              {
                label: "Tổng số ticket",
                value: Object.values(data.tickets).reduce((a, b) => a + b, 0),
                icon: Ticket,
              },
              {
                label: "Guard từ chối",
                value: data.guard_denies,
                icon: ShieldCheck,
              },
              {
                label: "Node được thống kê",
                value: Object.keys(data.node_average_seconds).length,
                icon: Activity,
              },
            ].map(({ label, value, icon: Icon }) => (
              <div
                key={label}
                className="rounded-xl border border-stone-200 p-5"
              >
                <div className="flex items-center justify-between gap-2 text-xs text-stone-500">
                  {label}
                  <Icon size={16} aria-hidden="true" />
                </div>
                <p className="mt-3 text-3xl font-semibold tabular-nums">
                  {value.toLocaleString()}
                </p>
              </div>
            ))}
          </div>
          <div className="grid gap-5 md:grid-cols-2">
            <div className="rounded-xl border border-stone-200 p-5">
              <h3 className="mb-4 text-sm font-semibold">Trạng thái ticket</h3>
              <div className="space-y-3">
                {Object.entries(data.tickets).map(([status, count]) => (
                  <div
                    key={status}
                    className="flex items-center justify-between gap-3"
                  >
                    <StatusBadge status={status} />
                    <b className="text-sm tabular-nums">{count}</b>
                  </div>
                ))}
                {!Object.keys(data.tickets).length && (
                  <p className="text-sm text-stone-500">Chưa có ticket.</p>
                )}
              </div>
            </div>
            <div className="rounded-xl border border-stone-200 p-5">
              <h3 className="mb-4 text-sm font-semibold">
                Thời gian trung bình mỗi node
              </h3>
              <div className="space-y-3">
                {Object.entries(data.node_average_seconds).map(
                  ([node, seconds]) => (
                    <div
                      key={node}
                      className="flex items-center justify-between gap-3 text-sm"
                    >
                      <span
                        className="min-w-0 truncate font-mono text-xs"
                        title={node}
                      >
                        {node}
                      </span>
                      <span className="shrink-0 tabular-nums text-stone-500">
                        {seconds.toFixed(1)}s
                      </span>
                    </div>
                  ),
                )}
                {!Object.keys(data.node_average_seconds).length && (
                  <p className="text-sm text-stone-500">
                    Chưa có lượt chạy hoàn tất.
                  </p>
                )}
              </div>
            </div>
          </div>
        </>
      )}
    </section>
  );
}
