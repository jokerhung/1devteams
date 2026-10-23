import { create } from "zustand";
import { apiFetch, send } from "@/lib/api";
export const useChatPrefs = create<{
  agentId: string | null;
  load: () => Promise<void>;
  choose: (id: string | null) => Promise<void>;
}>((set) => ({
  agentId: null,
  load: async () => {
    const cached = localStorage.getItem("aiteams_default_mention");
    if (cached) set({ agentId: cached });
    const prefs = await apiFetch<{ default_mention_agent_id?: string | null }>(
      "/me/preferences",
    );
    const agentId = prefs.default_mention_agent_id || null;
    set({ agentId });
    if (agentId) localStorage.setItem("aiteams_default_mention", agentId);
    else localStorage.removeItem("aiteams_default_mention");
  },
  choose: async (id) => {
    await send(
      "/me/preferences",
      { key: "default_mention_agent_id", value: id },
      "PUT",
    );
    set({ agentId: id });
    if (id) localStorage.setItem("aiteams_default_mention", id);
    else localStorage.removeItem("aiteams_default_mention");
  },
}));
