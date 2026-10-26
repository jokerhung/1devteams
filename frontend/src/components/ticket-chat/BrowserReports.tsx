"use client";
import type { BrowserReport } from "./types";
import { MessageAttachments } from "./MessageAttachments";

export function BrowserReports({ reports }: { reports: BrowserReport[] }) {
  return (
    <div className="mt-3 space-y-3" aria-label="Kết quả Browser Worker">
      {reports.map((report, index) => (
        <section
          key={`${report.at}-${index}`}
          className="rounded-lg border border-stone-200 bg-stone-50 p-3 text-xs"
        >
          <div className="flex flex-wrap items-center gap-2">
            <strong
              className={`rounded px-2 py-1 ${report.status === "PASS" ? "bg-emerald-100 text-emerald-800" : report.status === "FAIL" ? "bg-red-100 text-red-800" : "bg-amber-100 text-amber-800"}`}
            >
              {report.status}
            </strong>
            <b className="break-words">{report.test_case}</b>
            <span className="text-stone-500">
              {report.checks.length} kiểm tra · {report.steps.length} thao tác
            </span>
          </div>
          {report.url && (
            <p className="mt-2 break-all font-mono text-stone-500">
              {report.url}
            </p>
          )}
          {report.summary && (
            <p className="mt-2 whitespace-pre-wrap break-words">
              {report.summary}
            </p>
          )}
          {report.evidence_error && (
            <p className="mt-2 text-amber-700">{report.evidence_error}</p>
          )}
          <MessageAttachments files={report.attachments || []} />
          <details className="mt-2">
            <summary className="cursor-pointer text-stone-500">
              Chi tiết kiểm tra
            </summary>
            <ol className="mt-2 space-y-1">
              {report.steps.map((step, i) => (
                <li
                  key={i}
                  className={
                    step.status === "OK" ? "text-stone-600" : "text-red-700"
                  }
                >
                  {i + 1}. {step.action} · {step.status}
                  {step.error ? ` · ${step.error}` : ""}
                </li>
              ))}
            </ol>
            {!!report.network_errors?.length && (
              <ul className="mt-2 space-y-1 break-all text-red-700">
                {report.network_errors.map((error, i) => (
                  <li key={i}>
                    {error.method} {error.status} · {error.url}
                  </li>
                ))}
              </ul>
            )}
          </details>
        </section>
      ))}
    </div>
  );
}
