"use client";

import { render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import CourseTestHistoryPage from "@/app/courses/[courseId]/tests/history/page";

const replaceMock = vi.fn();

vi.mock("next/navigation", () => ({
  useRouter: () => ({
    replace: replaceMock,
  }),
  useParams: () => ({
    courseId: "course-1",
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


describe("Course test history page", () => {
  beforeEach(() => {
    window.localStorage.clear();
    window.sessionStorage.clear();
    window.localStorage.setItem("auth_token", "student-token");
    replaceMock.mockReset();
    vi.spyOn(console, "warn").mockImplementation(() => undefined);
    vi.spyOn(console, "log").mockImplementation(() => undefined);
  });


  it("renders history list and score summaries", async () => {
    const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
      const path = String(input);

      if (path === "/api/amls/courses/course-1/tests/history") {
        return createJsonResponse({
          attempts: [
            {
              id: "attempt-1",
              graph_version_id: "graph-version-1",
              kind: "general",
              status: "completed",
              started_at: "2026-04-03T10:00:00.000Z",
              ended_at: "2026-04-03T10:05:00.000Z",
              created_at: "2026-04-03T10:00:00.000Z",
              updated_at: "2026-04-03T10:05:00.000Z",
            },
          ],
        });
      }

      if (path === "/api/amls/tests/attempt-1/review") {
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
            elapsed_solve_seconds: 300,
            ended_at: "2026-04-03T10:05:00.000Z",
            created_at: "2026-04-03T10:00:00.000Z",
            updated_at: "2026-04-03T10:05:00.000Z",
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
                ],
              },
              chosen_answer_option_id: "answer-1",
              chosen_answer_option_type: "right",
              revealed_solution: false,
              solution: "$x = 1$",
              solution_images: [],
              created_at: "2026-04-03T10:04:59.000Z",
            },
          ],
        });
      }

      return createJsonResponse({}, 404);
    });
    vi.stubGlobal("fetch", fetchMock);

    render(<CourseTestHistoryPage />);

    await waitFor(() => {
      expect(screen.getByText("Attempt list")).toBeInTheDocument();
    });
    expect(screen.getByText("Practice • Completed")).toBeInTheDocument();
    expect(screen.getByText("Score: 1/1 (100%)")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Open review" })).toBeInTheDocument();
  });
});
