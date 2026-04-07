"use client";

import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import CourseTestPage from "@/app/courses/[courseId]/tests/[attemptId]/page";

const replaceMock = vi.fn();

vi.mock("next/navigation", () => ({
  useRouter: () => ({
    replace: replaceMock,
    push: vi.fn(),
  }),
  useParams: () => ({
    courseId: "course-1",
    attemptId: "attempt-1",
  }),
}));


function createJsonResponse(payload: unknown, status = 200): Response {
  return new Response(JSON.stringify(payload), {
    status,
    headers: {
      "Content-Type": "application/json",
    },
  });
}


describe("Course test page", () => {
  beforeEach(() => {
    window.localStorage.clear();
    window.sessionStorage.clear();
    window.localStorage.setItem("auth_token", "student-token");
    replaceMock.mockReset();
    vi.spyOn(console, "warn").mockImplementation(() => undefined);
    vi.spyOn(console, "log").mockImplementation(() => undefined);
  });


  it("shows paused state then resumes into active question flow", async () => {
    const user = userEvent.setup();
    const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const path = String(input);
      const method = init?.method ?? "GET";

      if (path === "/api/amls/courses/course-1/tests/current") {
        return createJsonResponse({
          test_attempt: {
            id: "attempt-1",
            user_id: "user-1",
            graph_version_id: "graph-version-1",
            kind: "general",
            status: "paused",
            current_problem_id: "problem-1",
            config_snapshot: {},
            metadata_json: {},
            started_at: "2026-04-03T10:00:00.000Z",
            paused_at: "2026-04-03T10:00:12.000Z",
            total_paused_seconds: 0,
            elapsed_solve_seconds: 12,
            ended_at: null,
            created_at: "2026-04-03T10:00:00.000Z",
            updated_at: "2026-04-03T10:00:12.000Z",
          },
          problem: {
            id: "problem-1",
            subtopic: { id: "sub-1", topic_id: "topic-1", name: "Subtopic" },
            difficulty: { key: "intermediate", name: "Intermediate", coefficient: 0.75 },
            problem_type: { id: "type-1", name: "Linear equations", prerequisite_ids: [] },
            course_node: null,
            condition: "$x + 1 = 2$",
            condition_images: [],
            answer_options: [
              { id: "answer-1", text: "$x = 1$" },
              { id: "answer-2", text: "$x = 0$" },
            ],
          },
        });
      }

      if (path === "/api/amls/tests/attempt-1/resume" && method === "POST") {
        return createJsonResponse({
          test_attempt: {
            id: "attempt-1",
            user_id: "user-1",
            graph_version_id: "graph-version-1",
            kind: "general",
            status: "active",
            current_problem_id: "problem-1",
            config_snapshot: {},
            metadata_json: {},
            started_at: "2026-04-03T10:00:00.000Z",
            paused_at: null,
            total_paused_seconds: 1,
            elapsed_solve_seconds: 12,
            ended_at: null,
            created_at: "2026-04-03T10:00:00.000Z",
            updated_at: "2026-04-03T10:00:13.000Z",
          },
          problem: {
            id: "problem-1",
            subtopic: { id: "sub-1", topic_id: "topic-1", name: "Subtopic" },
            difficulty: { key: "intermediate", name: "Intermediate", coefficient: 0.75 },
            problem_type: { id: "type-1", name: "Linear equations", prerequisite_ids: [] },
            course_node: null,
            condition: "$x + 1 = 2$",
            condition_images: [],
            answer_options: [
              { id: "answer-1", text: "$x = 1$" },
              { id: "answer-2", text: "$x = 0$" },
            ],
          },
        });
      }

      return createJsonResponse({});
    });
    vi.stubGlobal("fetch", fetchMock);

    render(<CourseTestPage />);
    expect(await screen.findByRole("button", { name: "Resume test" })).toBeInTheDocument();
    expect(screen.queryByText("Submit answer")).not.toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Resume test" }));

    await waitFor(() => {
      expect(screen.getByText("Submit answer")).toBeInTheDocument();
    });
  });


  it("shows calculating score screen after terminal answer then renders final review", async () => {
    const user = userEvent.setup();
    const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const path = String(input);
      const method = init?.method ?? "GET";

      if (path === "/api/amls/courses/course-1/tests/current") {
        return createJsonResponse({
          test_attempt: {
            id: "attempt-1",
            user_id: "user-1",
            graph_version_id: "graph-version-1",
            kind: "general",
            status: "active",
            current_problem_id: "problem-1",
            config_snapshot: {},
            metadata_json: {},
            started_at: "2026-04-03T10:00:00.000Z",
            paused_at: null,
            total_paused_seconds: 0,
            elapsed_solve_seconds: 12,
            ended_at: null,
            created_at: "2026-04-03T10:00:00.000Z",
            updated_at: "2026-04-03T10:00:12.000Z",
          },
          problem: {
            id: "problem-1",
            subtopic: { id: "sub-1", topic_id: "topic-1", name: "Subtopic" },
            difficulty: { key: "intermediate", name: "Intermediate", coefficient: 0.75 },
            problem_type: { id: "type-1", name: "Linear equations", prerequisite_ids: [] },
            course_node: null,
            condition: "$x + 1 = 2$",
            condition_images: [],
            answer_options: [
              { id: "answer-1", text: "$x = 1$" },
              { id: "answer-2", text: "$x = 0$" },
            ],
          },
        });
      }

      if (path === "/api/amls/tests/attempt-1/answers" && method === "POST") {
        return createJsonResponse({
          test_attempt: {
            id: "attempt-1",
            user_id: "user-1",
            graph_version_id: "graph-version-1",
            kind: "general",
            status: "completed",
            current_problem_id: null,
            config_snapshot: {},
            metadata_json: {},
            started_at: "2026-04-03T10:00:00.000Z",
            paused_at: null,
            total_paused_seconds: 0,
            elapsed_solve_seconds: 14,
            ended_at: "2026-04-03T10:00:14.000Z",
            created_at: "2026-04-03T10:00:00.000Z",
            updated_at: "2026-04-03T10:00:14.000Z",
          },
          response: {
            response_id: "response-1",
            problem_id: "problem-1",
            answer_option_id: "answer-1",
            answer_option_type: "right",
            revealed_solution: false,
          },
          next_problem: null,
          graph_assessment: null,
        }, 201);
      }

      if (path === "/api/amls/tests/attempt-1/review") {
        await new Promise((resolve) => setTimeout(resolve, 12));
        return createJsonResponse({
          test_attempt: {
            id: "attempt-1",
            user_id: "user-1",
            graph_version_id: "graph-version-1",
            kind: "general",
            status: "completed",
            current_problem_id: null,
            config_snapshot: {},
            metadata_json: {},
            started_at: "2026-04-03T10:00:00.000Z",
            paused_at: null,
            total_paused_seconds: 0,
            elapsed_solve_seconds: 14,
            ended_at: "2026-04-03T10:00:14.000Z",
            created_at: "2026-04-03T10:00:00.000Z",
            updated_at: "2026-04-03T10:00:14.000Z",
          },
          items: [
            {
              response_id: "response-1",
              problem: {
                id: "problem-1",
                subtopic: { id: "sub-1", topic_id: "topic-1", name: "Subtopic" },
                difficulty: { key: "intermediate", name: "Intermediate", coefficient: 0.75 },
                problem_type: { id: "type-1", name: "Linear equations", prerequisite_ids: [] },
                course_node: null,
                condition: "$x + 1 = 2$",
                condition_images: [],
                answer_options: [
                  { id: "answer-1", text: "$x = 1$" },
                  { id: "answer-2", text: "$x = 0$" },
                ],
              },
              chosen_answer_option_id: "answer-1",
              chosen_answer_option_type: "right",
              revealed_solution: false,
              solution: "$x = 1$",
              solution_images: [],
              created_at: "2026-04-03T10:00:14.000Z",
            },
          ],
        });
      }

      if (path === "/api/amls/courses/course-1/graph-assessments") {
        return createJsonResponse([
          {
            id: "assessment-1",
            user_id: "user-1",
            graph_version_id: "graph-version-1",
            source_test_attempt_id: "attempt-1",
            state: {
              learned_course_node_ids: ["node-1"],
              ready_course_node_ids: [],
              locked_course_node_ids: [],
              failed_course_node_ids: [],
              answered_course_node_ids: ["node-1"],
            },
            state_confidence: 1,
            is_active: true,
            assessment_kind: "general",
            metadata_json: {},
            review_status: "succeeded",
            review_text: "You solved this problem type with strong accuracy.",
            review_recommendations: ["Continue with systems of equations"],
            review_model: "qwen",
            review_error: null,
            review_generated_at: "2026-04-03T10:00:14.000Z",
            measured_at: "2026-04-03T10:00:14.000Z",
            created_at: "2026-04-03T10:00:14.000Z",
            updated_at: "2026-04-03T10:00:14.000Z",
          },
        ]);
      }

      return createJsonResponse({}, 404);
    });
    vi.stubGlobal("fetch", fetchMock);

    render(<CourseTestPage />);

    const answerOptionText = await screen.findByText("$x = 1$");
    const answerOptionButton = answerOptionText.closest("button");
    expect(answerOptionButton).not.toBeNull();
    if (!answerOptionButton) {
      throw new Error("Expected answer option button to exist");
    }

    await user.click(answerOptionButton);
    await user.click(screen.getByRole("button", { name: "Submit answer" }));

    expect(await screen.findByText("Calculating your score...")).toBeInTheDocument();
    await waitFor(() => {
      expect(screen.getByText("Result summary")).toBeInTheDocument();
    });
    expect(screen.getByText("Score: 1/1 (100%)")).toBeInTheDocument();
  });
});
