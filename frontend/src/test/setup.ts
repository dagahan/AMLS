import { cleanup } from "@testing-library/react";
import "@testing-library/jest-dom/vitest";
import { afterEach, vi } from "vitest";

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

class TestResizeObserver {
  observe(): void {}


  unobserve(): void {}


  disconnect(): void {}
}


function createStorageMock(): Storage {
  const values = new Map<string, string>();

  return {
    get length(): number {
      return values.size;
    },


    clear(): void {
      values.clear();
    },


    getItem(key: string): string | null {
      return values.get(key) ?? null;
    },


    key(index: number): string | null {
      return Array.from(values.keys())[index] ?? null;
    },


    removeItem(key: string): void {
      values.delete(key);
    },


    setItem(key: string, value: string): void {
      values.set(key, value);
    },
  };
}


const localStorageMock = createStorageMock();
const sessionStorageMock = createStorageMock();

Object.defineProperty(window, "matchMedia", {
  writable: true,
  value: vi.fn().mockImplementation((query: string) => ({
    matches: false,
    media: query,
    onchange: null,
    addEventListener: vi.fn(),
    removeEventListener: vi.fn(),
    addListener: vi.fn(),
    removeListener: vi.fn(),
    dispatchEvent: vi.fn(),
  })),
});

Object.defineProperty(window.HTMLElement.prototype, "scrollIntoView", {
  configurable: true,
  value: vi.fn(),
});

Object.defineProperty(window, "localStorage", {
  configurable: true,
  value: localStorageMock,
});

Object.defineProperty(window, "sessionStorage", {
  configurable: true,
  value: sessionStorageMock,
});

vi.stubGlobal("ResizeObserver", TestResizeObserver);
