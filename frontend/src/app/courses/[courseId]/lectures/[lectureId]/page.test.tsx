"use client";

import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import CourseLecturePage from "@/app/courses/[courseId]/lectures/[lectureId]/page";

let queryString = "page=2";

const replaceMock = vi.fn((url: string) => {
  const parsedUrl = new URL(url, "http://localhost");
  queryString = parsedUrl.searchParams.toString();
});
const pushMock = vi.fn();
const routerMock = {
  replace: replaceMock,
  push: pushMock,
};
const searchParamsMock = {
  get: (key: string) => new URLSearchParams(queryString).get(key),
  toString: () => queryString,
} as unknown as URLSearchParams;

vi.mock("next/navigation", () => ({
  useRouter: () => routerMock,
  useParams: () => ({
    courseId: "course-1",
    lectureId: "lecture-1",
  }),
  useSearchParams: () => searchParamsMock,
}));


function createJsonResponse(payload: unknown, status = 200): Response {
  return new Response(JSON.stringify(payload), {
    status,
    headers: {
      "Content-Type": "application/json",
    },
  });
}


describe("Course lecture page", () => {
  beforeEach(() => {
    window.localStorage.clear();
    window.sessionStorage.clear();
    window.localStorage.setItem("auth_token", "student-token");
    queryString = "page=2";
    replaceMock.mockClear();
    pushMock.mockClear();
    vi.spyOn(console, "warn").mockImplementation(() => undefined);
    vi.spyOn(console, "log").mockImplementation(() => undefined);
  });


  it("shows one lecture page at a time and navigates with page query", async () => {
    const user = userEvent.setup();
    const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
      const requestUrl = input instanceof Request
        ? input.url
        : input instanceof URL
          ? input.toString()
          : String(input);
      const path = new URL(requestUrl, "http://localhost").pathname;
      if (path !== "/api/amls/lectures/lecture-1") {
        return createJsonResponse({}, 404);
      }

      return createJsonResponse({
        lecture: {
          id: "lecture-1",
          course_node_id: "node-1",
          title: "Lecture: solve linear equations",
          created_at: "2026-04-03T10:00:00.000Z",
          updated_at: "2026-04-03T10:00:00.000Z",
        },
        pages: [
          {
            id: "page-1",
            lecture_id: "lecture-1",
            page_number: 1,
            page_content: "Page one content",
            created_at: "2026-04-03T10:00:00.000Z",
            updated_at: "2026-04-03T10:00:00.000Z",
          },
          {
            id: "page-2",
            lecture_id: "lecture-1",
            page_number: 2,
            page_content: "Page two content",
            created_at: "2026-04-03T10:00:00.000Z",
            updated_at: "2026-04-03T10:00:00.000Z",
          },
          {
            id: "page-3",
            lecture_id: "lecture-1",
            page_number: 3,
            page_content: "Page three content",
            created_at: "2026-04-03T10:00:00.000Z",
            updated_at: "2026-04-03T10:00:00.000Z",
          },
        ],
      });
    });
    vi.stubGlobal("fetch", fetchMock);

    render(<CourseLecturePage />);

    await waitFor(() => {
      expect(screen.getByText("Page 2 of 3")).toBeInTheDocument();
    });
    expect(screen.getByText("Page two content")).toBeInTheDocument();
    expect(screen.queryByText("Page one content")).not.toBeInTheDocument();
    expect(screen.queryByText("Page three content")).not.toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Next page" }));

    expect(replaceMock).toHaveBeenCalledWith("/courses/course-1/lectures/lecture-1?page=3");
  });
});
