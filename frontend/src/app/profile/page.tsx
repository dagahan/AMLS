"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { FormEvent, useCallback, useEffect, useState } from "react";
import { ArrowLeft, Save } from "lucide-react";
import { FullscreenLoadingOverlay, InlineLoadingLabel, SectionLoadingSkeleton } from "@/components/AppLoading";
import ThemeToggleButton from "@/components/ThemeToggleButton";
import {
  AmlsRequestError,
  clearAuthToken,
  getSessionExpiredMessage,
  getStoredAuthToken,
  requestAmls,
  storeSessionNotice,
} from "@/lib/amls-client";
import type { AuthUserResponse, UserResponse } from "@/lib/api-types";
import { Button, buttonVariants } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";

const PROFILE_LOG_SCOPE = "[Profile]";


function isRecoverableAuthError(error: unknown): error is AmlsRequestError {
  return error instanceof AmlsRequestError && error.recoverSession;
}


export default function ProfilePage() {
  const router = useRouter();
  const [token, setToken] = useState<string | null>(null);
  const [currentUser, setCurrentUser] = useState<UserResponse | null>(null);
  const [firstName, setFirstName] = useState("");
  const [lastName, setLastName] = useState("");
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const shouldShowBlockingOverlay = loading || saving;
  const blockingOverlayTitle = saving ? "Saving profile..." : "Loading profile";
  const blockingOverlayMessage = saving
    ? "Applying your profile changes."
    : "Preparing your profile data.";

  const handleSessionRecovery = useCallback((backendMessage: string) => {
    console.warn(`${PROFILE_LOG_SCOPE} Session recovery required`, {
      backendMessage,
    });
    clearAuthToken();
    storeSessionNotice(getSessionExpiredMessage());
    router.replace("/");
  }, [router]);

  const loadProfile = useCallback(async (authToken: string) => {
    try {
      setLoading(true);
      setErrorMessage(null);
      const response = await requestAmls<AuthUserResponse>("/auth/me", authToken);
      setCurrentUser(response.user);
      setFirstName(response.user.first_name);
      setLastName(response.user.last_name);
    } catch (error: unknown) {
      if (isRecoverableAuthError(error)) {
        handleSessionRecovery(error.backendMessage);
        return;
      }

      const message = error instanceof Error ? error.message : "Failed to load profile";
      setErrorMessage(message);
    } finally {
      setLoading(false);
    }
  }, [handleSessionRecovery]);

  useEffect(() => {
    const storedToken = getStoredAuthToken();
    if (!storedToken) {
      router.replace("/");
      return;
    }

    setToken(storedToken);
    void loadProfile(storedToken);
  }, [loadProfile, router]);

  const handleSubmit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!token) {
      return;
    }

    try {
      setSaving(true);
      setErrorMessage(null);
      setNotice(null);

      const updatedUser = await requestAmls<UserResponse>("/users/me", token, {
        method: "PATCH",
        body: JSON.stringify({
          first_name: firstName,
          last_name: lastName,
        }),
      });
      setCurrentUser(updatedUser);
      setNotice("Profile updated.");
    } catch (error: unknown) {
      if (isRecoverableAuthError(error)) {
        handleSessionRecovery(error.backendMessage);
        return;
      }

      const message = error instanceof Error ? error.message : "Failed to update profile";
      setErrorMessage(message);
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="min-h-screen px-4 py-5 lg:px-6 lg:py-6">
      {shouldShowBlockingOverlay ? (
        <FullscreenLoadingOverlay
          title={blockingOverlayTitle}
          message={blockingOverlayMessage}
        />
      ) : null}
      <div className="mx-auto flex max-w-[980px] flex-col gap-5">
        <header className="app-surface rounded-[1.9rem] px-5 py-4 sm:px-6">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div>
              <p className="section-kicker">Profile</p>
              <p className="section-title text-2xl text-foreground">Student profile</p>
            </div>
            <div className="flex flex-wrap items-center gap-2">
              <ThemeToggleButton />
              <Link href="/dashboard" className={buttonVariants({ variant: "outline", size: "sm" })}>
                <ArrowLeft />
                Back to dashboard
              </Link>
            </div>
          </div>
        </header>

        <Card>
          <CardHeader>
            <CardTitle>{currentUser ? `${currentUser.first_name} ${currentUser.last_name}` : "Profile"}</CardTitle>
          </CardHeader>
          <CardContent>
            {errorMessage ? (
              <div className="mb-4 rounded-[1rem] border border-destructive/35 bg-destructive/12 px-3 py-2 text-sm text-destructive">
                {errorMessage}
              </div>
            ) : null}
            {notice ? (
              <div className="mb-4 rounded-[1rem] border border-primary/30 bg-primary/12 px-3 py-2 text-sm text-primary">
                {notice}
              </div>
            ) : null}

            {loading ? (
              <SectionLoadingSkeleton lines={5} />
            ) : (
              <form className="space-y-4" onSubmit={handleSubmit}>
                <div className="space-y-2">
                  <Label htmlFor="profile-first-name">First name</Label>
                  <Input
                    id="profile-first-name"
                    value={firstName}
                    onChange={(event) => setFirstName(event.target.value)}
                    required
                  />
                </div>
                <div className="space-y-2">
                  <Label htmlFor="profile-last-name">Last name</Label>
                  <Input
                    id="profile-last-name"
                    value={lastName}
                    onChange={(event) => setLastName(event.target.value)}
                    required
                  />
                </div>
                <div className="rounded-[1rem] border border-border/70 bg-background/76 px-3 py-2 text-sm text-muted-foreground">
                  {currentUser?.email ?? "Email not loaded"}
                </div>
                <Button type="submit" disabled={saving}>
                  <Save />
                  <InlineLoadingLabel idleText="Save profile" loadingText="Saving profile" loading={saving} />
                </Button>
              </form>
            )}
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
