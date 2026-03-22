"use client";

import { useState } from "react";
import type { ReactNode } from "react";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import Home from "@/app/page";

vi.mock("@/components/EntranceTest", () => ({
  default: ({ token }: { token: string }) => (
    <div data-testid="entrance-test-mock">Entrance mock for {token}</div>
  ),
}));

vi.mock("@xyflow/react", () => ({
  Background: () => <div data-testid="graph-background" />,
  Controls: () => <div data-testid="graph-controls" />,
  MiniMap: () => <div data-testid="graph-minimap" />,
  Position: {
    Left: "left",
    Right: "right",
    Top: "top",
    Bottom: "bottom",
  },
  ReactFlow: ({
    nodes,
    edges,
    children,
  }: {
    nodes: Array<{ id: string }>;
    edges: Array<{ id: string }>;
    children?: ReactNode;
  }) => (
    <div
      data-edge-count={edges.length}
      data-node-count={nodes.length}
      data-testid="knowledge-graph-flow"
    >
      {children}
    </div>
  ),
  useNodesState: (initialNodes: Array<{ id: string }>) => {
    const [nodes, setNodes] = useState(initialNodes);

    return [nodes, setNodes, vi.fn()] as const;
  },
  useEdgesState: (initialEdges: Array<{ id: string }>) => {
    const [edges, setEdges] = useState(initialEdges);

    return [edges, setEdges, vi.fn()] as const;
  },
}));

const graphResponsePayload = {
  roots: [
    {
      id: "problem-type-root",
      name: "Algebra base",
      prerequisite_ids: [],
      children: [
        {
          id: "problem-type-child",
          name: "Algebra extension",
          prerequisite_ids: ["problem-type-root"],
          children: [],
        },
      ],
    },
  ],
};


function createJsonResponse(payload: unknown, status = 200): Response {
  return new Response(JSON.stringify(payload), {
    status,
    headers: {
      "Content-Type": "application/json",
    },
  });
}


function createLocalStorageMock(): Storage {
  const storageState = new Map<string, string>();

  return {
    get length() {
      return storageState.size;
    },
    clear() {
      storageState.clear();
    },
    getItem(key: string) {
      return storageState.get(key) ?? null;
    },
    key(index: number) {
      return Array.from(storageState.keys())[index] ?? null;
    },
    removeItem(key: string) {
      storageState.delete(key);
    },
    setItem(key: string, value: string) {
      storageState.set(key, value);
    },
  };
}


describe("Home page shell", () => {
  beforeEach(() => {
    const localStorageMock = createLocalStorageMock();

    Object.defineProperty(window, "localStorage", {
      configurable: true,
      value: localStorageMock,
    });

    Object.defineProperty(globalThis, "localStorage", {
      configurable: true,
      value: localStorageMock,
    });

    document.documentElement.classList.remove("dark", "light");
    document.documentElement.removeAttribute("data-theme");
    vi.stubGlobal(
      "fetch",
      vi.fn(async (input: RequestInfo | URL) => {
        if (String(input) === "/api/graph") {
          return createJsonResponse(graphResponsePayload);
        }

        return createJsonResponse({});
      }),
    );
    vi.spyOn(console, "log").mockImplementation(() => undefined);
    vi.spyOn(console, "error").mockImplementation(() => undefined);
  });


  it("renders the authenticated shell, applies persisted theme, toggles theme, and switches tabs", async () => {
    const user = userEvent.setup();

    window.localStorage.setItem("auth_token", "student-token");
    window.localStorage.setItem("amls_theme", "light");

    render(<Home />);

    expect(await screen.findByText("Adaptive Math Learning System")).toBeInTheDocument();

    await waitFor(() => {
      expect(document.documentElement).toHaveClass("light");
      expect(document.documentElement.dataset.theme).toBe("light");
    });

    await waitFor(() => {
      expect(screen.getByTestId("knowledge-graph-flow")).toHaveAttribute("data-node-count", "2");
      expect(screen.getByTestId("knowledge-graph-flow")).toHaveAttribute("data-edge-count", "1");
    });

    await user.click(screen.getByTestId("app-theme-toggle"));

    await waitFor(() => {
      expect(document.documentElement).toHaveClass("dark");
      expect(window.localStorage.getItem("amls_theme")).toBe("dark");
    });

    await user.click(screen.getByRole("button", { name: /Entrance Test/i }));
    expect(await screen.findByTestId("entrance-test-mock")).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: /Knowledge Graph/i }));
    expect(await screen.findByTestId("knowledge-graph-view")).toBeInTheDocument();
  });
});
