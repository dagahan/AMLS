"use client";

import { FormEvent, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import {
  getStoredAuthToken,
  readAndClearSessionNotice,
  storeAuthToken,
} from "@/lib/amls-client";
import type { TokenPairResponse } from "@/lib/api-types";
import { FullscreenLoadingOverlay, InlineLoadingLabel } from "@/components/AppLoading";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";

type AuthMode = "login" | "register";

const HOME_LOG_SCOPE = "[Home]";


function getResponseErrorMessage(payload: unknown, fallbackMessage: string): string {
  if (typeof payload !== "object" || payload === null) {
    return fallbackMessage;
  }

  const responsePayload = payload as {
    detail?: unknown;
    error?: unknown;
  };

  if (typeof responsePayload.detail === "string" && responsePayload.detail.trim() !== "") {
    return responsePayload.detail;
  }

  if (typeof responsePayload.error === "string" && responsePayload.error.trim() !== "") {
    return responsePayload.error;
  }

  return fallbackMessage;
}


export default function Home() {
  const router = useRouter();
  const [authMode, setAuthMode] = useState<AuthMode>("login");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [firstName, setFirstName] = useState("");
  const [lastName, setLastName] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [authError, setAuthError] = useState<string | null>(null);
  const [authNotice, setAuthNotice] = useState<string | null>(null);
  const [bootstrapped, setBootstrapped] = useState(false);

  useEffect(() => {
    const savedToken = getStoredAuthToken();
    if (savedToken) {
      router.replace("/dashboard");
      return;
    }

    const sessionNotice = readAndClearSessionNotice();
    if (sessionNotice) {
      setAuthNotice(sessionNotice);
    }

    setBootstrapped(true);
  }, [router]);


  const handleLogin = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();

    try {
      setSubmitting(true);
      setAuthError(null);
      setAuthNotice(null);

      const response = await fetch("/api/auth", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          email,
          password,
        }),
      });
      const payload = await response.json().catch(() => null);

      if (!response.ok) {
        throw new Error(getResponseErrorMessage(payload, "Invalid credentials"));
      }

      const tokenPair = payload as TokenPairResponse;
      storeAuthToken(tokenPair.access_token);
      setPassword("");
      router.push("/dashboard");
    } catch (error: unknown) {
      const message = error instanceof Error ? error.message : "Login failed";
      console.warn(`${HOME_LOG_SCOPE} Login failed`, {
        email,
        message,
      });
      setAuthError(message);
    } finally {
      setSubmitting(false);
    }
  };


  const handleRegister = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();

    try {
      setSubmitting(true);
      setAuthError(null);
      setAuthNotice(null);

      const response = await fetch("/api/auth/register", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          email,
          password,
          first_name: firstName,
          last_name: lastName,
        }),
      });
      const payload = await response.json().catch(() => null);

      if (!response.ok) {
        throw new Error(getResponseErrorMessage(payload, "Registration failed"));
      }

      setAuthMode("login");
      setPassword("");
      setAuthNotice("Registration completed. Please sign in.");
    } catch (error: unknown) {
      const message = error instanceof Error ? error.message : "Registration failed";
      console.warn(`${HOME_LOG_SCOPE} Registration failed`, {
        email,
        message,
      });
      setAuthError(message);
    } finally {
      setSubmitting(false);
    }
  };

  if (!bootstrapped) {
    return (
      <FullscreenLoadingOverlay
        title="Preparing sign in"
        message="Checking your current session."
      />
    );
  }

  return (
    <div className="min-h-screen px-4 py-6 lg:px-6">
      {submitting ? (
        <FullscreenLoadingOverlay
          title={authMode === "login" ? "Signing in..." : "Creating profile..."}
          message="Applying your authentication request."
        />
      ) : null}
      <div className="mx-auto flex max-w-[980px] flex-col gap-6">
        <header className="app-surface rounded-[1.8rem] px-5 py-5 sm:px-6">
          <p className="brand-mark text-[2.6rem] leading-none">AMLS</p>
          <p className="brand-caption mt-2">Adaptive Math Learning System</p>
          <p className="mt-4 max-w-2xl text-sm text-muted-foreground">
            Sign in to open your dashboard and continue working in the course workspace.
          </p>
        </header>

        <Card className="mx-auto w-full max-w-[520px]">
          <CardHeader>
            <p className="section-kicker">{authMode === "login" ? "Sign In" : "Register"}</p>
            <CardTitle>{authMode === "login" ? "Open your dashboard" : "Create student profile"}</CardTitle>
          </CardHeader>
          <CardContent>
            {authNotice ? (
              <div className="mb-4 rounded-[1rem] border border-primary/30 bg-primary/12 px-3 py-2 text-sm text-primary">
                {authNotice}
              </div>
            ) : null}
            {authError ? (
              <div className="mb-4 rounded-[1rem] border border-destructive/35 bg-destructive/12 px-3 py-2 text-sm text-destructive">
                {authError}
              </div>
            ) : null}

            {authMode === "login" ? (
              <form className="space-y-4" onSubmit={handleLogin}>
                <div className="space-y-2">
                  <Label htmlFor="login-email">Email</Label>
                  <Input
                    id="login-email"
                    autoComplete="email"
                    type="email"
                    value={email}
                    onChange={(event) => setEmail(event.target.value)}
                    required
                  />
                </div>
                <div className="space-y-2">
                  <Label htmlFor="login-password">Password</Label>
                  <Input
                    id="login-password"
                    autoComplete="current-password"
                    type="password"
                    value={password}
                    onChange={(event) => setPassword(event.target.value)}
                    required
                  />
                </div>
                <Button className="w-full" type="submit" disabled={submitting}>
                  <InlineLoadingLabel
                    idleText="Sign in"
                    loadingText="Signing in"
                    loading={submitting}
                  />
                </Button>
                <Button
                  className="w-full"
                  variant="ghost"
                  type="button"
                  onClick={() => {
                    setAuthMode("register");
                    setAuthError(null);
                    setAuthNotice(null);
                  }}
                >
                  Need a profile? Register
                </Button>
              </form>
            ) : (
              <form className="space-y-4" onSubmit={handleRegister}>
                <div className="space-y-2">
                  <Label htmlFor="register-first-name">First name</Label>
                  <Input
                    id="register-first-name"
                    autoComplete="given-name"
                    value={firstName}
                    onChange={(event) => setFirstName(event.target.value)}
                    required
                  />
                </div>
                <div className="space-y-2">
                  <Label htmlFor="register-last-name">Last name</Label>
                  <Input
                    id="register-last-name"
                    autoComplete="family-name"
                    value={lastName}
                    onChange={(event) => setLastName(event.target.value)}
                    required
                  />
                </div>
                <div className="space-y-2">
                  <Label htmlFor="register-email">Email</Label>
                  <Input
                    id="register-email"
                    autoComplete="email"
                    type="email"
                    value={email}
                    onChange={(event) => setEmail(event.target.value)}
                    required
                  />
                </div>
                <div className="space-y-2">
                  <Label htmlFor="register-password">Password</Label>
                  <Input
                    id="register-password"
                    autoComplete="new-password"
                    type="password"
                    value={password}
                    onChange={(event) => setPassword(event.target.value)}
                    required
                  />
                </div>
                <Button className="w-full" type="submit" disabled={submitting}>
                  <InlineLoadingLabel
                    idleText="Create profile"
                    loadingText="Creating profile"
                    loading={submitting}
                  />
                </Button>
                <Button
                  className="w-full"
                  variant="ghost"
                  type="button"
                  onClick={() => {
                    setAuthMode("login");
                    setAuthError(null);
                    setAuthNotice(null);
                  }}
                >
                  Already registered? Sign in
                </Button>
              </form>
            )}
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
