import type { components } from "./api/schema";
type Schemas = components["schemas"];
export type Agent = Schemas["AgentOut"];
export type Team = Schemas["TeamOut"];
export type Project = Schemas["ProjectOut"];
export type Workflow = Schemas["WorkflowOut"];
export type Ticket = Schemas["TicketOut"];
export type User = Schemas["UserOut"];
export type Members = Schemas["MembersOut"];
export type ProjectTree = Schemas["ProjectTree"];
export type Notice = Schemas["NotificationOut"];
export type Workspace = Schemas["WorkspaceOut"];
export type Connection = Schemas["ConnectionOut"];
export type Permission = Schemas["PermissionProfile"];
export type Page<T> = {
  items: T[];
  total: number;
  next_cursor?: string | null;
};
