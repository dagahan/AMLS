"use client";

import { Handle, Position } from "@xyflow/react";
import type { Node, NodeProps } from "@xyflow/react";
import MathText from "@/components/MathText";

export type MathFlowNodeTone = "default" | "learned" | "ready" | "locked";

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
  sourcePosition = Position.Bottom,
  targetPosition = Position.Top,
}: NodeProps<MathFlowGraphNode>) {
  return (
    <div
      data-tone={data.tone ?? "default"}
      className="flow-node"
      style={{
        boxShadow: data.isFrontier
          ? "0 0 0 4px var(--graph-status-frontier-ring)"
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
