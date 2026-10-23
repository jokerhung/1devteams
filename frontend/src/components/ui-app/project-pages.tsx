"use client";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { Plus, Settings, Users, Folder } from "lucide-react";
import { apiFetch, send } from "@/lib/api";
import { keys } from "@/lib/query-keys";
import { allProjects } from "@/lib/projects";
import { WorkflowCard } from "@/components/workflow/WorkflowCard";
import { WorkspacePathField } from "./workspace-path-field";
import type {
  Agent,
  Team,
  User,
  Project,
  Members,
  Workflow,
  Ticket,
} from "@/lib/types";
import {
  AgentPill,
  ConfirmDialog,
  EmptyState,
  ErrorState,
  Loading,
  Logo,
  PageHeader,
  StatusBadge,
  UserAvatar,
} from "./primitives";
import { ProjectDialog } from "./project-dialog";
import { CreateTicketDialog } from "./ticket-dialog";
export function TicketTable({
  tickets,
  pid,
  workflows = [],
}: {
  tickets: Ticket[];
  pid: string;
  workflows?: Workflow[];
}) {
  return (
    <div className="overflow-x-auto">
      <table className="table">
        <thead>
          <tr>
            <th>Ticket</th>
            <th>Tiêu đề</th>
            {!!workflows.length && <th>Workflow</th>}
            <th>Trạng thái</th>
            <th>Đang chạy</th>
            <th>Cập nhật</th>
          </tr>
        </thead>
        <tbody>
          {tickets.map((t) => (
            <tr key={t.id}>
              <td>
                <Link
                  className="font-mono hover:underline"
                  href={`/projects/${pid}/workflows/${t.workflow_id}/tickets/${t.id}`}
                >
                  {t.code}
                </Link>
              </td>
              <td>
                <Link
                  href={`/projects/${pid}/workflows/${t.workflow_id}/tickets/${t.id}`}
                >
                  {t.title}
                </Link>
              </td>
              {!!workflows.length && (
                <td>{workflows.find((w) => w.id === t.workflow_id)?.name}</td>
              )}
              <td>
                <StatusBadge status={t.status} />
              </td>
              <td className="font-mono text-[11px]">
                {t.current_node_id || "—"}
              </td>
              <td className="whitespace-nowrap text-[11px] text-stone-500">
                {new Date(t.updated_at).toLocaleString("vi-VN")}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
export function ProjectsPage() {
  const [create, setCreate] = useState(false);
  const projects = useQuery({
    queryKey: [...keys.projects, "list"],
    queryFn: allProjects,
  });
  return (
    <>
      <PageHeader
        title="Projects"
        description="Mỗi project là một workspace local. Thêm AI Team và workflow sau khi tạo project."
      >
        <button className="btn btn-dark" onClick={() => setCreate(true)}>
          <Plus size={14} />
          Tạo project
        </button>
      </PageHeader>
      <ErrorState error={projects.error} />
      {projects.isLoading ? (
        <Loading />
      ) : projects.data?.total === 0 ? (
        <EmptyState
          action={
            <button className="btn btn-dark" onClick={() => setCreate(true)}>
              Tạo project đầu tiên
            </button>
          }
        >
          Chưa có project. Bắt đầu từ thư mục Git local của bạn.
        </EmptyState>
      ) : (
        <div className="grid gap-3 xl:grid-cols-2">
          {projects.data?.items.map((p) => (
            <Link
              className="card hover:border-stone-400"
              key={p.id}
              href={`/projects/${p.id}`}
            >
              <h2 className="flex items-center gap-2 text-sm font-semibold">
                <Folder size={16} />
                {p.name}
              </h2>
              <p className="mt-3 truncate font-mono text-[11px] text-stone-500">
                {p.workspace_path}
              </p>
              <p className="mt-2 text-xs text-stone-400">
                ⑂ {p.default_branch}
              </p>
            </Link>
          ))}
        </div>
      )}
      {create && <ProjectDialog onClose={() => setCreate(false)} />}
    </>
  );
}
export function ProjectOverview({
  pid,
  workflowsOnly = false,
}: {
  pid: string;
  workflowsOnly?: boolean;
}) {
  const client = useQueryClient();
  const [ticketWorkflow, setTicketWorkflow] = useState<string | null>(null);
  const [seeding, setSeeding] = useState(false);
  const project = useQuery({
    queryKey: keys.project(pid),
    queryFn: () => apiFetch<Project>(`/projects/${pid}`),
  });
  const workflows = useQuery({
    queryKey: keys.workflows(pid),
    queryFn: () =>
      apiFetch<Workflow[]>(`/projects/${pid}/workflows?include_archived=true`),
  });
  const members = useQuery({
    queryKey: keys.members(pid),
    queryFn: () => apiFetch<Members>(`/projects/${pid}/members`),
  });
  const agents = useQuery({
    queryKey: keys.effective(pid),
    queryFn: () => apiFetch<Agent[]>(`/projects/${pid}/effective-agents`),
  });
  const tickets = useQuery({
    queryKey: keys.tickets(pid),
    queryFn: () => apiFetch<Ticket[]>(`/projects/${pid}/tickets?limit=15`),
  });
  if (project.isLoading) return <Loading />;
  if (!project.data) return <ErrorState error={project.error} />;
  const p = project.data;
  const step = tickets.data?.length
    ? 4
    : workflows.data?.some((w) => w.status === "PUBLISHED")
      ? 3
      : 2;
  return (
    <>
      <PageHeader
        title={workflowsOnly ? `Workflows · ${p.name}` : p.name}
        description={`${p.workspace_path} · ⑂ ${p.default_branch}`}
      >
        <Link className="btn btn-light" href={`/projects/${pid}/members`}>
          <Users size={14} />
          Thành viên & AI Team
        </Link>
        <Link
          className="btn btn-light"
          aria-label="Cài đặt project"
          href={`/projects/${pid}/settings`}
        >
          <Settings size={14} />
        </Link>
        <Link className="btn btn-dark" href={`/projects/${pid}/workflows/new`}>
          <Plus size={14} />
          Tạo workflow
        </Link>
      </PageHeader>
      {!workflowsOnly && (
        <>
          <div className="mb-7 flex flex-wrap gap-3 rounded-xl bg-[#F7F6EE] p-4 text-xs">
            {["Project", "Workflow (xuất bản)", "Ticket", "Cửa sổ chat"].map(
              (s, i) => (
                <span
                  key={s}
                  className={
                    i + 1 === step
                      ? "font-semibold text-stone-900"
                      : "text-stone-400"
                  }
                >
                  {i + 1 < step ? "✓" : i + 1}. {s}
                  {i < 3 && <span className="ml-3 text-stone-300">›</span>}
                </span>
              ),
            )}
            <p className="w-full text-[11px] text-stone-500">
              Tạo project → thêm AI Team → xuất bản workflow → tạo ticket và mở
              chat.
            </p>
          </div>
          <section className="mb-7">
            <h2 className="mb-3 text-sm font-semibold">
              AI Team & Agent trong project
            </h2>
            <div className="flex flex-wrap gap-2">
              {members.data?.teams.map((t) => (
                <span className="pill" key={t.id}>
                  <Logo entity={t} size={20} />
                  {t.name}
                </span>
              ))}
              {agents.data?.map((a) => (
                <AgentPill key={a.id} agent={a} />
              ))}
            </div>
            {agents.data?.length === 0 && (
              <p className="error mt-3">
                Chưa có agent nào — hãy thêm AI Team trước khi tạo workflow.
              </p>
            )}
            <ErrorState error={members.error || agents.error} />
          </section>
        </>
      )}
      <section>
        <h2 className="mb-3 text-sm font-semibold">
          Workflows ({workflows.data?.length || 0})
        </h2>
        <ErrorState error={workflows.error} />
        {workflows.isLoading ? (
          <Loading />
        ) : !workflows.data?.length ? (
          <>
            <EmptyState
              action={
                <Link
                  className="btn btn-dark"
                  href={`/projects/${pid}/workflows/new`}
                >
                  Tạo workflow đầu tiên
                </Link>
              }
            >
              Project chưa có workflow. Tạo workflow để bắt đầu nhận ticket.
              Ticket luôn được tạo bên trong một workflow.
            </EmptyState>
            <button
              className="btn btn-light mt-3"
              disabled={seeding}
              onClick={async () => {
                setSeeding(true);
                try {
                  await send(`/projects/${pid}/seed-default`);
                  await client.invalidateQueries({ queryKey: ["projects"] });
                  toast.success(
                    "Đã thêm Core Bugfix Squad và xuất bản Fix Bug",
                  );
                } catch (e) {
                  toast.error((e as Error).message);
                } finally {
                  setSeeding(false);
                }
              }}
            >
              Dùng nhanh workflow Fix Bug mẫu
            </button>
          </>
        ) : (
          <div className="grid gap-3 xl:grid-cols-2">
            {workflows.data.map((w) => (
              <WorkflowCard
                key={w.id}
                workflow={w}
                agents={agents.data || []}
                onTicket={() => setTicketWorkflow(w.id)}
              />
            ))}
          </div>
        )}
      </section>
      {!workflowsOnly && (
        <section className="mt-8">
          <h2 className="mb-3 text-sm font-semibold">Ticket gần đây</h2>
          {tickets.data?.length ? (
            <TicketTable
              tickets={tickets.data}
              pid={pid}
              workflows={workflows.data}
            />
          ) : (
            <p className="text-xs text-stone-400">Chưa có ticket.</p>
          )}
          <ErrorState error={tickets.error} />
        </section>
      )}
      {ticketWorkflow && (
        <CreateTicketDialog
          pid={pid}
          wid={ticketWorkflow}
          onClose={() => setTicketWorkflow(null)}
        />
      )}
    </>
  );
}
export function ProjectSettings({ pid }: { pid: string }) {
  const client = useQueryClient();
  const router = useRouter();
  const [busy, setBusy] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const [error, setError] = useState("");
  const p = useQuery({
    queryKey: keys.project(pid),
    queryFn: () => apiFetch<Project>(`/projects/${pid}`),
  });
  if (p.isLoading) return <Loading />;
  if (!p.data) return <ErrorState error={p.error} />;
  return (
    <>
      <PageHeader title={`Cài đặt · ${p.data.name}`}>
        <Link className="btn btn-light" href={`/projects/${pid}`}>
          Về project
        </Link>
      </PageHeader>
      <form
        className="max-w-xl space-y-4"
        onSubmit={async (e) => {
          e.preventDefault();
          const data = Object.fromEntries(new FormData(e.currentTarget));
          setBusy(true);
          try {
            await send(`/projects/${pid}`, data, "PATCH");
            await client.invalidateQueries({ queryKey: ["projects"] });
            toast.success("Đã lưu project");
          } catch (e) {
            setError((e as Error).message);
          } finally {
            setBusy(false);
          }
        }}
      >
        {[
          ["name", "Tên project"],
          ["workspace_path", "Đường dẫn thư mục local"],
          ["default_branch", "Nhánh Git"],
          ["git_remote", "Git remote"],
        ].map(([key, label]) =>
          key === "workspace_path" ? (
            <WorkspacePathField
              key={key}
              defaultValue={p.data!.workspace_path}
            />
          ) : (
            <label className="field" key={key}>
              {label}
              <input
                name={key}
                required
                defaultValue={String(p.data![key as keyof Project])}
              />
            </label>
          ),
        )}
        <label className="field">
          Mô tả
          <textarea name="description" defaultValue={p.data.description} />
        </label>
        {error && (
          <p className="error" role="alert">
            {error}
          </p>
        )}
        <button className="btn btn-dark" disabled={busy}>
          Lưu cài đặt
        </button>
      </form>
      <div className="mt-12 max-w-xl rounded-xl border border-red-200 p-4">
        <h2 className="text-sm font-semibold">Xoá project</h2>
        <p className="my-2 text-xs text-stone-500">
          Xoá dữ liệu project, workflow và ticket trong aiTeams.
        </p>
        <button
          className="btn btn-light text-red-700"
          onClick={() => setDeleting(true)}
        >
          Xoá project
        </button>
      </div>
      {deleting && (
        <ConfirmDialog
          title="Xoá project?"
          onClose={() => setDeleting(false)}
          onConfirm={async () => {
            await send(`/projects/${pid}`, undefined, "DELETE");
            localStorage.removeItem("lastProjectId");
            await client.invalidateQueries({ queryKey: ["projects"] });
            router.replace("/projects");
          }}
        >
          Dữ liệu project trong aiTeams sẽ bị xoá vĩnh viễn.
        </ConfirmDialog>
      )}
    </>
  );
}
export function ProjectMembers({ pid }: { pid: string }) {
  const client = useQueryClient();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const members = useQuery({
    queryKey: keys.members(pid),
    queryFn: () => apiFetch<Members>(`/projects/${pid}/members`),
  });
  const agents = useQuery({
    queryKey: keys.agents,
    queryFn: () => apiFetch<Agent[]>("/agents"),
  });
  const teams = useQuery({
    queryKey: keys.teams,
    queryFn: () => apiFetch<Team[]>("/teams"),
  });
  const effective = useQuery({
    queryKey: keys.effective(pid),
    queryFn: () => apiFetch<Agent[]>(`/projects/${pid}/effective-agents`),
  });
  const me = useQuery({
    queryKey: keys.me,
    queryFn: () => apiFetch<User>("/auth/me"),
  });
  const users = useQuery({
    queryKey: ["users"],
    queryFn: () => apiFetch<User[]>("/users"),
    enabled: !!me.data && ["OWNER", "ADMIN"].includes(me.data.system_role),
  });
  async function change(type: string, id: string, add: boolean, role?: string) {
    setBusy(true);
    setError("");
    const previous = client.getQueryData<Members>(keys.members(pid));
    if (previous && type === "TEAM") {
      const team = teams.data?.find((t) => t.id === id);
      client.setQueryData(keys.members(pid), {
        ...previous,
        teams:
          add && team
            ? [...previous.teams, team]
            : previous.teams.filter((t) => t.id !== id),
      });
    }
    if (previous && type === "AGENT") {
      const agent = agents.data?.find((a) => a.id === id);
      client.setQueryData(keys.members(pid), {
        ...previous,
        agents:
          add && agent
            ? [...previous.agents, agent]
            : previous.agents.filter((a) => a.id !== id),
      });
    }
    try {
      await send(
        add
          ? `/projects/${pid}/members`
          : `/projects/${pid}/members/${type}/${id}`,
        add
          ? {
              member_type: type,
              member_id: id,
              ...(role ? { project_role: role } : {}),
            }
          : undefined,
        add ? "POST" : "DELETE",
      );
      await client.invalidateQueries({ queryKey: ["projects"] });
    } catch (e) {
      if (previous) client.setQueryData(keys.members(pid), previous);
      setError((e as Error).message);
      toast.error((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  if (members.isLoading) return <Loading />;
  return (
    <>
      <PageHeader
        title="Thành viên & AI Team"
        description="Thêm người dùng, AI Team hoặc agent lẻ vào project."
      >
        <Link className="btn btn-light" href={`/projects/${pid}`}>
          Về project
        </Link>
      </PageHeader>
      <ErrorState error={members.error || agents.error || teams.error} />
      {error && (
        <p role="alert" className="error mb-4">
          {error}
        </p>
      )}
      <section className="mb-8">
        <h2 className="mb-3 text-sm font-semibold">Người dùng</h2>
        <div className="overflow-x-auto">
          <table className="table">
            <thead>
              <tr>
                <th>Tên</th>
                <th>Email</th>
                <th>Quyền</th>
                <th />
              </tr>
            </thead>
            <tbody>
              {members.data?.users.map((user) => (
                <tr key={user.id}>
                  <td>
                    <span className="flex items-center gap-2">
                      <UserAvatar name={user.display_name} />
                      {user.display_name}
                    </span>
                  </td>
                  <td>{user.email}</td>
                  <td>
                    <select
                      aria-label={`Quyền ${user.display_name}`}
                      value={user.project_role || "VIEWER"}
                      disabled={busy}
                      onChange={async (e) => {
                        setBusy(true);
                        try {
                          await send(
                            `/projects/${pid}/members/USER/${user.id}`,
                            { project_role: e.target.value },
                            "PATCH",
                          );
                          await client.invalidateQueries({
                            queryKey: keys.members(pid),
                          });
                        } catch (e) {
                          toast.error((e as Error).message);
                        } finally {
                          setBusy(false);
                        }
                      }}
                    >
                      {["MAINTAINER", "REPORTER", "VIEWER"].map((role) => (
                        <option key={role}>{role}</option>
                      ))}
                    </select>
                  </td>
                  <td>
                    <button
                      className="text-red-700"
                      disabled={busy}
                      onClick={() => change("USER", user.id, false)}
                    >
                      Gỡ
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <form
          className="mt-3 flex flex-wrap items-end gap-2"
          onSubmit={(e) => {
            e.preventDefault();
            const form = new FormData(e.currentTarget);
            change(
              "USER",
              String(form.get("user")),
              true,
              String(form.get("role")),
            );
          }}
        >
          <label className="field">
            Người dùng
            {me.isPending ||
            (me.data && ["OWNER", "ADMIN"].includes(me.data.system_role)) ? (
              <select name="user" required disabled={!users.data}>
                <option value="">
                  {users.isPending ? "Đang tải người dùng…" : "Chọn người dùng"}
                </option>
                {(users.data || [])
                  .filter(
                    (u) => !members.data?.users.some((m) => m.id === u.id),
                  )
                  .map((u) => (
                    <option key={u.id} value={u.id}>
                      {u.display_name} · {u.email}
                    </option>
                  ))}
              </select>
            ) : (
              <input name="user" placeholder="UUID người dùng" required />
            )}
          </label>
          <label className="field">
            Quyền
            <select name="role">
              <option>VIEWER</option>
              <option>REPORTER</option>
              <option>MAINTAINER</option>
            </select>
          </label>
          <button className="btn btn-light" disabled={busy}>
            Thêm
          </button>
        </form>
      </section>
      <section className="mb-8">
        <h2 className="mb-3 text-sm font-semibold">AI Teams</h2>
        <div className="grid gap-3 xl:grid-cols-2">
          {teams.data?.map((t) => (
            <label key={t.id} className="card flex items-start gap-3">
              <input
                type="checkbox"
                className="mt-2"
                disabled={busy}
                checked={!!members.data?.teams.some((m) => m.id === t.id)}
                onChange={(e) => change("TEAM", t.id, e.target.checked)}
              />
              <Logo entity={t} />
              <span>
                <span className="text-xs font-semibold">{t.name}</span>
                <span className="mt-2 flex flex-wrap gap-1">
                  {t.agent_ids
                    .map((id) => agents.data?.find((a) => a.id === id))
                    .filter((a): a is Agent => !!a)
                    .map((a) => (
                      <span key={a.id} className="pill">
                        {a.handle}
                      </span>
                    ))}
                </span>
              </span>
            </label>
          ))}
        </div>
      </section>
      <section className="mb-8">
        <h2 className="mb-3 text-sm font-semibold">Agent lẻ</h2>
        <div className="grid grid-cols-2 gap-3">
          {agents.data
            ?.filter(
              (a) =>
                a.is_active &&
                (!members.data?.teams.some((t) => t.agent_ids.includes(a.id)) ||
                  members.data?.agents.some((m) => m.id === a.id)),
            )
            .map((a) => (
              <label key={a.id} className="flex items-center gap-2 text-xs">
                <input
                  type="checkbox"
                  disabled={busy}
                  checked={!!members.data?.agents.some((m) => m.id === a.id)}
                  onChange={(e) => change("AGENT", a.id, e.target.checked)}
                />
                <Logo entity={a} size={24} />
                {a.handle}
              </label>
            ))}
        </div>
      </section>
      <section className="rounded-xl bg-[#F7F6EE] p-4">
        <h2 className="mb-3 text-sm font-semibold">
          Agent hiệu lực trong project
        </h2>
        <div className="flex flex-wrap gap-2">
          {effective.data?.map((a) => (
            <AgentPill agent={a} key={a.id} />
          ))}
          {effective.data?.length === 0 && (
            <p className="text-xs text-stone-500">Chưa có agent nào.</p>
          )}
        </div>
      </section>
    </>
  );
}
