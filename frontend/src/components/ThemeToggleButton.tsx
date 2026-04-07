"use client";

import { Moon, Sun } from "lucide-react";
import { useEffect, useState } from "react";
import { Button } from "@/components/ui/button";
import {
  applyThemeMode,
  persistThemeMode,
  readStoredThemeMode,
} from "@/lib/theme-mode";


export default function ThemeToggleButton() {
  const [themeMode, setThemeMode] = useState(readStoredThemeMode);

  useEffect(() => {
    applyThemeMode(themeMode);
  }, [themeMode]);

  const handleToggle = () => {
    const nextThemeMode = themeMode === "dark" ? "light" : "dark";
    setThemeMode(nextThemeMode);
    persistThemeMode(nextThemeMode);
    applyThemeMode(nextThemeMode);
  };

  const buttonLabel = themeMode === "dark" ? "Light theme" : "Black theme";

  return (
    <Button
      variant="outline"
      size="sm"
      onClick={handleToggle}
      aria-label={buttonLabel}
    >
      {themeMode === "dark" ? <Sun /> : <Moon />}
      {buttonLabel}
    </Button>
  );
}
