"use client";
import { useEffect, useState } from "react";
import Link from "next/link";
import { apiFetch } from "@/lib/api";

type Versions = Record<
  string,
  { version: string | null; installed: boolean; latest?: string | null }
>;
type Metrics = {
  tickets: Record<string, number>;
  guard_denies: number;
  node_average_seconds: Record<string, number>;
};
export default function AdaptersPage() {
  const [versions, setVersions] = useState<Versions>({});
  const [metrics, setMetrics] = useState<Metrics>();
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  async function load(check = false) {
    setBusy(true);
    setError("");
    try {
      const [v, m] = await Promise.all([
        apiFetch<Versions>(`/settings/adapters?check_updates=${check}`),
        apiFetch<Metrics>("/metrics"),
      ]);
      setVersions(v);
      setMetrics(m);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  useEffect(() => {
    void load();
  }, []);
  return (
    <section>
      <h1 className="text-xl font-semibold">Adapter & vận hành</h1>
      <Link className="btn btn-light my-3" href="/settings/audit">
        Nhật ký audit
      </Link>
      {error && (
        <p role="alert" className="error">
          {error}
        </p>
      )}
      <button
        className="btn btn-dark ml-2"
        disabled={busy}
        onClick={() => void load(true)}
      >
        {busy ? "Đang kiểm tra…" : "Kiểm tra cập nhật"}
      </button>
      <table className="my-4 w-full text-left text-sm">
        <thead>
          <tr>
            <th>Adapter</th>
            <th>Đã cài</th>
            <th>Version local</th>
            <th>Mới nhất</th>
          </tr>
        </thead>
        <tbody>
          {Object.entries(versions).map(([name, value]) => (
            <tr key={name} className="border-t">
              <td className="py-3 font-mono">{name}</td>
              <td>{value.installed ? "Có" : "Chưa"}</td>
              <td>{value.version || "Không xác định"}</td>
              <td>{value.latest || "—"}</td>
            </tr>
          ))}
        </tbody>
      </table>
      <p className="text-xs text-stone-500">
        Kiểm tra version trên npm; cập nhật adapter bằng quy trình cài đặt sau
        khi dừng ứng dụng.
      </p>
      {metrics && (
        <div className="mt-6 space-y-3">
          <h2 className="font-semibold">Thống kê</h2>
          <p>Số lần Guard từ chối: {metrics.guard_denies}</p>
          <div className="flex flex-wrap gap-4">
            {Object.entries(metrics.tickets).map(([status, count]) => (
              <span key={status}>
                {status}: <b>{count}</b>
              </span>
            ))}
          </div>
          <h3>Thời gian trung bình mỗi node</h3>
          {Object.entries(metrics.node_average_seconds).map(
            ([node, seconds]) => (
              <p key={node}>
                {node}: {seconds.toFixed(1)}s
              </p>
            ),
          )}
        </div>
      )}
    </section>
  );
}
