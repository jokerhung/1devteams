import { Sidebar } from "@/components/ui-app/sidebar";
export default function WorkspaceLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <div className="flex h-dvh overflow-hidden p-2.5">
      <Sidebar />
      <main
        id="main-content"
        className="min-w-0 flex-1 overflow-y-auto rounded-2xl border border-stone-300/80 bg-white px-5 py-6 shadow-sm max-lg:pt-14 lg:px-8 lg:py-7"
      >
        {children}
      </main>
    </div>
  );
}
