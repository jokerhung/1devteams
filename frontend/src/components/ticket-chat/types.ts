import type { components } from "@/lib/api/schema";
export type ChatEvent = components["schemas"]["MessageOut"];
export type Attachment = {
  id: string;
  filename: string;
  mime: string;
  size?: number;
  url?: string;
  thumbnail_url?: string | null;
  path?: string;
};
export type Waiting = {
  kind: string;
  node_id: string;
  payload: Record<string, unknown>;
};
export type RuntimeState = {
  result?: Record<string, unknown>;
  status: string;
  current_node_id: string | null;
  waiting: Waiting | null;
  node_statuses: Record<
    string,
    "idle" | "running" | "done" | "waiting" | "failed"
  >;
  last_seq?: number;
};
export type LogLine = {
  seq: number;
  at: string;
  agent: string;
  kind: "info" | "tool" | "perm" | "deny" | "think" | "ok" | "error";
  text: string;
};
export type FileChange = {
  path: string;
  old: string;
  next: string;
  diff: string;
};
export type Gate = {
  key: string;
  kind: string;
  payload: Record<string, unknown>;
  resolved?: {
    approved?: boolean;
    user?: { display_name?: string };
    at: string;
  };
};
export type TurnGroup = {
  type: "turn";
  id: string;
  agent: string;
  nodeId?: string | null;
  at: string;
  endedAt?: string;
  content: string;
  thinking: string;
  model?: string;
  runtime?: string;
  tools: Record<string, ChatEvent>;
  files: Record<string, FileChange>;
  terminals: ChatEvent[];
  permissions: ChatEvent[];
  plans: ChatEvent[];
  logLines: LogLine[];
  gate?: Gate;
  failed?: boolean;
};
export type MessageGroup =
  | TurnGroup
  | { type: "user"; id: string; event: ChatEvent }
  | { type: "system"; id: string; text: string; at: string };
export type PendingMessage = {
  id: string;
  text: string;
  attachments: Attachment[];
  failed?: boolean;
};
export type DraftFile = {
  key: string;
  file: File;
  progress: number;
  attachment?: Attachment;
  error?: string;
};
