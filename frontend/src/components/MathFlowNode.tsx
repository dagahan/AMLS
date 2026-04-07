"use client";

import { Handle, Position } from "@xyflow/react";
import type { Node, NodeProps } from "@xyflow/react";
import MathText from "@/components/MathText";

export type MathFlowNodeTone = "default" | "learned" | "ready" | "locked" | "failed";

export interface MathFlowNodeData extends Record<string, unknown> {
  label: string;
  badge?: string;
  subtitle?: string;
  tone?: MathFlowNodeTone;
  isFrontier?: boolean;
}

export type MathFlowGraphNode = Node<MathFlowNodeData, "mathNode">;


export default function MathFlowNode({
  data,
  selected,
  sourcePosition = Position.Bottom,
  targetPosition = Position.Top,
}: NodeProps<MathFlowGraphNode>) {
  return (
    <div
      data-tone={data.tone ?? "default"}
      data-frontier={data.isFrontier ? "true" : "false"}
      data-selected={selected ? "true" : "false"}
      className="flow-node"
      style={{
        boxShadow: data.isFrontier
          ? "var(--graph-node-shadow), 0 0 0 4px var(--graph-status-frontier-ring), 0 0 32px var(--graph-status-frontier-glow)"
          : "var(--graph-node-shadow)",
      }}
    >
      <Handle
        className="flow-node-handle"
        position={targetPosition}
        type="target"
      />
      {data.badge ? <div className="flow-node-badge">{data.badge}</div> : null}
      <MathText content={data.label} className="flow-node-label" />
      {data.subtitle ? <div className="flow-node-subtitle">{data.subtitle}</div> : null}
      <Handle
        className="flow-node-handle"
        position={sourcePosition}
        type="source"
      />
    </div>
  );
}
