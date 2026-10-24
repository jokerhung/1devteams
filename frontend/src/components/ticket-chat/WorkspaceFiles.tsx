"use client";

import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { ArrowUp, FileText, Folder, RotateCw, X } from "lucide-react";
import { apiFetch } from "@/lib/api";

type Listing = {
  path: string;
  entries: { name: string; path: string; kind: "directory" | "file" }[];
  truncated: boolean;
};
type TextFile = { path: string; content: string; size: number };

export function WorkspaceFiles({
  projectId,
  onClose,
}: {
  projectId: string;
  onClose: () => void;
}) {
  const [directory, setDirectory] = useState("");
  const [selected, setSelected] = useState<string | null>(null);
  const listing = useQuery({
    queryKey: ["workspace-files", projectId, directory],
    queryFn: ({ signal }) =>
      apiFetch<Listing>(
        `/projects/${projectId}/files?path=${encodeURIComponent(directory)}`,
        { signal },
      ),
    retry: false,
  });
  const file = useQuery({
    queryKey: ["workspace-file", projectId, selected],
    queryFn: ({ signal }) =>
      apiFetch<TextFile>(
        `/projects/${projectId}/file?path=${encodeURIComponent(selected!)}`,
        { signal },
      ),
    enabled: selected !== null,
    retry: false,
    gcTime: 0,
  });
  function refresh() {
    void listing.refetch();
    if (selected) void file.refetch();
  }
  return (
    <aside
      id="ticket-files-panel"
      aria-label="File workspace"
      className="flex h-full min-h-0 w-[45%] min-w-[min(280px,75%)] max-w-[640px] shrink-0 flex-col border-l border-stone-200 bg-stone-50"
    >
      <header className="flex shrink-0 items-center gap-2 border-b border-stone-200 px-3 py-2 text-xs">
        <Folder size={15} aria-hidden="true" />
        <b className="flex-1">Files</b>
        <button
          type="button"
          className="btn btn-light"
          title="Tải lại file"
          aria-label="Tải lại file"
          onClick={refresh}
        >
          <RotateCw size={15} aria-hidden="true" />
        </button>
        <button
          type="button"
          className="btn btn-light"
          title="Đóng panel file"
          aria-label="Đóng panel file"
          onClick={onClose}
        >
          <X size={15} aria-hidden="true" />
        </button>
      </header>
      <nav
        aria-label="Thư mục workspace"
        className="flex shrink-0 items-center gap-2 border-b px-2 py-1 text-xs"
      >
        <button
          type="button"
          className="btn btn-light shrink-0"
          aria-label="Lên thư mục cha"
          disabled={!directory}
          onClick={() =>
            setDirectory(directory.split("/").slice(0, -1).join("/"))
          }
        >
          <ArrowUp size={14} aria-hidden="true" />
        </button>
        <button
          type="button"
          className="shrink-0 text-sky-700"
          onClick={() => setDirectory("")}
        >
          Workspace
        </button>
        <span className="truncate text-stone-500" title={directory}>
          / {directory}
        </span>
      </nav>
      <div className="h-[35%] min-h-20 shrink-0 overflow-auto overscroll-contain border-b border-stone-200 p-1">
        {listing.isFetching && (
          <p role="status" className="p-2 text-xs text-stone-500">
            Đang tải thư mục…
          </p>
        )}
        {listing.error && (
          <p role="alert" className="p-2 text-xs text-red-700">
            {listing.error.message}
          </p>
        )}
        {!listing.isPending &&
          !listing.error &&
          !listing.data?.entries.length && (
            <p className="p-2 text-xs text-stone-500">Thư mục trống</p>
          )}
        {listing.data?.entries.map((entry) => (
          <button
            type="button"
            key={entry.path}
            className={`flex min-h-9 w-full items-center gap-2 rounded px-2 py-1 text-left text-xs hover:bg-stone-200 ${selected === entry.path ? "bg-sky-100 text-sky-900" : ""}`}
            title={entry.path}
            aria-pressed={
              entry.kind === "file" ? selected === entry.path : undefined
            }
            onClick={() =>
              entry.kind === "directory"
                ? setDirectory(entry.path)
                : setSelected(entry.path)
            }
          >
            {entry.kind === "directory" ? (
              <Folder
                size={15}
                className="shrink-0 text-amber-600"
                aria-hidden="true"
              />
            ) : (
              <FileText
                size={15}
                className="shrink-0 text-stone-500"
                aria-hidden="true"
              />
            )}
            <span className="truncate">{entry.name}</span>
          </button>
        ))}
        {listing.data?.truncated && (
          <p className="p-2 text-xs text-amber-700">
            Chỉ hiển thị 1.000 mục đầu tiên trong thư mục.
          </p>
        )}
      </div>
      <div className="flex min-h-0 flex-1 flex-col bg-white">
        {selected ? (
          <>
            <div className="shrink-0 border-b px-3 py-2 text-xs">
              <p className="truncate font-mono" title={selected}>
                {selected}
              </p>
              {file.data && (
                <span className="text-stone-400">
                  {file.data.size.toLocaleString()} bytes · Chỉ đọc
                </span>
              )}
            </div>
            {file.isFetching && (
              <p role="status" className="p-3 text-xs text-stone-500">
                Đang tải file…
              </p>
            )}
            {file.error && (
              <p role="alert" className="p-3 text-xs text-red-700">
                {file.error.message}
              </p>
            )}
            {file.data && !file.error && (
              <pre
                aria-label="Nội dung file"
                tabIndex={0}
                className="min-h-0 flex-1 overflow-auto overscroll-contain p-3 font-mono text-xs leading-5 select-text"
              >
                {file.data.content || "(File trống)"}
              </pre>
            )}
          </>
        ) : (
          <p className="p-3 text-xs text-stone-500">
            Chọn file để xem nội dung dạng text.
          </p>
        )}
      </div>
    </aside>
  );
}
