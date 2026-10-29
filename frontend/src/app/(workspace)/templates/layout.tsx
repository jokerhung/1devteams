"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { Compass, Workflow } from "lucide-react";
import { PageHeader } from "@/components/ui-app/primitives";

export default function TemplatesLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  const pathname = usePathname();
  const catalog =
    pathname === "/templates" || pathname === "/templates/orchestrators";
  if (!catalog) return children;

  return (
    <section className="mx-auto max-w-6xl">
      <PageHeader
        title="Template"
        description="Quản lý mẫu Workflow và Orchestrator để áp dụng cho các project."
      />
      <nav
        aria-label="Loại template"
        className="mb-6 flex gap-1 border-b border-stone-200"
      >
        {[
          { href: "/templates", label: "Workflow", Icon: Workflow },
          {
            href: "/templates/orchestrators",
            label: "Orchestrator",
            Icon: Compass,
          },
        ].map(({ href, label, Icon }) => (
          <Link
            key={href}
            href={href}
            aria-current={pathname === href ? "page" : undefined}
            className={`-mb-px flex items-center gap-2 border-b-2 px-4 py-3 text-sm font-medium transition-colors focus-visible:outline-2 focus-visible:outline-offset-2 ${pathname === href ? "border-stone-900 text-stone-900" : "border-transparent text-stone-500 hover:border-stone-300 hover:text-stone-800"}`}
          >
            <Icon size={16} aria-hidden="true" />
            {label}
          </Link>
        ))}
      </nav>
      {children}
    </section>
  );
}
