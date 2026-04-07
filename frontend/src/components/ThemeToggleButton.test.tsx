"use client";

import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it } from "vitest";
import ThemeToggleButton from "@/components/ThemeToggleButton";


describe("Theme toggle button", () => {
  beforeEach(() => {
    window.localStorage.clear();
    document.documentElement.classList.remove("dark", "light");
    document.documentElement.classList.add("dark");
  });


  it("uses black mode by default and persists toggle selection", async () => {
    const user = userEvent.setup();

    render(<ThemeToggleButton />);
    expect(await screen.findByRole("button", { name: "Light theme" })).toBeInTheDocument();
    expect(document.documentElement.classList.contains("dark")).toBe(true);

    await user.click(screen.getByRole("button", { name: "Light theme" }));

    expect(screen.getByRole("button", { name: "Black theme" })).toBeInTheDocument();
    expect(window.localStorage.getItem("amls_theme_mode")).toBe("light");
    expect(document.documentElement.classList.contains("light")).toBe(true);
  });
});
