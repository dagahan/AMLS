"use client";

import { render, screen, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import CourseWorkspacePage from "@/app/courses/[courseId]/workspace/page";

const replaceMock = vi.fn();
const pushMock = vi.fn();

vi.mock("next/navigation", () => ({
  useRouter: () => ({
    replace: replaceMock,
    push: pushMock,
  }),
  useParams: () => ({
    courseId: "course-1",
  }),
}));

vi.mock("@xyflow/react", () => ({
  Background: () => null,
  Controls: () => null,
  MiniMap: () => null,
  ReactFlow: ({ children }: { children: ReactNode }) => <div>{children}</div>,
  useNodesState: () => [[], vi.fn(), vi.fn()],
  useEdgesState: () => [[], vi.fn(), vi.fn()],
}));


function createJsonResponse(payload: unknown, status = 200): Response {
  return new Response(JSON.stringify(payload), {
    status,
    headers: {
      "Content-Type": "application/json",
    },
  });
}


describe("Course workspace page", () => {
  beforeEach(() => {
    window.localStorage.clear();
    window.sessionStorage.clear();
    window.localStorage.setItem("auth_token", "student-token");
    replaceMock.mockReset();
    pushMock.mockReset();
    vi.spyOn(console, "warn").mockImplementation(() => undefined);
    vi.spyOn(console, "log").mockImplementation(() => undefined);
  });


  it("keeps mastery summary compact without quick practice and embedded history button", async () => {
    const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
      const path = String(input);
      if (path !== "/api/amls/courses/course-1/workspace") {
        return createJsonResponse({}, 404);
      }

      return createJsonResponse({
        course: {
          id: "course-1",
          author_id: "admin-1",
          current_graph_version_id: "graph-version-1",
          title: "Profile Mathematics (Grades 10-11)",
          description: "Course description",
          created_at: "2026-04-03T10:00:00.000Z",
          updated_at: "2026-04-03T10:00:00.000Z",
        },
        graph_version: {
          id: "graph-version-1",
          course_id: "course-1",
          version_number: 1,
          status: "ready",
          node_count: 1,
          edge_count: 0,
          built_at: "2026-04-03T10:00:00.000Z",
          error_message: null,
          created_at: "2026-04-03T10:00:00.000Z",
          updated_at: "2026-04-03T10:00:00.000Z",
        },
        nodes: [
          {
            course_node_id: "node-1",
            problem_type_id: "problem-type-1",
            name: "solve linear equations",
            lecture_id: "lecture-1",
            has_lecture: true,
            topological_rank: 0,
            mastery_state: "ready",
            is_frontier: true,
          },
        ],
        edges: [],
        active_test_attempt: null,
        active_graph_assessment: null,
        latest_graph_assessment: {
          id: "assessment-1",
          user_id: "user-1",
          graph_version_id: "graph-version-1",
          source_test_attempt_id: "attempt-1",
          state: {
            learned_course_node_ids: [],
            ready_course_node_ids: ["node-1"],
            locked_course_node_ids: [],
            failed_course_node_ids: [],
            answered_course_node_ids: ["node-1"],
          },
          state_confidence: 0.75,
          is_active: true,
          assessment_kind: "general",
          metadata_json: {},
          review_status: "succeeded",
          review_text: "```json {\"review_text\":\"Ready to advance on linear equations.\",\"recommendations\":[\"Start systems of equations practice\"]} ```",
          review_recommendations: [],
          review_model: "qwen2.5-coder-3b-instruct-mlx",
          review_error: null,
          review_generated_at: "2026-04-03T10:02:00.000Z",
          measured_at: "2026-04-03T10:01:00.000Z",
          created_at: "2026-04-03T10:01:00.000Z",
          updated_at: "2026-04-03T10:01:00.000Z",
        },
        latest_review: {
          graph_assessment_id: "assessment-1",
          review_status: "succeeded",
          review_text: "Ready to advance on linear equations.",
          review_recommendations: ["Start systems of equations practice"],
          review_model: "qwen2.5-coder-3b-instruct-mlx",
          review_error: null,
          review_generated_at: "2026-04-03T10:02:00.000Z",
        },
        action_flags: {
          can_start_entrance: false,
          can_start_practice: true,
          can_start_exam: true,
          can_start_mistakes: true,
          has_active_attempt: false,
          has_active_assessment: true,
        },
      });
    });
    vi.stubGlobal("fetch", fetchMock);

    render(<CourseWorkspacePage />);

    await waitFor(() => {
      expect(screen.getByText("Review status: succeeded • Confidence: 75%")).toBeInTheDocument();
    });
    expect(screen.queryByRole("button", { name: "Quick practice" })).not.toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "Go to test history" })).not.toBeInTheDocument();
    expect(screen.queryByText("Ready to advance on linear equations.")).not.toBeInTheDocument();
    expect(screen.queryByText("• Start systems of equations practice")).not.toBeInTheDocument();
  });
});
