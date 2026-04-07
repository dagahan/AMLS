"use client";

import { render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import DashboardPage from "@/app/dashboard/page";

const replaceMock = vi.fn();

vi.mock("next/navigation", () => ({
  useRouter: () => ({
    replace: replaceMock,
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


describe("Dashboard page", () => {
  beforeEach(() => {
    window.localStorage.clear();
    window.sessionStorage.clear();
    replaceMock.mockReset();
    vi.spyOn(console, "warn").mockImplementation(() => undefined);
    vi.spyOn(console, "log").mockImplementation(() => undefined);
  });


  it("keeps token for non-student role and skips active courses request", async () => {
    window.localStorage.setItem("auth_token", "admin-token");

    const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
      const path = String(input);

      if (path === "/api/amls/auth/me") {
        return createJsonResponse({
          user: {
            id: "admin-1",
            email: "admin@example.org",
            first_name: "Admin",
            last_name: "User",
            avatar_url: null,
            role: "admin",
            is_active: true,
          },
        });
      }

      if (path === "/api/amls/courses") {
        return createJsonResponse([
          {
            id: "course-1",
            author_id: "author-1",
            current_graph_version_id: "graph-version-1",
            title: "Profile Mathematics (Grades 10-11)",
            description: "Main diploma demo course",
            created_at: "2026-04-02T10:00:00.000Z",
            updated_at: "2026-04-02T10:00:00.000Z",
          },
        ]);
      }

      if (path === "/api/amls/courses/active") {
        return createJsonResponse({ detail: "Student role required" }, 403);
      }

      return createJsonResponse({});
    });
    vi.stubGlobal("fetch", fetchMock);

    render(<DashboardPage />);

    expect(await screen.findByText("Enrolled courses")).toBeInTheDocument();
    expect(screen.getByText("Course catalog")).toBeInTheDocument();
    expect(screen.getByText("No enrolled courses yet.")).toBeInTheDocument();

    await waitFor(() => {
      expect(window.localStorage.getItem("auth_token")).toBe("admin-token");
      expect(replaceMock).not.toHaveBeenCalledWith("/");
    });
  });
});
