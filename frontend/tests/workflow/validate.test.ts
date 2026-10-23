import { expect, test } from "vitest";
import { templateGraph } from "@/components/workflow/templates";
import { validateGraph } from "@/components/workflow/validate";
import { mainPath } from "@/components/workflow/PipelineView";
import { agents } from "./fixtures";
test.each(["blank", "bugfix_default", "bugfix_with_security_review"] as const)(
  "template %s is valid and security review precedes tester",
  (template) => {
    const graph = templateGraph(template, agents);
    expect(validateGraph(graph, agents)).toEqual([]);
    if (template === "bugfix_with_security_review") {
      const route = mainPath(graph).map((n) => n.id);
      expect(route.indexOf("n_security")).toBeLessThan(route.indexOf("n_test"));
    }
  },
);
test("missing fail branch and foreign agent produce node errors", () => {
  const graph = templateGraph("bugfix_default", agents);
  graph.edges = graph.edges!.filter((e) => e.sourceHandle !== "fail");
  graph.nodes!.find((n) => n.id === "n_ba")!.data!.agent_id = "outside-project";
  const issues = validateGraph(graph, agents);
  expect(
    issues.some((i) => i.nodeId === "n_test" && i.message.includes("fail")),
  ).toBe(true);
  expect(
    issues.some((i) => i.nodeId === "n_ba" && i.message.includes("project")),
  ).toBe(true);
});
test("a bypass to Git release fails even when another path has confirmation", () => {
  const graph = templateGraph("bugfix_default", agents);
  graph.edges!.push({
    id: "bypass",
    source: "n_dev",
    target: "n_lead",
    sourceHandle: null,
  });
  expect(
    validateGraph(graph, agents).some(
      (i) => i.nodeId === "n_lead" && i.message.includes("approved"),
    ),
  ).toBe(true);
});
test("empty control loops and invalid expressions are rejected", () => {
  const graph = templateGraph("blank", agents);
  graph.nodes!.push({
    id: "cond",
    type: "condition",
    data: { expression: "__import__('os')" },
  });
  graph.edges = [
    { id: "a", source: "start", target: "cond" },
    { id: "b", source: "cond", target: "cond", sourceHandle: "true" },
    { id: "c", source: "cond", target: "end", sourceHandle: "false" },
  ];
  const issues = validateGraph(graph, agents);
  expect(issues.some((i) => i.message.includes("expression"))).toBe(true);
  expect(issues.some((i) => i.message.includes("chu trình"))).toBe(true);
});
test("text-only API agent cannot run developer or tester and iteration limit must be positive", () => {
  const graph = templateGraph("bugfix_default", agents);
  graph.nodes!.find((n) => n.id === "n_dev")!.data!.max_iterations = 0;
  const apiAgents = agents.map((a) =>
    a.role_key === "DEVELOPER" ? { ...a, runtime: "openai-api" as const } : a,
  );
  const issues = validateGraph(graph, apiAgents);
  expect(issues.some((i) => i.message.includes("OpenAI Custom"))).toBe(true);
  expect(issues.some((i) => i.message.includes("vòng lặp"))).toBe(true);
});
