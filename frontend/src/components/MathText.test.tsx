"use client";

import { render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import MathText from "@/components/MathText";

interface MathJaxTestEngine {
  startup?: {
    promise?: Promise<unknown>;
  };
  typesetPromise?: (elements?: HTMLElement[]) => Promise<void>;
}


describe("MathText", () => {
  afterEach(() => {
    delete (window as Window & { MathJax?: MathJaxTestEngine }).MathJax;
    vi.restoreAllMocks();
  });


  it("renders the source content and requests MathJax typesetting when available", async () => {
    const typesetPromise = vi.fn().mockResolvedValue(undefined);

    (window as Window & { MathJax?: MathJaxTestEngine }).MathJax = {
      startup: {
        promise: Promise.resolve(),
      },
      typesetPromise,
    };

    render(<MathText content={"$x^2 + y^2 = r^2$"} />);

    expect(screen.getByText("$x^2 + y^2 = r^2$")).toBeInTheDocument();

    await waitFor(() => {
      expect(typesetPromise).toHaveBeenCalledTimes(1);
    });
  });


  it("skips MathJax typesetting for plain text without TeX delimiters", async () => {
    const typesetPromise = vi.fn().mockResolvedValue(undefined);

    (window as Window & { MathJax?: MathJaxTestEngine }).MathJax = {
      startup: {
        promise: Promise.resolve(),
      },
      typesetPromise,
    };

    render(<MathText content="Plain text only" />);

    expect(screen.getByText("Plain text only")).toBeInTheDocument();

    await waitFor(() => {
      expect(typesetPromise).not.toHaveBeenCalled();
    });
  });
});
