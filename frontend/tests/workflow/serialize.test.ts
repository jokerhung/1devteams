import { describe, expect, test } from "vitest";
import { deserialize, serialize } from "@/components/workflow/serialize";
import { templateGraph } from "@/components/workflow/templates";
describe("workflow serialization", () => {
  test("template round trip excludes React Flow internals and UI decorations", () => {
    const graph = templateGraph("bugfix_default", []);
    const state = deserialize(graph);
    state.nodes[0] = {
      ...state.nodes[0],
      selected: true,
      dragging: true,
      measured: { width: 250, height: 120 },
      data: {
        ...state.nodes[0].data,
        _errors: ["warning"],
        _status: "running",
      },
    };
    state.edges[0].selected = true;
    expect(serialize(state)).toEqual(graph);
    expect(Object.keys(serialize(state).nodes![0]).sort()).toEqual([
      "data",
      "id",
      "position",
      "type",
    ]);
  });
  test("legacy default GitRelease handle is preserved while render metadata is removed", () => {
    const graph = templateGraph("bugfix_default", []);
    graph.edges!.find((e) => e.source === "n_lead")!.sourceHandle = null;
    const state = deserialize(graph);
    expect(
      state.nodes.find((n) => n.id === "n_lead")!.data._legacyDefault,
    ).toBe(true);
    expect(serialize(state)).toEqual(graph);
  });
});
