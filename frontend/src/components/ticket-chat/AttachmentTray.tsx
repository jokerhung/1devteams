"use client";
/* eslint-disable @next/next/no-img-element -- Local blob previews must bypass the image optimizer. */
import { useEffect, useState } from "react";
import type { DraftFile } from "./types";
function DraftCard({
  file,
  onRemove,
}: {
  file: DraftFile;
  onRemove: () => void;
}) {
  const [url, setUrl] = useState("");
  useEffect(() => {
    if (!file.file.type.startsWith("image/")) return;
    const url = URL.createObjectURL(file.file);
    setUrl(url);
    return () => URL.revokeObjectURL(url);
  }, [file.file]);
  return (
    <div className="flex max-w-64 items-center gap-2 rounded-lg border border-stone-200 bg-stone-50 p-2 text-[11px]">
      {url ? (
        <img src={url} alt="" className="size-8 rounded object-cover" />
      ) : (
        <span>📄</span>
      )}
      <span className="min-w-0 flex-1">
        <span className="block truncate">{file.file.name}</span>
        <span className={file.error ? "text-red-600" : "text-stone-400"}>
          {file.error ||
            (file.attachment
              ? `${(file.file.size / 1024).toFixed(1)} KB · Đã tải`
              : `Đang tải ${file.progress}%`)}
        </span>
      </span>
      <button
        type="button"
        aria-label={`Gỡ ${file.file.name}`}
        onClick={onRemove}
      >
        ✕
      </button>
    </div>
  );
}
export function AttachmentTray({
  files,
  onRemove,
}: {
  files: DraftFile[];
  onRemove: (key: string) => void;
}) {
  return files.length ? (
    <div className="mb-2 flex flex-wrap gap-2" aria-label="Tệp chờ gửi">
      {files.map((f) => (
        <DraftCard key={f.key} file={f} onRemove={() => onRemove(f.key)} />
      ))}
    </div>
  ) : null;
}
