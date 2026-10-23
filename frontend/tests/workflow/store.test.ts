import { expect, test } from "vitest";
import {
  createWorkflowStore,
  validConnection,
} from "@/components/workflow/store";
import { templateGraph } from "@/components/workflow/templates";
import { graphKey } from "@/components/workflow/serialize";
import { autoLayout } from "@/components/workflow/layout";
test("30 nodes support delete, duplicate, layout and history without recording selection", () => {
  const store = createWorkflowStore(templateGraph("blank", []));
  for (let i = 0; i < 30; i++)
    store
      .getState()
      .addNode({
        id: `extra${i}`,
        type: "agent",
        position: { x: i * 20, y: 50 },
        data: {},
      });
  const count = store.temporal.getState().pastStates.length;
  store.getState().select("extra10");
  expect(store.temporal.getState().pastStates.length).toBe(count);
  store.getState().duplicateSelected();
  expect(store.getState().nodes).toHaveLength(33);
  store.temporal.getState().undo();
  expect(store.getState().nodes).toHaveLength(32);
  store.temporal.getState().redo();
  expect(store.getState().nodes).toHaveLength(33);
  store.getState().removeSelected();
  expect(store.getState().nodes).toHaveLength(32);
  store.setState(autoLayout(store.getState()));
  expect(
    store.getState().nodes.every((n) => Number.isFinite(n.position.x)),
  ).toBe(true);
  expect(graphKey(store.getState())).not.toBe(store.getState().savedKey);
});
test("connection guard prevents self, start incoming, end outgoing and duplicate source handles", () => {
  const store = createWorkflowStore(templateGraph("blank", []));
  const connection = (source: string, target: string) =>
    validConnection(
      { source, target, sourceHandle: "default" },
      store.getState(),
    );
  expect(connection("start", "start")).toBe(false);
  expect(connection("end", "start")).toBe(false);
  expect(connection("start", "end")).toBe(false);
  store.setState({ edges: [] });
  expect(connection("start", "end")).toBe(true);
});
