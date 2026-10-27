"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  Activity,
  ClipboardList,
  FolderOpen,
  Plug,
  Settings2,
} from "lucide-react";

const sections = [
  { value: "workspaces", label: "Thư mục", icon: FolderOpen },
  { value: "adapters", label: "Adapter", icon: Plug },
  { value: "operations", label: "Vận hành", icon: Activity },
  { value: "audit", label: "Nhật ký", icon: ClipboardList },
];

export default function SettingsLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  const pathname = usePathname();
  const active = pathname.split("/")[2] || "adapters";
  return (
    <div className="mx-auto w-full max-w-6xl">
      <header className="mb-7 flex items-start gap-3">
        <span className="flex size-11 shrink-0 items-center justify-center rounded-xl border border-stone-200 bg-stone-50 text-stone-600">
          <Settings2 size={21} aria-hidden="true" />
        </span>
        <div>
          <h1 className="text-2xl font-semibold tracking-tight text-stone-900">
            Settings
          </h1>
          <p className="mt-1 text-sm text-stone-500">
            Quản lý thư mục truy cập, adapter và hoạt động hệ thống.
          </p>
        </div>
      </header>
      <div className="flex min-w-0 items-start gap-3 sm:gap-6 lg:gap-8">
        <nav
          aria-label="Cài đặt hệ thống"
          className="sticky top-0 w-24 shrink-0 space-y-1 sm:w-44"
        >
          <p className="mb-3 hidden px-3 text-[10px] font-semibold uppercase tracking-wider text-stone-400 sm:block">
            Hệ thống
          </p>
          {sections.map(({ value, label, icon: Icon }) => (
            <Link
              key={value}
              href={`/settings/${value}`}
              scroll={false}
              aria-current={active === value ? "page" : undefined}
              className={`flex min-h-11 items-center gap-2 rounded-lg px-2 py-2.5 text-xs outline-none transition-colors focus-visible:ring-2 focus-visible:ring-stone-400 sm:px-3 sm:text-sm ${active === value ? "bg-stone-100 font-semibold text-stone-900" : "text-stone-500 hover:bg-stone-50 hover:text-stone-900"}`}
            >
              <Icon size={16} aria-hidden="true" className="shrink-0" /> {label}
            </Link>
          ))}
        </nav>
        <div className="min-h-[420px] min-w-0 flex-1 border-l border-stone-200 pl-3 sm:pl-6 lg:pl-8">
          {children}
        </div>
      </div>
    </div>
  );
}
