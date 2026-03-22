"use client";

import type { ReactNode } from "react";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import EntranceTest from "@/components/EntranceTest";
import type {
  EntranceTestAnswerResponse,
  EntranceTestCurrentProblemResponse,
  EntranceTestResultResponse,
  EntranceTestSessionResponse,
  ProblemResponse,
} from "@/lib/api-types";

vi.mock("@xyflow/react", () => ({
  Background: () => <div data-testid="graph-background" />,
  Controls: () => <div data-testid="graph-controls" />,
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
      data-testid="react-flow"
    >
      {children}
    </div>
  ),
  MarkerType: {
    ArrowClosed: "arrowclosed",
  },
  Position: {
    Left: "left",
    Right: "right",
    Top: "top",
    Bottom: "bottom",
  },
}));

const completedSessionPayload: EntranceTestSessionResponse = {
  id: "session-completed",
  status: "completed",
  structure_version: 5,
  current_problem_id: null,
  final_result: {
    state_index: 12,
    state_probability: 0.81,
    learned_problem_type_ids: ["problem-type-1"],
    inner_fringe_ids: ["problem-type-1"],
    outer_fringe_ids: ["problem-type-2"],
  },
  started_at: "2026-03-22T08:00:00.000Z",
  completed_at: "2026-03-22T08:12:00.000Z",
  skipped_at: null,
};

const activeProblemPayload: ProblemResponse = {
  id: "problem-1",
  subtopic: {
    id: "subtopic-1",
    topic_id: "topic-1",
    name: "Systems",
  },
  difficulty: {
    id: "difficulty-1",
    name: "medium",
    coefficient: 1.2,
  },
  problem_type: {
    id: "problem-type-1",
    name: "Solve systems",
    prerequisite_ids: [],
  },
  condition: "Choose the correct next step.",
  condition_images: [],
  answer_options: [
    {
      id: "answer-right",
      text: "A right answer",
    },
    {
      id: "answer-wrong",
      text: "A wrong answer",
    },
  ],
};

const activeSessionPayload: EntranceTestSessionResponse = {
  id: "session-active",
  status: "active",
  structure_version: 5,
  current_problem_id: activeProblemPayload.id,
  final_result: null,
  started_at: "2026-03-22T08:00:00.000Z",
  completed_at: null,
  skipped_at: null,
};

const currentProblemResponsePayload: EntranceTestCurrentProblemResponse = {
  session: activeSessionPayload,
  problem: activeProblemPayload,
};

const entranceTestResultPayload: EntranceTestResultResponse = {
  session: completedSessionPayload,
  final_result: {
    state_index: 12,
    state_probability: 0.81,
    learned_problem_type_ids: ["problem-type-1"],
    inner_fringe_ids: ["problem-type-1"],
    outer_fringe_ids: ["problem-type-2"],
  },
  nodes: [
    {
      id: "problem-type-1",
      name: "Solve systems",
      topic_id: "topic-1",
      topic_name: "Algebra",
      subtopic_id: "subtopic-1",
      subtopic_name: "Systems",
      status: "learned",
      is_frontier: true,
    },
    {
      id: "problem-type-2",
      name: "Graph equations",
      topic_id: "topic-1",
      topic_name: "Algebra",
      subtopic_id: "subtopic-2",
      subtopic_name: "Graphing",
      status: "ready",
      is_frontier: false,
    },
    {
      id: "problem-type-3",
      name: "Use elimination",
      topic_id: "topic-1",
      topic_name: "Algebra",
      subtopic_id: "subtopic-1",
      subtopic_name: "Systems",
      status: "locked",
      is_frontier: false,
    },
  ],
  edges: [
    {
      from_problem_type_id: "problem-type-1",
      to_problem_type_id: "problem-type-2",
    },
    {
      from_problem_type_id: "problem-type-2",
      to_problem_type_id: "problem-type-3",
    },
  ],
  topic_summaries: [
    {
      topic_id: "topic-1",
      topic_name: "Algebra",
      total_problem_types: 3,
      learned_count: 1,
      ready_count: 1,
      frontier_count: 1,
      locked_count: 1,
    },
  ],
  subtopic_summaries: [
    {
      subtopic_id: "subtopic-1",
      subtopic_name: "Systems",
      topic_id: "topic-1",
      topic_name: "Algebra",
      total_problem_types: 2,
      learned_count: 1,
      ready_count: 0,
      frontier_count: 1,
      locked_count: 1,
    },
    {
      subtopic_id: "subtopic-2",
      subtopic_name: "Graphing",
      topic_id: "topic-1",
      topic_name: "Algebra",
      total_problem_types: 1,
      learned_count: 0,
      ready_count: 1,
      frontier_count: 0,
      locked_count: 0,
    },
  ],
};

