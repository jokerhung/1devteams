"use client";
import { useEffect, useState } from "react";
import Link from "next/link";
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
  const [rows, setRows] = useState<Audit[]>([]);
  const [offset, setOffset] = useState(0);
  const [error, setError] = useState("");
  useEffect(() => {
    let active = true;
    apiFetch<Audit[]>(`/audit?offset=${offset}&limit=100`)
      .then((data) => {
        if (active) {
          setRows(data);
          setError("");
        }
      })
      .catch((e) => {
        if (active) setError(e.message);
      });
    return () => {
      active = false;
    };
  }, [offset]);
  return (
    <section>
      <h1 className="text-xl font-semibold">Nhật ký audit</h1>
      <Link className="btn btn-light my-3" href="/settings/adapters">
        Adapter & vận hành
      </Link>
      {error && (
        <p role="alert" className="error">
          {error}
        </p>
      )}
      <div className="overflow-x-auto">
        <table className="w-full text-left text-xs">
          <thead>
            <tr>
              {[
                "Thời gian",
                "User",
                "Hành động",
                "Đối tượng",
                "Chi tiết",
                "IP",
              ].map((name) => (
                <th key={name} className="p-2">
                  {name}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => (
              <tr key={row.id} className="border-t">
                <td className="p-2">
                  {new Date(row.created_at).toLocaleString("vi-VN")}
                </td>
                <td className="p-2">{row.user_id || "System"}</td>
                <td className="p-2">{row.action}</td>
                <td className="p-2 break-all">{row.target}</td>
                <td className="max-w-lg p-2">
                  <pre className="whitespace-pre-wrap break-all">
                    {JSON.stringify(row.payload, null, 2)}
                  </pre>
                </td>
                <td className="p-2">{row.ip}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <div className="mt-3 flex gap-2">
        <button
          className="btn btn-light"
          disabled={offset === 0}
          onClick={() => setOffset(Math.max(0, offset - 100))}
        >
          Trước
        </button>
        <button
          className="btn btn-light"
          disabled={rows.length < 100}
          onClick={() => setOffset(offset + 100)}
        >
          Sau
        </button>
      </div>
    </section>
  );
}
