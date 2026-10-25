"use client";
import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Check, CircleDashed, RefreshCw, Terminal } from "lucide-react";
import { apiFetch } from "@/lib/api";

type Versions = Record<
  string,
  { version: string | null; installed: boolean; latest?: string | null }
>;

export default function AdaptersPage() {
  const [checking, setChecking] = useState(false);
  const [checkError, setCheckError] = useState("");
  const versions = useQuery({
    queryKey: ["settings", "adapters"],
    queryFn: ({ signal }) =>
      apiFetch<Versions>("/settings/adapters", { signal }),
    staleTime: 60_000,
  });
  const [updates, setUpdates] = useState<Versions | null>(null);
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
      {(versions.error || checkError) && (
        <p
          role="alert"
          className="rounded-xl border border-red-200 bg-red-50 p-3 text-sm text-red-700"
        >
          {checkError || versions.error?.message}
        </p>
      )}
      <div className="overflow-hidden rounded-xl border border-stone-200">
        <div className="overflow-x-auto">
          <table className="w-full min-w-[560px] text-left text-sm">
            <thead className="border-b border-stone-200 bg-stone-50 text-xs text-stone-500">
              <tr>
                {["Adapter", "Trạng thái", "Phiên bản local", "Mới nhất"].map(
                  (label) => (
                    <th key={label} className="px-5 py-3 font-medium">
                      {label}
                    </th>
                  ),
                )}
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
                </tr>
              ))}
              {versions.isPending && (
                <tr>
                  <td
                    colSpan={4}
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
          Kiểm tra phiên bản mới nhất từ npm. Để cập nhật adapter, dừng ứng dụng
          rồi chạy quy trình cài đặt.
        </p>
      </div>
    </section>
  );
}
