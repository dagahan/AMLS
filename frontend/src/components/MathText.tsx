"use client";

import { useEffect, useId, useRef } from "react";
import { cn } from "@/lib/utils";

interface MathJaxEngine {
  startup?: {
    promise?: Promise<unknown>;
  };
  typesetPromise?: (elements?: HTMLElement[]) => Promise<void>;
}

interface MathTextProps {
  content: string;
  className?: string;
  inline?: boolean;
}


function containsTeXDelimiters(content: string): boolean {
  return (
    /\\\([\s\S]+?\\\)/.test(content)
    || /\\\[[\s\S]+?\\\]/.test(content)
    || /\$\$[\s\S]+?\$\$/.test(content)
    || /\$[^$\n]+?\$/.test(content)
  );
}


function getMathJaxEngine(): MathJaxEngine | null {
  if (typeof window === "undefined") {
    return null;
  }

  const mathJaxWindow = window as Window & {
    MathJax?: MathJaxEngine;
  };

  return mathJaxWindow.MathJax ?? null;
}


export default function MathText({
  content,
  className,
  inline = false,
}: MathTextProps) {
  const containerId = useId();
  const elementRef = useRef<HTMLElement | null>(null);


  useEffect(() => {
    const mathJax = getMathJaxEngine();
    const element = elementRef.current;
    const shouldTypeset = containsTeXDelimiters(content);

    if (!mathJax?.typesetPromise || !element || !shouldTypeset) {
      return;
    }

    const typesetPromise = mathJax.typesetPromise;

    const typesetContent = async (): Promise<void> => {
      try {
        await mathJax.startup?.promise;
        await typesetPromise([element]);
      } catch (error: unknown) {
        console.error("[MathText] MathJax typeset failed", {
          containerId,
          content,
          error,
        });
      }
    };

    void typesetContent();
  }, [containerId, content]);


  if (inline) {
    return (
      <span
        ref={(element) => {
          elementRef.current = element;
        }}
        className={cn("math-content inline-block", className)}
        suppressHydrationWarning
      >
        {content}
      </span>
    );
  }

  return (
    <div
      ref={(element) => {
        elementRef.current = element;
      }}
      className={cn("math-content", className)}
      suppressHydrationWarning
    >
      {content}
    </div>
  );
}
