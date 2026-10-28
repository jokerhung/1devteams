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
import { allProjects } from "@/lib/projects";
import { keys } from "@/lib/query-keys";
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
  const [selected, setSelected] = useState("");
  const [createdProject, setCreatedProject] = useState("");
  const projects = useQuery({
    queryKey: [...keys.projects, "list"],
    queryFn: allProjects,
  });
  useEffect(() => {
    try {
      setSelected(localStorage.getItem("lastProjectId") || "");
    } catch {
      /* Storage is optional. */
    }
  }, []);
  useEffect(() => {
    if (routeProject) setSelected(routeProject);
  }, [routeProject]);
  const projectId =
    projects.data?.items.find((p) => p.id === (routeProject || selected))?.id ||
    "";
  useEffect(() => {
    if (tools.terminalOpen && projectId) setCreatedProject(projectId);
  }, [tools.terminalOpen, projectId]);
  const showTools = tools.terminalOpen;
  return (
    <div className="flex min-h-0 min-w-0 flex-1 flex-col overflow-hidden rounded-2xl border border-stone-300/80 bg-white shadow-sm">
      {showTools && (
        <div className="flex shrink-0 flex-wrap items-center gap-2 border-b border-stone-200 px-4 py-2 text-xs max-lg:pt-14">
          <label htmlFor="tools-project">Workspace</label>
          <select
            id="tools-project"
            aria-label="Project cho terminal"
            className="inp !w-auto max-w-full text-xs"
            value={projectId}
            disabled={!!routeProject}
            onChange={(event) => {
              setSelected(event.target.value);
              try {
                localStorage.setItem("lastProjectId", event.target.value);
              } catch {
                /* Storage is optional. */
              }
            }}
          >
            <option value="">Chọn project</option>
            {projects.data?.items.map((project) => (
              <option key={project.id} value={project.id}>
                {project.name}
              </option>
            ))}
          </select>
          {projects.error ? (
            <span role="alert" className="text-red-700">
              {projects.error.message}
            </span>
          ) : (
            !projectId && (
              <span className="text-stone-500">
                Chọn project để mở terminal.
              </span>
            )
          )}
        </div>
      )}
      <div className="flex min-h-0 min-w-0 flex-1 overflow-hidden">
        <TerminalDock
          projectId={projectId}
          open={tools.terminalOpen && !!projectId}
          created={!!projectId && createdProject === projectId}
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
