"use client";
import { useId, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { ArrowUp, Folder, FolderOpen, X } from "lucide-react";
import { apiFetch } from "@/lib/api";

type DirectoryListing = {
  path: string | null;
  parent: string | null;
  directories: { name: string; path: string }[];
};

export function WorkspacePathField({
  label = "Đường dẫn thư mục local",
  value,
  defaultValue = "",
  onChange,
  onBlur,
  onSelect,
}: {
  label?: string;
  value?: string;
  defaultValue?: string;
  onChange?: (path: string) => void;
  onBlur?: () => void;
  onSelect?: (path: string) => void;
}) {
  const id = useId();
  const [internal, setInternal] = useState(defaultValue);
  const selected = value ?? internal;
  const [open, setOpen] = useState(false);
  const [directory, setDirectory] = useState("");
  const listing = useQuery({
    queryKey: ["workspace-directories", directory],
    queryFn: () =>
      apiFetch<DirectoryListing>(
        `/projects/browse-workspace?path=${encodeURIComponent(directory)}`,
      ),
    enabled: open,
    retry: false,
  });
  const change = (path: string) => {
    setInternal(path);
    onChange?.(path);
  };
  return (
    <div>
      <label htmlFor={id} className="field">
        {label}
      </label>
      <div className="flex gap-2">
        <input
          id={id}
          className="inp min-w-0 flex-1 font-mono"
          name="workspace_path"
          required
          value={selected}
          onChange={(e) => change(e.target.value)}
          onBlur={onBlur}
          placeholder="D:\projects\my-app"
        />
        <button
          type="button"
          className="btn btn-light shrink-0"
          aria-label="Chọn thư mục local"
          title="Chọn thư mục local"
          aria-expanded={open}
          aria-controls={`${id}-browser`}
          onClick={() => {
            setDirectory(selected.trim());
            setOpen(!open);
          }}
        >
          <FolderOpen size={18} />
        </button>
      </div>
      {open && (
        <section
          id={`${id}-browser`}
          aria-label="Duyệt thư mục local"
          className="mt-2 rounded-xl border border-stone-200 bg-stone-50 p-3"
        >
          <div className="mb-2 flex items-center gap-2">
            <button
              type="button"
              className="btn btn-light"
              onClick={() => setDirectory("")}
            >
              Thư mục gốc
            </button>
            <button
              type="button"
              className="btn btn-light"
              disabled={!listing.data?.path || listing.isFetching}
              aria-label="Thư mục cha"
              onClick={() => setDirectory(listing.data?.parent || "")}
            >
              <ArrowUp size={14} />
            </button>
            <button
              type="button"
              className="ml-auto rounded p-1"
              aria-label="Đóng chọn thư mục"
              onClick={() => setOpen(false)}
            >
              <X size={16} />
            </button>
          </div>
          <p className="mb-2 break-all font-mono text-xs">
            {listing.data?.path || directory || "Chọn thư mục gốc"}
          </p>
          {listing.isFetching ? (
            <p role="status" className="text-xs">
              Đang đọc thư mục…
            </p>
          ) : listing.error ? (
            <p role="alert" className="error">
              {listing.error.message}. Chọn “Thư mục gốc” để duyệt lại.
            </p>
          ) : (
            <div className="max-h-52 overflow-y-auto">
              {listing.data?.directories.map((item) => (
                <button
                  key={item.path}
                  type="button"
                  className="flex w-full items-center gap-2 rounded p-2 text-left text-xs hover:bg-stone-200"
                  onClick={() => setDirectory(item.path)}
                >
                  <Folder size={16} className="shrink-0" />
                  <span className="break-all">{item.name}</span>
                </button>
              ))}
              {!listing.data?.directories.length && (
                <p className="p-2 text-xs text-stone-500">
                  Không có thư mục con.
                </p>
              )}
            </div>
          )}
          <div className="mt-3 flex justify-end">
            <button
              type="button"
              className="btn btn-dark"
              disabled={
                !listing.data?.path || listing.isFetching || !!listing.error
              }
              onClick={() => {
                const path = listing.data!.path!;
                change(path);
                onSelect?.(path);
                setOpen(false);
              }}
            >
              Chọn thư mục này
            </button>
          </div>
        </section>
      )}
    </div>
  );
}
