"use client";
import { useEffect, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Pencil, Trash2, Plus } from "lucide-react";
import { apiFetch, send } from "@/lib/api";
import type { Agent, Team, Members, User } from "@/lib/types";
import { keys } from "@/lib/query-keys";
import { allProjects } from "@/lib/projects";
import {
  AgentAvatar,
  AgentPill,
  ConfirmDialog,
  EmptyState,
  ErrorState,
  Loading,
  Logo,
  PageHeader,
  PermissionBadges,
  RuntimeBadge,
} from "@/components/ui-app/primitives";
import { AgentForm } from "@/components/ui-app/agent-form";
import { TeamForm } from "@/components/ui-app/team-form";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
export default function AgentsPage() {
  const client = useQueryClient();
  const [agentForm, setAgentForm] = useState<Agent | "new" | null>(null);
  const [teamForm, setTeamForm] = useState<Team | "new" | null>(null);
  const [deleting, setDeleting] = useState<{
    id: string;
    name: string;
    type: "agents" | "teams";
  } | null>(null);
  const [restarting, setRestarting] = useState<string[]>([]);
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
  const admin = me.data && ["OWNER", "ADMIN"].includes(me.data.system_role);
  const counts = useQuery({
    queryKey: ["projects", "team-counts"],
    queryFn: async () => {
      const projects = await allProjects();
      const members = await Promise.all(
        projects.items.map((p) =>
          apiFetch<Members>(`/projects/${p.id}/members`),
        ),
      );
      const result: Record<string, number> = {};
      for (const m of members)
        for (const t of m.teams) result[t.id] = (result[t.id] || 0) + 1;
      return result;
    },
  });
  useEffect(() => {
    const listener = (event: Event) => {
      const detail = (event as CustomEvent).detail;
      setRestarting((ids) => ids.filter((id) => id !== detail.agent_id));
    };
    window.addEventListener("agent-restarted", listener);
    return () => window.removeEventListener("agent-restarted", listener);
  }, []);
  return (
    <>
      <Tabs defaultValue="agents">
        <TabsList aria-label="Quản lý Agents và Teams" className="mb-4">
          <TabsTrigger value="agents" className="px-4">
            Agents
          </TabsTrigger>
          <TabsTrigger value="teams" className="px-4">
            Teams
          </TabsTrigger>
        </TabsList>
        <TabsContent value="agents">
          <PageHeader
            title="Agents"
            description="Ngoài 4 agent mặc định, bạn có thể tạo thêm agent nối với Claude Code hoặc Codex, rồi gom vào AI Team."
          >
            {admin && (
              <button
                className="btn btn-dark"
                onClick={() => setAgentForm("new")}
              >
                <Plus size={14} />
                Tạo Agent
              </button>
            )}
          </PageHeader>
          <ErrorState error={agents.error || teams.error} />
          {agents.isLoading ? (
            <Loading />
          ) : (
            <div className="grid gap-3.5 xl:grid-cols-2">
              {agents.data?.map((agent) => (
                <article className="card" key={agent.id}>
                  <div className="flex items-start gap-3">
                    <AgentAvatar agent={agent} />
                    <div className="min-w-0 flex-1">
                      <div className="flex flex-wrap items-center gap-2">
                        <span className="font-mono text-xs font-semibold">
                          {agent.handle}
                        </span>
                        <span className="text-xs font-semibold">
                          {agent.display_name}
                        </span>
                        {agent.is_builtin && (
                          <span className="badge">Mặc định</span>
                        )}
                      </div>
                      <div className="mt-1.5">
                        <RuntimeBadge runtime={agent.runtime} />
                      </div>
                    </div>
                    {admin && (
                      <div className="flex gap-1">
                        <button
                          className="rounded p-1 text-stone-400 hover:bg-stone-100 hover:text-stone-800"
                          aria-label={`Sửa ${agent.handle}`}
                          onClick={() => setAgentForm(agent)}
                        >
                          <Pencil size={14} />
                        </button>
                        {!agent.is_builtin && (
                          <button
                            className="rounded p-1 text-stone-400 hover:bg-red-50 hover:text-red-600"
                            aria-label={`Xoá ${agent.handle}`}
                            onClick={() =>
                              setDeleting({
                                id: agent.id,
                                name: agent.handle,
                                type: "agents",
                              })
                            }
                          >
                            <Trash2 size={14} />
                          </button>
                        )}
                      </div>
                    )}
                  </div>
                  <p className="mt-3 text-xs leading-relaxed text-stone-500">
                    {agent.description || "Chưa có mô tả vai trò."}
                  </p>
                  <div className="mt-3 flex flex-wrap items-center gap-2 border-t border-stone-100 pt-2 text-[11px] text-stone-500">
                    <span>
                      Model: <code>{agent.model || "Mặc định"}</code>
                    </span>
                    <span>·</span>
                    <PermissionBadges profile={agent.permission_profile} />
                    <p className="ml-auto text-[10px] text-stone-400">
                      {teams.data?.some((t) => t.agent_ids.includes(agent.id))
                        ? `Team: ${teams.data
                            .filter((t) => t.agent_ids.includes(agent.id))
                            .map((t) => t.name)
                            .join(", ")}`
                        : "Chưa thuộc team"}
                    </p>
                  </div>
                  {agent.base_url && (
                    <p className="mt-2 truncate font-mono text-[10px] text-sky-700">
                      {new URL(agent.base_url).host}
                    </p>
                  )}
                  {restarting.includes(agent.id) && (
                    <p
                      role="status"
                      className="mt-3 animate-pulse text-xs text-amber-700"
                    >
                      ↻ Đang khởi động lại…
                    </p>
                  )}
                </article>
              ))}
            </div>
          )}
        </TabsContent>
        <TabsContent value="teams">
          <section>
            <PageHeader
              title="Teams"
              description="Mỗi AI Team gồm một hoặc nhiều AI Agent. Thêm AI Team vào project để dùng các agent trong workflow."
            >
              {admin && (
                <button
                  className="btn btn-light"
                  onClick={() => setTeamForm("new")}
                >
                  <Plus size={14} />
                  Tạo AI Team
                </button>
              )}
            </PageHeader>
            <ErrorState error={teams.error} />
            {teams.isLoading && <Loading />}
            {teams.data?.length === 0 && (
              <EmptyState>
                Chưa có AI Team. Gom các agent thành team để thêm vào project.
              </EmptyState>
            )}
            <div className="grid gap-3.5 xl:grid-cols-2">
              {teams.data?.map((team) => (
                <article className="card" key={team.id}>
                  <div className="flex items-center gap-3">
                    <Logo entity={team} />
                    <h2 className="flex-1 text-sm font-semibold">
                      {team.name}
                    </h2>
                    {admin && (
                      <>
                        <button
                          aria-label={`Sửa team ${team.name}`}
                          onClick={() => setTeamForm(team)}
                          className="btn btn-light"
                        >
                          Sửa
                        </button>
                        <button
                          aria-label={`Xoá team ${team.name}`}
                          onClick={() =>
                            setDeleting({
                              id: team.id,
                              name: team.name,
                              type: "teams",
                            })
                          }
                          className="rounded p-1 text-stone-400"
                        >
                          <Trash2 size={14} />
                        </button>
                      </>
                    )}
                  </div>
                  <p className="my-3 text-xs text-stone-500">
                    {team.description}
                  </p>
                  <div className="flex flex-wrap gap-1.5">
                    {team.agent_ids
                      .map((id) => agents.data?.find((a) => a.id === id))
                      .filter((a): a is Agent => !!a)
                      .map((a) => (
                        <AgentPill key={a.id} agent={a} />
                      ))}
                  </div>
                  <p className="mt-4 text-[11px] text-stone-400">
                    {team.agent_ids.length} agent · dùng trong{" "}
                    {counts.data?.[team.id] || 0} project
                  </p>
                </article>
              ))}
            </div>
          </section>
        </TabsContent>
      </Tabs>
      {agentForm && (
        <AgentForm
          agent={agentForm === "new" ? undefined : agentForm}
          teams={teams.data || []}
          onClose={() => setAgentForm(null)}
          onRestart={(a, pending) =>
            setRestarting((ids) =>
              pending
                ? [...new Set([...ids, a.id])]
                : ids.filter((id) => id !== a.id),
            )
          }
        />
      )}
      {teamForm && (
        <TeamForm
          team={teamForm === "new" ? undefined : teamForm}
          agents={agents.data || []}
          onClose={() => setTeamForm(null)}
        />
      )}
      {deleting && (
        <ConfirmDialog
          title={`Xoá ${deleting.name}?`}
          onClose={() => setDeleting(null)}
          onConfirm={async () => {
            await send(`/${deleting.type}/${deleting.id}`, undefined, "DELETE");
            await client.invalidateQueries({ queryKey: [deleting.type] });
            await client.invalidateQueries({ queryKey: ["projects"] });
          }}
        >
          Bạn có chắc muốn xoá? Backend sẽ kiểm tra các workflow đang dùng trước
          khi xoá.
        </ConfirmDialog>
      )}
    </>
  );
}
