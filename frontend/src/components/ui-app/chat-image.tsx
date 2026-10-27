"use client";

import Image from "next/image";
import { Download, X } from "lucide-react";
import {
  Dialog,
  DialogClose,
  DialogContent,
  DialogDescription,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";

export function ChatImage({
  src,
  alt,
  filename = "screenshot.png",
  thumbnailClassName = "h-auto w-full rounded border border-stone-200",
}: {
  src: string;
  alt: string;
  filename?: string;
  thumbnailClassName?: string;
}) {
  return (
    <Dialog>
      <span className="relative inline-block max-w-full align-top">
        <DialogTrigger
          type="button"
          aria-label={`Phóng to ${alt}`}
          className="block max-w-full cursor-zoom-in rounded-lg focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-sky-600"
        >
          <Image
            unoptimized
            src={src}
            alt={alt}
            width={1280}
            height={720}
            className={thumbnailClassName}
          />
        </DialogTrigger>
        <a
          href={src}
          download={filename}
          aria-label={`Tải ảnh ${alt}`}
          title="Tải ảnh"
          className="absolute right-2 top-2 flex items-center gap-1 rounded-md border border-stone-200 bg-white/95 px-2 py-1.5 text-xs font-medium text-stone-700 shadow-sm hover:bg-white focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-sky-600"
        >
          <Download size={14} aria-hidden="true" />
          Tải ảnh
        </a>
      </span>
      <DialogContent
        showCloseButton={false}
        className="!flex !h-[90dvh] !w-[96vw] !max-w-[1400px] !flex-col !gap-0 overflow-hidden !p-0"
      >
        <header className="flex shrink-0 items-center gap-2 border-b border-stone-200 p-3">
          <DialogTitle className="min-w-0 flex-1 truncate text-sm font-semibold">
            {alt}
          </DialogTitle>
          <a
            href={src}
            download={filename}
            className="btn btn-light shrink-0 gap-2"
            aria-label="Tải ảnh xuống"
          >
            <Download size={16} aria-hidden="true" />
            Tải ảnh
          </a>
          <DialogClose
            className="btn btn-light shrink-0 !p-2"
            aria-label="Đóng ảnh phóng to"
          >
            <X size={18} aria-hidden="true" />
          </DialogClose>
        </header>
        <DialogDescription className="sr-only">
          Xem ảnh phóng to và tải ảnh về máy. Nhấn Escape để đóng.
        </DialogDescription>
        <div className="flex min-h-0 flex-1 items-center justify-center overflow-auto bg-stone-100 p-2">
          <Image
            unoptimized
            src={src}
            alt={`Ảnh phóng to: ${alt}`}
            width={1280}
            height={720}
            className="h-full w-full object-contain"
          />
        </div>
      </DialogContent>
    </Dialog>
  );
}
