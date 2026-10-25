"use client";
import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { ChevronLeft, ChevronRight, RefreshCw } from "lucide-react";
import { apiFetch } from "@/lib/api";

type Audit = {
  id: string;
  created_at: string;
  user_id: string | null;
  action: string;
  target: string;
  payload: Record<string, unknown>;
  ip: string | null;
};

export default function AuditPage() {
  const [offset, setOffset] = useState(0);
  const audit = useQuery({
    queryKey: ["settings", "audit", offset],
    queryFn: ({ signal }) =>
      apiFetch<Audit[]>(`/audit?offset=${offset}&limit=100`, { signal }),
  });
  const rows = audit.data || [];
  return (
    <section className="space-y-5">
      <div className="flex items-start justify-between gap-4">
        <div>
          <h2 className="text-base font-semibold">Nhật ký hoạt động</h2>
          <p className="mt-1 text-sm text-stone-500">
            Theo dõi các thao tác và sự kiện trong hệ thống.
          </p>
        </div>
        <button
          type="button"
          className="btn btn-light shrink-0"
          aria-label="Tải lại nhật ký"
          disabled={audit.isFetching}
          onClick={() => void audit.refetch()}
        >
          <RefreshCw
            size={14}
            className={audit.isFetching ? "animate-spin" : ""}
            aria-hidden="true"
          />
        </button>
      </div>
      {audit.error && (
        <p
          role="alert"
          className="rounded-xl border border-red-200 bg-red-50 p-3 text-sm text-red-700"
        >
          {audit.error.message}
        </p>
      )}
      <div className="overflow-hidden rounded-xl border border-stone-200">
        <div
          role="region"
          aria-label="Bảng nhật ký hoạt động"
          tabIndex={0}
          className="max-h-[max(12rem,calc(100dvh-440px))] overflow-auto overscroll-contain outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-stone-400 sm:max-h-[max(14rem,calc(100dvh-360px))]"
        >
          <table className="w-full min-w-[720px] text-left text-xs">
            <thead className="border-b border-stone-200 bg-stone-50 text-stone-500">
              <tr>
                {[
                  "Thời gian",
                  "User",
                  "Hành động",
                  "Đối tượng",
                  "Chi tiết",
                  "IP",
                ].map((name) => (
                  <th
                    key={name}
                    className="sticky top-0 z-10 bg-stone-50 px-4 py-3 font-medium shadow-[inset_0_-1px_0_#e7e5e4]"
                  >
                    {name}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody className="divide-y divide-stone-100">
              {rows.map((row) => (
                <tr key={row.id} className="align-top">
                  <td className="whitespace-nowrap px-4 py-4 text-stone-500">
                    {new Date(row.created_at).toLocaleString("vi-VN")}
                  </td>
                  <td className="max-w-36 break-all px-4 py-4 font-mono text-stone-500">
                    {row.user_id || "System"}
                  </td>
                  <td className="px-4 py-4">
                    <span className="inline-block rounded bg-stone-100 px-2 py-1 font-mono break-all">
                      {row.action}
                    </span>
                  </td>
                  <td className="max-w-48 break-all px-4 py-4">{row.target}</td>
                  <td className="min-w-32 px-4 py-4">
                    <details>
                      <summary className="cursor-pointer text-stone-500 hover:text-stone-900">
                        Xem JSON
                      </summary>
                      <pre className="mt-2 max-h-60 max-w-sm overflow-auto rounded-lg bg-stone-50 p-3 whitespace-pre-wrap break-all">
                        {JSON.stringify(row.payload, null, 2)}
                      </pre>
                    </details>
                  </td>
                  <td className="px-4 py-4 font-mono text-stone-500">
                    {row.ip || "—"}
                  </td>
                </tr>
              ))}
              {audit.isPending && (
                <tr>
                  <td
                    colSpan={6}
                    role="status"
                    className="p-8 text-center text-stone-500"
                  >
                    Đang tải nhật ký…
                  </td>
                </tr>
              )}
              {!audit.isPending && !audit.error && !rows.length && (
                <tr>
                  <td colSpan={6} className="p-8 text-center text-stone-500">
                    Chưa có hoạt động trên trang này.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
        <div className="flex flex-wrap items-center justify-between gap-3 border-t border-stone-200 bg-stone-50/60 px-4 py-3">
          <p className="text-xs text-stone-500">
            Trang {offset / 100 + 1}
            {rows.length ? ` · ${offset + 1}–${offset + rows.length}` : ""}
          </p>
          <div className="flex gap-2">
            <button
              type="button"
              className="btn btn-light gap-1"
              disabled={offset === 0 || audit.isFetching}
              onClick={() => setOffset(Math.max(0, offset - 100))}
            >
              <ChevronLeft size={14} aria-hidden="true" />
              Trước
            </button>
            <button
              type="button"
              className="btn btn-light gap-1"
              disabled={rows.length < 100 || audit.isFetching || !!audit.error}
              onClick={() => setOffset(offset + 100)}
            >
              Sau
              <ChevronRight size={14} aria-hidden="true" />
            </button>
          </div>
        </div>
      </div>
    </section>
  );
}
