import { Compass, Workflow } from "lucide-react";

export function TemplateCard({
  name,
  description,
  kind,
  builtin = false,
  summary,
  children,
}: {
  name: string;
  description: string;
  kind: "Workflow" | "Orchestrator";
  builtin?: boolean;
  summary: React.ReactNode;
  children: React.ReactNode;
}) {
  const Icon = kind === "Workflow" ? Workflow : Compass;
  return (
    <article className="card flex h-full flex-col gap-4 p-5">
      <div className="flex items-center gap-3">
        <span className="flex size-10 shrink-0 items-center justify-center rounded-xl border border-stone-200 bg-stone-50">
          <Icon size={20} aria-hidden="true" />
        </span>
        <span className="text-xs text-stone-500">{kind}</span>
        {builtin && <span className="badge ml-auto">Có sẵn</span>}
      </div>
      <div className="flex-1">
        <h2 className="text-sm font-semibold">{name}</h2>
        <p className="mt-2 text-sm leading-6 text-stone-500">{description}</p>
      </div>
      <p className="text-xs text-stone-500">{summary}</p>
      <div className="flex flex-wrap gap-2 border-t border-stone-200 pt-4">
        {children}
      </div>
    </article>
  );
}
