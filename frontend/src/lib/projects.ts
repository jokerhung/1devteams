import { apiFetch } from "./api";
import type { Page, Project } from "./types";
export async function allProjects(): Promise<Page<Project>> {
  const items: Project[] = [];
  let total = 0;
  do {
    const page = await apiFetch<Page<Project>>(
      `/projects?limit=500${items.length ? `&offset=${items.length}` : ""}`,
    );
    total = page.total;
    items.push(...page.items);
    if (!page.items.length) break;
  } while (items.length < total);
  return { items, total };
}
