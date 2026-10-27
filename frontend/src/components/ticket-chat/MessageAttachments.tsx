"use client";
import { ChatImage } from "@/components/ui-app/chat-image";
import { assetUrl } from "@/lib/api";
import type { Attachment } from "./types";
export function MessageAttachments({ files }: { files: Attachment[] }) {
  return (
    <>
      <div className="mt-2 flex flex-wrap gap-2">
        {files.map((f) => {
          const url = assetUrl(f.url || `/api/attachments/${f.id}`);
          return f.mime?.startsWith("image/") ? (
            <ChatImage
              key={f.id}
              src={url}
              alt={f.filename}
              filename={f.filename}
              thumbnailClassName="h-auto w-auto max-h-40 max-w-64 rounded-lg border border-stone-200"
            />
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
    </>
  );
}
