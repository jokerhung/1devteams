"use client";

import {
  createContext,
  useContext,
  useEffect,
  useState,
  type ReactNode,
} from "react";
import { usePathname } from "next/navigation";
import { useQuery } from "@tanstack/react-query";
import { TerminalDock } from "@/components/ticket-chat/TerminalDock";
import { WorkspaceFiles } from "@/components/ticket-chat/WorkspaceFiles";
import { apiFetch } from "@/lib/api";
import { AgentChat } from "./agent-chat";

type Tools = {
  terminalOpen: boolean;
  filesOpen: boolean;
  chatOpen: boolean;
  toggleTerminal: () => void;
  toggleFiles: () => void;
  toggleChat: () => void;
};
const Context = createContext<Tools | null>(null);
export function useWorkspaceTools() {
  const value = useContext(Context);
  if (!value) throw new Error("Workspace tools provider is missing");
  return value;
}

export function WorkspaceToolsProvider({ children }: { children: ReactNode }) {
  const [terminalOpen, setTerminalOpen] = useState(false);
  const [filesOpen, setFilesOpen] = useState(false);
  const [chatOpen, setChatOpen] = useState(false);
  return (
    <Context.Provider
      value={{
        terminalOpen,
        filesOpen,
        chatOpen,
        toggleTerminal: () => setTerminalOpen((v) => !v),
        toggleFiles: () => setFilesOpen((v) => !v),
        toggleChat: () => setChatOpen((v) => !v),
      }}
    >
      {children}
    </Context.Provider>
  );
}

export function WorkspaceToolsArea({ children }: { children: ReactNode }) {
  const tools = useWorkspaceTools();
  const pathname = usePathname();
  const routeProject = pathname.match(/^\/projects\/([^/]+)/)?.[1];
  const [createdTarget, setCreatedTarget] = useState("");
  const workspace = useQuery({
    queryKey: ["workspace-terminal"],
    queryFn: ({ signal }) =>
      apiFetch<{ enabled: boolean; workspace: string }>("/workspace-terminal", {
        signal,
      }),
    enabled: tools.terminalOpen && !routeProject,
    retry: false,
  });
  const target = routeProject
    ? `project:${routeProject}`
    : workspace.data && !workspace.error
      ? `workspace:${workspace.data.workspace}`
      : "";
  useEffect(() => {
    if (tools.terminalOpen && target) setCreatedTarget(target);
  }, [tools.terminalOpen, target]);
  const showTools = tools.terminalOpen;
  return (
    <div className="flex min-h-0 min-w-0 flex-1 flex-col overflow-hidden rounded-2xl border border-stone-300/80 bg-white shadow-sm">
      {showTools && (
        <div className="flex shrink-0 flex-wrap items-center gap-2 border-b border-stone-200 px-4 py-2 text-xs max-lg:pt-14">
          <span>Workspace</span>
          <span
            className="truncate font-medium"
            title={!routeProject ? workspace.data?.workspace : undefined}
          >
            {routeProject ? "Project hiện tại" : workspace.data?.workspace}
          </span>
          {!routeProject && workspace.error ? (
            <span role="alert" className="text-red-700">
              {workspace.error.message}
            </span>
          ) : (
            !routeProject &&
            workspace.isPending && (
              <span className="text-stone-500">
                Đang lấy thư mục cho phép đầu tiên…
              </span>
            )
          )}
        </div>
      )}
      <div className="flex min-h-0 min-w-0 flex-1 overflow-hidden">
        <TerminalDock
          projectId={routeProject}
          workspace={!routeProject ? workspace.data?.workspace : undefined}
          open={tools.terminalOpen && !!target}
          created={!!target && createdTarget === target}
          onClose={tools.toggleTerminal}
        >
          {children}
        </TerminalDock>
        {tools.filesOpen && (
          <WorkspaceFiles
            key={routeProject || "allowed-roots"}
            projectId={routeProject}
            onClose={tools.toggleFiles}
          />
        )}
        <AgentChat
          open={tools.chatOpen}
          onClose={tools.toggleChat}
          contextProjectId={routeProject}
        />
      </div>
    </div>
  );
}
