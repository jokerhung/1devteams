"use client";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import {
  Bell,
  Bot,
  Folder,
  ChevronDown,
  ChevronRight,
  Plus,
  GitBranch,
  LogOut,
  Settings2,
  Menu,
  PanelLeftClose,
  PanelLeftOpen,
  X,
} from "lucide-react";
import { apiFetch } from "@/lib/api";
import {
  DropdownMenu,
  DropdownMenuTrigger,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
} from "@/components/ui/dropdown-menu";
import { toast } from "sonner";
import { keys } from "@/lib/query-keys";
import { allProjects } from "@/lib/projects";
import type { Agent, Team, Project, ProjectTree, User } from "@/lib/types";
import { useRealtime } from "@/lib/realtime";
import { Modal, StatusBadge, UserAvatar, ErrorState } from "./primitives";
import { ProjectDialog } from "./project-dialog";
import { CreateTicketDialog } from "./ticket-dialog";
import { AppBrand } from "./app-brand";
export function recentProjects(projects: Project[], currentId?: string) {
  const sorted = [...projects].sort(
    (a, b) =>
      b.last_activity_at.localeCompare(a.last_activity_at) ||
      a.id.localeCompare(b.id),
  );
  const recent = sorted.slice(0, 5);
  const current = sorted.find((p) => p.id === currentId);
  return current && !recent.some((p) => p.id === current.id)
    ? [...recent.slice(0, 4), current]
    : recent;
}
function useOpen(key: string) {
  const [open, setOpen] = useState(false);
  useEffect(() => {
    setOpen(localStorage.getItem(key) === "true");
  }, [key]);
  return [
    open,
    (value: boolean) => {
      localStorage.setItem(key, String(value));
      setOpen(value);
    },
  ] as const;
}
function WorkflowTree({
  flow,
  pid,
}: {
  flow: ProjectTree["workflows"][number];
  pid: string;
}) {
  const pathname = usePathname();
  const [open, setOpen] = useOpen(`sidebar.workflow.${flow.id}`);
  const [ticketDialog, setTicketDialog] = useState(false);
  return (
    <div>
      <div className="flex items-center">
        <button
          className="p-1"
          aria-label={`${open ? "Thu gọn" : "Mở"} workflow ${flow.name}`}
          onClick={() => setOpen(!open)}
        >
          {open ? <ChevronDown size={12} /> : <ChevronRight size={12} />}
        </button>
        <Link
          href={`/projects/${pid}/workflows/${flow.id}`}
          className="side-item flex-1 !gap-1.5 !px-1 text-xs"
        >
          <GitBranch size={13} />
          <span className="truncate">{flow.name}</span>
          <span className="text-[10px] text-stone-500">
            {flow.prefix}
            {flow.status === "DRAFT" && " · nháp"}
          </span>
        </Link>
        {flow.status === "PUBLISHED" && (
          <button
            aria-label={`Tạo ticket ${flow.name}`}
            title="Tạo ticket"
            className="rounded p-1 hover:bg-stone-300/50"
            onClick={() => setTicketDialog(true)}
          >
            <Plus size={14} />
          </button>
        )}
      </div>
      {open && (
        <div className="ml-3 border-l border-stone-400/20 pl-1">
          {flow.tickets.length === 0 && (
            <p className="px-3 py-1 text-[11px] text-stone-500">
              Chưa có ticket
            </p>
          )}
          {flow.tickets.slice(0, 15).map((ticket) => (
            <Link
              key={ticket.id}
              title={ticket.title}
              className={`side-item !gap-1 !py-1 text-[11px] ${pathname.endsWith(ticket.id) ? "active" : ""}`}
              href={`/projects/${pid}/workflows/${flow.id}/tickets/${ticket.id}`}
            >
              <span className="truncate"># {ticket.channel_slug}</span>
              <StatusBadge status={ticket.status} />
            </Link>
          ))}
          {flow.tickets.length >= 15 && (
            <Link
              className="side-item text-[11px]"
              href={`/projects/${pid}/workflows/${flow.id}`}
            >
              Xem tất cả
            </Link>
          )}
        </div>
      )}
      {ticketDialog && (
        <CreateTicketDialog
          pid={pid}
          wid={flow.id}
          onClose={() => setTicketDialog(false)}
        />
      )}
    </div>
  );
}
function ProjectItem({
  project,
  current,
  onNavigate,
}: {
  project: Project;
  current: boolean;
  onNavigate: () => void;
}) {
  const [open, setOpen] = useOpen(`sidebar.open.${project.id}`);
  useEffect(() => {
    if (current) {
      localStorage.setItem(`sidebar.open.${project.id}`, "true");
      setOpen(true);
    }
  }, [current, project.id]); // eslint-disable-line react-hooks/exhaustive-deps
  const tree = useQuery({
    queryKey: keys.tree(project.id),
    queryFn: () => apiFetch<ProjectTree>(`/projects/${project.id}/tree`),
    enabled: open,
  });
  useRealtime(`projects/${project.id}`, open);
  const waiting = tree.data?.workflows.some((w) =>
    w.tickets.some((t) => t.status.startsWith("WAITING")),
  );
  return (
    <div data-testid="sidebar-project">
      <div
        className={`flex items-center rounded-lg ${current ? "bg-[#DFDDD0]/40" : ""}`}
      >
        <Link
          href={`/projects/${project.id}`}
          className="side-item flex-1"
          onClick={() => {
            setOpen(true);
            onNavigate();
          }}
        >
          <Folder className="size-4 shrink-0" />
          <span className="truncate">{project.name}</span>
          {waiting && (
            <span
              title="Có ticket chờ bạn"
              className="ml-auto size-1.5 shrink-0 rounded-full bg-amber-500"
            />
          )}
        </Link>
        <button
          aria-label={`${open ? "Thu gọn" : "Mở"} project ${project.name}`}
          aria-expanded={open}
          className="p-2"
          onClick={() => setOpen(!open)}
        >
          {open ? <ChevronDown size={13} /> : <ChevronRight size={13} />}
        </button>
      </div>
      {open && (
        <div className="ml-3 space-y-0.5 border-l border-stone-400/20 py-1 pl-2">
          <ErrorState error={tree.error} />
          {tree.isLoading && (
            <p className="p-2 text-xs text-stone-500">Đang tải…</p>
          )}
          {tree.data?.workflows.map((flow) => (
            <WorkflowTree key={flow.id} flow={flow} pid={project.id} />
          ))}
          {tree.data?.workflows.length === 0 && (
            <p className="px-2 py-1 text-[11px] text-stone-500">
              Chưa có workflow.
            </p>
          )}
          <Link
            className="side-item !py-1 text-[11px] text-stone-500"
            href={`/projects/${project.id}/workflows/new`}
          >
            <Plus size={12} />
            {tree.data?.workflows.length === 0
              ? "Tạo workflow đầu tiên"
              : "Thêm workflow"}
          </Link>
        </div>
      )}
    </div>
  );
}
export function Sidebar() {
  const pathname = usePathname();
  const router = useRouter();
  const currentId = pathname.match(/^\/projects\/([^/]+)/)?.[1];
  const [mobile, setMobile] = useState(false);
  const [create, setCreate] = useState(false);
  const [all, setAll] = useState(false);
  const [loggingOut, setLoggingOut] = useState(false);
  const [collapsed, setCollapsed] = useOpen("sidebar.collapsed");
  const compact = collapsed && !mobile;
  const projects = useQuery({
    queryKey: [...keys.projects, "list"],
    queryFn: allProjects,
  });
  const agents = useQuery({
    queryKey: keys.agents,
    queryFn: () => apiFetch<Agent[]>("/agents"),
  });
  const teams = useQuery({
    queryKey: keys.teams,
    queryFn: () => apiFetch<Team[]>("/teams"),
  });
  const me = useQuery({
    queryKey: keys.me,
    queryFn: () => apiFetch<User>("/auth/me"),
  });
  const count = useQuery({
    queryKey: keys.count,
    queryFn: () => apiFetch<{ open: number }>("/notifications/unread-count"),
    refetchInterval: 30000,
  });
  const health = useQuery({
    queryKey: keys.health,
    queryFn: () =>
      apiFetch<{ acp: { claude: boolean; codex: boolean } }>("/health"),
    refetchInterval: 30000,
  });
  useRealtime("users/me");
  useEffect(() => {
    if (currentId) localStorage.setItem("lastProjectId", currentId);
  }, [currentId]);
  const connected = health.data?.acp.claude && health.data?.acp.codex;
  const current = projects.data?.items.find((p) => p.id === currentId);
  return (
    <>
      <button
        aria-label="Mở menu"
        className="fixed top-3 left-3 z-30 rounded-lg bg-[#EBE9D8] p-2 lg:hidden"
        onClick={() => setMobile(true)}
      >
        <Menu size={18} />
      </button>
      {mobile && (
        <button
          aria-label="Đóng menu"
          className="fixed inset-0 z-30 bg-black/20 lg:hidden"
          onClick={() => setMobile(false)}
        />
      )}
      <aside
        aria-label="Sidebar"
        className={`fixed inset-y-0 left-0 z-40 flex shrink-0 flex-col bg-[#EBE9D8] px-2.5 py-4 text-[13px] lg:static lg:z-auto lg:h-full lg:py-1 ${compact ? "w-16" : "w-60"} ${mobile ? "flex" : "hidden lg:flex"}`}
      >
        <div
          className={`mb-5 flex gap-2 pt-1 ${compact ? "flex-col items-center" : "items-center justify-between px-1"}`}
        >
          <Link
            href="/"
            aria-label="aiteams · Trang chủ"
            onClick={() => setMobile(false)}
            className="flex min-w-0 items-center gap-2 rounded-lg outline-none focus-visible:ring-2 focus-visible:ring-stone-400"
          >
            <span
              className="relative flex shrink-0 items-center"
              title={`Claude: ${health.data?.acp.claude ? "OK" : "lỗi"} · Codex: ${health.data?.acp.codex ? "OK" : "lỗi"}`}
            >
              <AppBrand compact={compact} />
              <span
                className={`absolute -bottom-0.5 left-[34px] size-2 rounded-full border border-[#EBE9D8] ${connected ? "bg-emerald-500" : "bg-amber-500"}`}
              />
            </span>
          </Link>
          <button
            type="button"
            className="hidden size-8 shrink-0 items-center justify-center rounded-lg text-stone-500 hover:bg-[#DFDDD0] focus-visible:ring-2 focus-visible:ring-stone-400 lg:flex"
            aria-label={compact ? "Mở rộng sidebar" : "Thu gọn sidebar"}
            title={compact ? "Mở rộng sidebar" : "Thu gọn sidebar"}
            aria-expanded={!compact}
            onClick={() => setCollapsed(!collapsed)}
          >
            {compact ? (
              <PanelLeftOpen size={17} aria-hidden="true" />
            ) : (
              <PanelLeftClose size={17} aria-hidden="true" />
            )}
          </button>
          <button
            className="lg:hidden"
            aria-label="Đóng sidebar"
            onClick={() => setMobile(false)}
          >
            <X size={16} />
          </button>
        </div>
        <nav className="space-y-0.5">
          <Link
            onClick={() => setMobile(false)}
            className={`side-item ${compact ? "justify-center !px-0" : ""} ${pathname === "/notifications" ? "active" : ""}`}
            title={compact ? "Thông báo" : undefined}
            href="/notifications"
          >
            <Bell size={16} />
            <span className={compact ? "sr-only" : undefined}>Thông báo</span>
            {!compact && !!count.data?.open && (
              <span className="ml-auto rounded-full bg-stone-800 px-1.5 font-mono text-[10px] text-white">
                {count.data.open}
              </span>
            )}
          </Link>
          <Link
            onClick={() => setMobile(false)}
            className={`side-item ${compact ? "justify-center !px-0" : ""} ${pathname === "/agents" ? "active" : ""}`}
            title={compact ? "Agents & Teams" : undefined}
            href="/agents"
          >
            <Bot size={16} />
            <span className={compact ? "sr-only" : undefined}>
              Agents & Teams
            </span>
            <span
              className={
                compact
                  ? "hidden"
                  : "ml-auto font-mono text-[10px] text-stone-500"
              }
            >
              {agents.data?.length || 0} · {teams.data?.length || 0}
            </span>
          </Link>
        </nav>
        {compact ? (
          <div className="mt-5 flex min-h-0 flex-1 flex-col gap-1 overflow-y-auto">
            <button
              type="button"
              className="side-item justify-center !px-0"
              aria-label="Tạo project mới"
              title="Tạo project mới"
              onClick={() => setCreate(true)}
            >
              <Plus size={16} aria-hidden="true" />
            </button>
            {recentProjects(projects.data?.items || [], currentId).map(
              (project) => (
                <Link
                  key={project.id}
                  href={`/projects/${project.id}`}
                  aria-label={project.name}
                  title={project.name}
                  className={`side-item justify-center !px-0 ${currentId === project.id ? "active" : ""}`}
                >
                  <Folder size={17} aria-hidden="true" />
                </Link>
              ),
            )}
            <button
              type="button"
              className="side-item justify-center !px-0"
              aria-label="Tất cả projects"
              title="Tất cả projects"
              onClick={() => setAll(true)}
            >
              <Menu size={16} aria-hidden="true" />
            </button>
          </div>
        ) : (
          <>
            <div className="mt-5 flex items-center justify-between px-2 pb-2 text-[11px] font-semibold text-stone-500">
              <span>Projects</span>
              <button
                aria-label="Tạo project mới"
                onClick={() => setCreate(true)}
              >
                <Plus size={15} />
              </button>
            </div>
            <div className="min-h-0 flex-1 space-y-1 overflow-y-auto">
              <ErrorState error={projects.error} />
              {recentProjects(projects.data?.items || [], currentId).map(
                (project) => (
                  <ProjectItem
                    key={project.id}
                    project={project}
                    current={currentId === project.id}
                    onNavigate={() => setMobile(false)}
                  />
                ),
              )}
              {(projects.data?.total || 0) > 5 && (
                <button
                  className="side-item w-full text-xs text-stone-500"
                  onClick={() => setAll(true)}
                >
                  Xem tất cả ({projects.data?.total})
                </button>
              )}
              {projects.data?.total === 0 && (
                <button
                  className="side-item text-xs text-stone-500"
                  onClick={() => setCreate(true)}
                >
                  + Tạo project đầu tiên
                </button>
              )}
            </div>
          </>
        )}
        <DropdownMenu>
          <DropdownMenuTrigger
            type="button"
            aria-label={`Menu tài khoản ${me.data?.display_name || ""}`}
            disabled={!me.data || loggingOut}
            title={compact ? me.data?.display_name : undefined}
            className={`mt-4 flex w-full items-center gap-2 rounded-xl text-left outline-none hover:bg-[#DFDDD0]/60 focus-visible:ring-2 focus-visible:ring-stone-400 data-popup-open:bg-[#DFDDD0]/60 ${compact ? "justify-center p-1.5" : "p-2"}`}
          >
            <UserAvatar name={me.data?.display_name || "?"} />
            <span className={compact ? "hidden" : "min-w-0 flex-1"}>
              <span className="block truncate text-xs font-semibold">
                {me.data?.display_name}
              </span>
              <span
                className="block truncate font-mono text-[10px] text-stone-500"
                title={current?.workspace_path}
              >
                {current?.workspace_path || "Workspace của bạn"}
              </span>
            </span>
            <ChevronDown
              size={14}
              aria-hidden="true"
              className={compact ? "hidden" : "shrink-0 text-stone-500"}
            />
          </DropdownMenuTrigger>
          <DropdownMenuContent side="top" align="start" className="w-56">
            {me.data && ["OWNER", "ADMIN"].includes(me.data.system_role) && (
              <>
                <DropdownMenuItem
                  className="min-h-10 gap-2"
                  render={
                    <Link
                      href="/settings/adapters"
                      onClick={() => setMobile(false)}
                    />
                  }
                >
                  <Settings2 size={16} aria-hidden="true" /> Settings
                </DropdownMenuItem>
                <DropdownMenuSeparator />
              </>
            )}
            <DropdownMenuItem
              className="min-h-10 gap-2"
              variant="destructive"
              disabled={loggingOut}
              onClick={async () => {
                if (loggingOut) return;
                setLoggingOut(true);
                try {
                  const response = await fetch("/api/auth/logout", {
                    method: "POST",
                  });
                  if (!response.ok)
                    throw new Error("Không đăng xuất được. Vui lòng thử lại.");
                  router.replace("/login");
                  router.refresh();
                } catch (error) {
                  toast.error((error as Error).message);
                  setLoggingOut(false);
                }
              }}
            >
              <LogOut size={16} aria-hidden="true" /> Đăng xuất
            </DropdownMenuItem>
          </DropdownMenuContent>
        </DropdownMenu>
      </aside>
      {create && <ProjectDialog onClose={() => setCreate(false)} />}{" "}
      {all && (
        <Modal title="Tất cả projects" onClose={() => setAll(false)}>
          <div className="space-y-1">
            {projects.data?.items.map((p) => (
              <Link
                key={p.id}
                className="side-item"
                href={`/projects/${p.id}`}
                onClick={() => {
                  localStorage.setItem(`sidebar.open.${p.id}`, "true");
                  setAll(false);
                  setMobile(false);
                }}
              >
                <Folder size={15} />
                {p.name}
                <span className="ml-auto truncate font-mono text-[10px] text-stone-400">
                  {p.default_branch}
                </span>
              </Link>
            ))}
          </div>
          <Link
            className="btn btn-light mt-4"
            href="/projects"
            onClick={() => setAll(false)}
          >
            Trang danh sách projects
          </Link>
        </Modal>
      )}
    </>
  );
}
