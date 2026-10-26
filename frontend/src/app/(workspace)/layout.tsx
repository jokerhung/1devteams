import { Sidebar } from "@/components/ui-app/sidebar";
import {
  WorkspaceToolsProvider,
  WorkspaceToolsArea,
} from "@/components/ui-app/workspace-tools";
export default function WorkspaceLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <WorkspaceToolsProvider>
      <div className="flex h-dvh overflow-hidden p-2.5">
        <Sidebar />
        <WorkspaceToolsArea>
          <main
            id="main-content"
            className="min-h-0 min-w-0 flex-1 overflow-y-auto px-5 py-6 max-lg:pt-14 lg:px-8 lg:py-7"
          >
            {children}
          </main>
        </WorkspaceToolsArea>
      </div>
    </WorkspaceToolsProvider>
  );
}
