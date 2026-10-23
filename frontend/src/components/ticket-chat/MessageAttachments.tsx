"use client";
/* eslint-disable @next/next/no-img-element -- Authenticated attachment URLs cannot use the public image optimizer. */
import { useState } from "react";
import { Modal } from "@/components/ui-app/primitives";
import { assetUrl } from "@/lib/api";
import type { Attachment } from "./types";
export function MessageAttachments({ files }: { files: Attachment[] }) {
  const [preview, setPreview] = useState<Attachment | null>(null);
  return (
    <>
      <div className="mt-2 flex flex-wrap gap-2">
        {files.map((f) => {
          const url = assetUrl(f.url || `/api/attachments/${f.id}`);
          return f.mime?.startsWith("image/") ? (
            <button
              key={f.id}
              onClick={() => setPreview(f)}
              aria-label={`Phóng to ${f.filename}`}
            >
              <img
                src={url}
                alt={f.filename}
                className="max-h-40 max-w-64 rounded-lg border border-stone-200"
              />
            </button>
          ) : (
            <a
              key={f.id}
              href={url}
              download={f.filename}
              className="rounded-lg border border-stone-200 p-3 text-xs"
            >
              📄 {f.filename}{" "}
              {f.size != null && `· ${(f.size / 1024).toFixed(1)} KB`}
            </a>
          );
        })}
      </div>
      {preview && (
        <Modal title={preview.filename} wide onClose={() => setPreview(null)}>
          <img
            src={assetUrl(preview.url || `/api/attachments/${preview.id}`)}
            alt={preview.filename}
            className="max-h-[75vh] w-full object-contain"
          />
        </Modal>
      )}
    </>
  );
}
