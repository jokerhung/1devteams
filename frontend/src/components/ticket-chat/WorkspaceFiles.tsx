"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import {
  ArrowUp,
  Code2,
  Eye,
  FileText,
  Folder,
  Maximize2,
  RotateCw,
  X,
} from "lucide-react";
import { apiFetch } from "@/lib/api";
import { MarkdownContent } from "./blocks/MarkdownContent";
import {
  Dialog,
  DialogClose,
  DialogContent,
  DialogDescription,
  DialogTitle,
} from "@/components/ui/dialog";

type Listing = {
  path: string;
  entries: { name: string; path: string; kind: "directory" | "file" }[];
  truncated: boolean;
};
type TextFile = { path: string; content: string; size: number };

export function WorkspaceFiles({
  projectId,
  initialDirectory = "",
  onClose,
}: {
  projectId?: string;
  initialDirectory?: string;
  onClose: () => void;
}) {
  const [width, setWidth] = useState(280);
  const [bounds, setBounds] = useState({ min: 280, max: 800 });
  const [resizing, setResizing] = useState(false);
  const panel = useRef<HTMLElement>(null);
  const drag = useRef<{ pointerId: number; x: number; width: number } | null>(
    null,
  );
  useEffect(() => {
    const container = panel.current?.parentElement;
    if (!container) return;
    const observer = new ResizeObserver(() => {
      const max = Math.max(
        1,
        Math.floor(Math.min(800, container.clientWidth * 0.75)),
      );
      setBounds({ min: Math.min(280, max), max });
    });
    observer.observe(container);
    return () => observer.disconnect();
  }, []);
  const actualWidth = Math.max(bounds.min, Math.min(bounds.max, width));
  const resize = (value: number) =>
    setWidth(Math.round(Math.max(bounds.min, Math.min(bounds.max, value))));
  const stopResize = () => {
    drag.current = null;
    setResizing(false);
  };
  const [directory, setDirectory] = useState(initialDirectory);
  const [root, setRoot] = useState("");
  const [selected, setSelected] = useState<string | null>(null);
  const [preview, setPreview] = useState(false);
  const [fullscreen, setFullscreen] = useState(false);
  const isMarkdown = /\.(md|markdown)$/i.test(selected || "");
  const listing = useQuery({
    queryKey: ["workspace-files", projectId, root, directory],
    queryFn: ({ signal }) =>
      apiFetch<Listing>(
        projectId
          ? `/projects/${projectId}/files?path=${encodeURIComponent(directory)}`
          : `/projects/workspace-files?root=${encodeURIComponent(root)}&path=${encodeURIComponent(directory)}`,
        { signal },
      ),
    retry: false,
  });
  const file = useQuery({
    queryKey: ["workspace-file", projectId, root, selected],
    queryFn: ({ signal }) =>
      apiFetch<TextFile>(
        projectId
          ? `/projects/${projectId}/file?path=${encodeURIComponent(selected!)}`
          : `/projects/workspace-file?root=${encodeURIComponent(root)}&path=${encodeURIComponent(selected!)}`,
        { signal },
      ),
    enabled: selected !== null,
    retry: false,
    gcTime: 0,
  });
  const lineNumbers = useMemo(
    () =>
      Array.from(
        { length: (file.data?.content || "").split(/\r\n|\n|\r/).length },
        (_, index) => index + 1,
      ).join("\n"),
    [file.data?.content],
  );
  function refresh() {
    void listing.refetch();
    if (selected) void file.refetch();
  }
  const previewButton = (
    <button
      type="button"
      className="btn btn-light shrink-0"
      disabled={!isMarkdown || !file.data}
      aria-label={preview ? "Xem mã nguồn" : "Xem trước Markdown"}
      title={preview ? "Xem mã nguồn" : "Xem trước Markdown"}
      aria-pressed={preview && isMarkdown}
      onClick={() => setPreview((value) => !value)}
    >
      {preview && isMarkdown ? (
        <Code2 size={15} aria-hidden="true" />
      ) : (
        <Eye size={15} aria-hidden="true" />
      )}
    </button>
  );
  const content = (
    <>
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
      {file.data &&
        !file.error &&
        (preview && isMarkdown ? (
          <div
            aria-label="Xem trước Markdown"
            tabIndex={0}
            className="min-h-0 flex-1 overflow-auto overscroll-contain p-4 select-text [&_h1]:text-2xl [&_h1]:font-bold [&_h2]:text-xl [&_h2]:font-semibold [&_h3]:text-lg [&_h3]:font-semibold [&_blockquote]:border-l-2 [&_blockquote]:border-stone-300 [&_blockquote]:pl-3 [&_hr]:my-4"
          >
            <MarkdownContent text={file.data.content || "(File trống)"} />
          </div>
        ) : (
          <div
            aria-label="Nội dung file"
            tabIndex={0}
            className="min-h-0 flex-1 overflow-auto overscroll-contain font-mono text-xs leading-5 select-text"
          >
            <div className="flex min-h-full w-max min-w-full items-stretch">
              <div
                aria-hidden="true"
                className="sticky left-0 shrink-0 border-r border-stone-200 bg-stone-50 px-3 py-3 text-right whitespace-pre text-stone-400 select-none"
              >
                {lineNumbers}
              </div>
              <pre className="m-0 flex-1 px-3 py-3 font-[inherit] text-[inherit] leading-[inherit]">
                {file.data.content || "(File trống)"}
              </pre>
            </div>
          </div>
        ))}
    </>
  );
  return (
    <aside
      ref={panel}
      id="ticket-files-panel"
      aria-label="File workspace"
      style={{ width: actualWidth }}
      className={`relative flex h-full min-h-0 min-w-0 max-w-[75%] shrink-0 flex-col border-l border-stone-200 bg-stone-50 ${resizing ? "select-none" : ""}`}
    >
      <div
        role="separator"
        aria-label="Đổi chiều rộng panel file"
        aria-orientation="vertical"
        aria-controls="ticket-files-panel"
        aria-valuemin={bounds.min}
        aria-valuemax={bounds.max}
        aria-valuenow={actualWidth}
        tabIndex={0}
        title="Kéo để đổi chiều rộng panel file"
        className="group absolute inset-y-0 -left-1.5 z-20 flex w-3 touch-none cursor-col-resize items-center justify-center outline-none hover:bg-sky-100/60 focus-visible:bg-sky-100"
        onPointerDown={(event) => {
          if (event.button !== 0 || drag.current) return;
          event.preventDefault();
          event.currentTarget.setPointerCapture(event.pointerId);
          drag.current = {
            pointerId: event.pointerId,
            x: event.clientX,
            width: actualWidth,
          };
          setResizing(true);
        }}
        onPointerMove={(event) => {
          if (drag.current?.pointerId === event.pointerId)
            resize(drag.current.width + drag.current.x - event.clientX);
        }}
        onPointerUp={(event) => {
          if (drag.current?.pointerId !== event.pointerId) return;
          stopResize();
          if (event.currentTarget.hasPointerCapture(event.pointerId))
            event.currentTarget.releasePointerCapture(event.pointerId);
        }}
        onPointerCancel={stopResize}
        onLostPointerCapture={stopResize}
        onKeyDown={(event) => {
          const next = (
            {
              ArrowLeft: actualWidth + 20,
              ArrowRight: actualWidth - 20,
              Home: bounds.min,
              End: bounds.max,
            } as Record<string, number>
          )[event.key];
          if (next !== undefined) {
            event.preventDefault();
            resize(next);
          }
        }}
      >
        <span className="h-10 w-1 rounded-full bg-stone-300 group-hover:bg-sky-400 group-focus-visible:bg-sky-400" />
      </div>
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
          disabled={!directory && !root}
          onClick={() => {
            if (directory)
              setDirectory(directory.split("/").slice(0, -1).join("/"));
            else {
              setRoot("");
              setSelected(null);
            }
          }}
        >
          <ArrowUp size={14} aria-hidden="true" />
        </button>
        <button
          type="button"
          className="shrink-0 text-sky-700"
          onClick={() => {
            setDirectory("");
            if (!projectId) {
              setRoot("");
              setSelected(null);
            }
          }}
        >
          {projectId ? "Workspace" : "Thư mục cho phép"}
        </button>
        <span
          className="truncate text-stone-500"
          title={root ? `${root}/${directory}` : directory}
        >
          {root
            ? `${root}${directory ? ` / ${directory}` : ""}`
            : `/ ${directory}`}
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
            <p className="p-2 text-xs text-stone-500">
              {!projectId && !root
                ? "Không có thư mục được phép truy cập."
                : "Thư mục trống"}
            </p>
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
            onClick={() => {
              if (entry.kind === "directory") {
                if (!projectId && !root) {
                  setRoot(entry.path);
                  setDirectory("");
                  setSelected(null);
                } else setDirectory(entry.path);
              } else {
                setSelected(entry.path);
                setPreview(false);
              }
            }}
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
              <div className="flex min-w-0 items-center gap-2">
                <p
                  className="min-w-0 flex-1 truncate font-mono"
                  title={selected}
                >
                  {selected}
                </p>
                <div className="ml-auto flex shrink-0 items-center gap-1">
                  {previewButton}
                  <button
                    type="button"
                    className="btn btn-light shrink-0"
                    title="Phóng to file"
                    aria-label="Phóng to file"
                    onClick={() => setFullscreen(true)}
                  >
                    <Maximize2 size={15} aria-hidden="true" />
                  </button>
                </div>
              </div>
              {file.data && (
                <span className="text-stone-400">
                  {file.data.size.toLocaleString()} bytes · Chỉ đọc
                </span>
              )}
            </div>
            {!fullscreen && content}
          </>
        ) : (
          <p className="p-3 text-xs text-stone-500">
            Chọn file để xem nội dung dạng text.
          </p>
        )}
      </div>
      <Dialog open={fullscreen} onOpenChange={setFullscreen}>
        <DialogContent
          showCloseButton={false}
          className="!flex !h-dvh !w-screen !max-w-none !flex-col !gap-0 !rounded-none !p-0"
        >
          <header className="flex shrink-0 items-center gap-2 border-b border-stone-200 px-4 py-3">
            <FileText size={18} className="shrink-0" aria-hidden="true" />
            <DialogTitle
              className="min-w-0 flex-1 truncate font-mono text-sm"
              title={selected || ""}
            >
              {selected}
            </DialogTitle>
            {previewButton}
            <DialogClose
              className="btn btn-light shrink-0"
              aria-label="Đóng cửa sổ file"
              title="Đóng cửa sổ file"
            >
              <X size={16} aria-hidden="true" />
            </DialogClose>
          </header>
          <DialogDescription className="sr-only">
            Nội dung file chỉ đọc. Nhấn Escape để đóng cửa sổ.
          </DialogDescription>
          <div className="flex min-h-0 flex-1 flex-col bg-white">
            {fullscreen && content}
          </div>
        </DialogContent>
      </Dialog>
    </aside>
  );
}
