"use client";
import {
  BaseEdge,
  EdgeLabelRenderer,
  getBezierPath,
  type EdgeProps,
} from "@xyflow/react";
import { handleLabels } from "../nodes/BaseNode";
export function LabeledEdge(props: EdgeProps) {
  const [path, x, y] = getBezierPath(props);
  const failed = ["fail", "failed", "rejected", "false"].includes(
    props.sourceHandleId || "",
  );
  return (
    <>
      <BaseEdge
        id={props.id}
        path={path}
        markerEnd={props.markerEnd}
        style={{
          stroke: props.selected ? "#2563eb" : failed ? "#dc2626" : "#78716c",
          strokeWidth: props.selected ? 3 : 1.5,
        }}
      />
      <EdgeLabelRenderer>
        <span
          className="pointer-events-none absolute rounded border border-stone-200 bg-white px-1.5 py-0.5 text-[10px]"
          style={{
            transform: `translate(-50%, -50%) translate(${x}px,${y}px)`,
            color: failed ? "#b91c1c" : "#57534e",
          }}
        >
          {handleLabels[props.sourceHandleId || "default"] ||
            props.sourceHandleId}
        </span>
      </EdgeLabelRenderer>
    </>
  );
}
