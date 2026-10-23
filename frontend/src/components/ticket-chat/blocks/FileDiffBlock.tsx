"use client";
import { useState } from "react";
import dynamic from "next/dynamic";
import { diffLines } from "diff";
import { Modal } from "@/components/ui-app/primitives";
import type { FileChange } from "../types";
const DiffViewer = dynamic(() => import("react-diff-viewer-continued"), {
  ssr: false,
});
export function FileDiffBlock({ change }: { change: FileChange }) {
  const [full, setFull] = useState(false);
  const parts = diffLines(change.old, change.next);
  const added = parts
    .filter((p) => p.added)
    .reduce((n, p) => n + (p.count || 0), 0);
  const removed = parts
    .filter((p) => p.removed)
    .reduce((n, p) => n + (p.count || 0), 0);
  return (
    <>
      <details className="my-2 rounded-lg border border-stone-200 p-2 text-xs">
        <summary className="cursor-pointer">
          📄 Xem thay đổi mã nguồn: {change.path}{" "}
          <span className="text-emerald-700">(+{added}</span>{" "}
          <span className="text-rose-700">−{removed})</span> · Bấm để mở
        </summary>
        <pre className="my-2 max-h-80 overflow-auto font-mono text-xs">
          {change.diff.split("\n").map((line, i) => (
            <div
              key={i}
              className={
                line.startsWith("+")
                  ? "bg-emerald-50 text-emerald-700"
                  : line.startsWith("-")
                    ? "bg-rose-50 text-rose-700"
                    : "text-stone-500"
              }
            >
              {line || " "}
            </div>
          ))}
        </pre>
        <button className="underline" onClick={() => setFull(true)}>
          Xem toàn màn hình
        </button>
      </details>
      {full && (
        <Modal title={change.path} wide onClose={() => setFull(false)}>
          <div className="max-h-[75vh] overflow-auto">
            <DiffViewer
              oldValue={change.old}
              newValue={change.next}
              splitView
            />
          </div>
        </Modal>
      )}
    </>
  );
}
