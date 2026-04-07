"use client";

import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import Home from "@/app/page";

const replaceMock = vi.fn();
const pushMock = vi.fn();

vi.mock("next/navigation", () => ({
  useRouter: () => ({
    replace: replaceMock,
    push: pushMock,
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


describe("Home auth page", () => {
  beforeEach(() => {
    window.localStorage.clear();
    window.sessionStorage.clear();
    replaceMock.mockReset();
    pushMock.mockReset();
    vi.spyOn(console, "warn").mockImplementation(() => undefined);
  });


  it("redirects to dashboard when token is already stored", async () => {
    window.localStorage.setItem("auth_token", "student-token");

    render(<Home />);

    await waitFor(() => {
      expect(replaceMock).toHaveBeenCalledWith("/dashboard");
    });
  });


  it("shows session notice and allows successful login", async () => {
    const user = userEvent.setup();
    window.sessionStorage.setItem("amls_session_notice", "Session expired. Please sign in again.");

    vi.stubGlobal(
      "fetch",
      vi.fn(async () => createJsonResponse({ access_token: "token-1", refresh_token: "token-2" }, 201)),
    );

    render(<Home />);

    expect(await screen.findByText("Session expired. Please sign in again.")).toBeInTheDocument();

    await user.type(screen.getByLabelText("Email"), "student@example.org");
    await user.type(screen.getByLabelText("Password"), "Student123!");
    await user.click(screen.getByRole("button", { name: "Sign in" }));

    await waitFor(() => {
      expect(window.localStorage.getItem("auth_token")).toBe("token-1");
      expect(pushMock).toHaveBeenCalledWith("/dashboard");
    });
  });
});