const completedAnswerPayload: EntranceTestAnswerResponse = {
  session: completedSessionPayload,
  response: {
    id: "response-1",
    problem_id: activeProblemPayload.id,
    answer_option_id: "answer-right",
    is_correct: true,
    created_at: "2026-03-22T08:10:00.000Z",
  },
  next_problem: null,
  final_result: entranceTestResultPayload.final_result,
};


function createJsonResponse(payload: unknown, status = 200): Response {
  return new Response(JSON.stringify(payload), {
    status,
    headers: {
      "Content-Type": "application/json",
    },
  });
}


describe("EntranceTest", () => {
  beforeEach(() => {
    vi.stubGlobal("fetch", vi.fn());
    vi.spyOn(console, "log").mockImplementation(() => undefined);
    vi.spyOn(console, "error").mockImplementation(() => undefined);
  });


  it("renders the completed entrance test result with graph metrics and summaries", async () => {
    const fetchMock = vi.mocked(fetch);

    fetchMock.mockResolvedValueOnce(createJsonResponse(completedSessionPayload));
    fetchMock.mockResolvedValueOnce(createJsonResponse(entranceTestResultPayload));

    render(<EntranceTest token="student-token" />);

    expect(await screen.findByText("Entrance Test Completed")).toBeInTheDocument();
    expect(screen.getByText("Estimated Knowledge State")).toBeInTheDocument();
    expect(screen.getByText("State 12")).toBeInTheDocument();
    expect(screen.getByText("Confidence 81.0%")).toBeInTheDocument();
    expect(screen.getByText("Topic Summaries")).toBeInTheDocument();
    expect(screen.getByText("Subtopic Summaries")).toBeInTheDocument();
    expect(screen.getAllByText("Algebra")).not.toHaveLength(0);
    expect(screen.getByText("1 learned / 1 ready / 1 frontier / 1 locked")).toBeInTheDocument();
    expect(screen.getByText("Systems")).toBeInTheDocument();
    expect(screen.getByText("1 learned / 0 ready / 1 frontier / 1 locked")).toBeInTheDocument();
    expect(screen.getByTestId("entrance-test-result-graph")).toBeInTheDocument();

    await waitFor(() => {
      expect(screen.getByTestId("react-flow")).toHaveAttribute("data-node-count", "3");
      expect(screen.getByTestId("react-flow")).toHaveAttribute("data-edge-count", "2");
    });
  });


  it("fetches and renders the personalized graph immediately after the final answer completes the test", async () => {
    const user = userEvent.setup();
    const fetchMock = vi.mocked(fetch);

    fetchMock.mockResolvedValueOnce(createJsonResponse(activeSessionPayload));
    fetchMock.mockResolvedValueOnce(createJsonResponse(currentProblemResponsePayload));
    fetchMock.mockResolvedValueOnce(createJsonResponse(completedAnswerPayload, 201));
    fetchMock.mockResolvedValueOnce(createJsonResponse(entranceTestResultPayload));

    render(<EntranceTest token="student-token" />);

    expect(await screen.findByText("Choose the correct next step.")).toBeInTheDocument();

    await user.click(screen.getByText("A right answer"));
    await user.click(screen.getByRole("button", { name: "Next Question" }));

    expect(await screen.findByText("Entrance Test Completed")).toBeInTheDocument();

    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledWith(
        "/api/entrance-test/result",
        expect.objectContaining({
          headers: {
            Authorization: "Bearer student-token",
          },
        }),
      );
    });

    expect(screen.getByTestId("entrance-test-result-graph")).toBeInTheDocument();
  });
});
