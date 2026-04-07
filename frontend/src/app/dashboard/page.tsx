"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useCallback, useEffect, useMemo, useState } from "react";
import { BookOpenCheck, LogOut, RefreshCw, UserRound } from "lucide-react";
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
import type { AuthUserResponse, CourseResponse, UserResponse } from "@/lib/api-types";
import { Button, buttonVariants } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";

const DASHBOARD_LOG_SCOPE = "[Dashboard]";


function isRecoverableAuthError(error: unknown): error is AmlsRequestError {
  return error instanceof AmlsRequestError && error.recoverSession;
}


export default function DashboardPage() {
  const router = useRouter();
  const [token, setToken] = useState<string | null>(null);
  const [currentUser, setCurrentUser] = useState<UserResponse | null>(null);
  const [allCourses, setAllCourses] = useState<CourseResponse[]>([]);
  const [activeCourses, setActiveCourses] = useState<CourseResponse[]>([]);
  const [loading, setLoading] = useState(true);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [pendingCourseActionId, setPendingCourseActionId] = useState<string | null>(null);

  const activeCourseIds = useMemo(
    () => new Set(activeCourses.map((course) => course.id)),
    [activeCourses],
  );
  const availableCourses = useMemo(
    () => allCourses.filter((course) => !activeCourseIds.has(course.id)),
    [activeCourseIds, allCourses],
  );
  const shouldShowBlockingOverlay = loading || pendingCourseActionId !== null;
  const blockingOverlayTitle = pendingCourseActionId !== null
    ? "Updating enrollment..."
    : "Loading dashboard";
  const blockingOverlayMessage = pendingCourseActionId !== null
    ? "Saving your course changes and refreshing your dashboard."
    : "Preparing your profile and course data.";

  const handleSessionRecovery = useCallback((backendMessage: string) => {
    console.warn(`${DASHBOARD_LOG_SCOPE} Session recovery required`, {
      backendMessage,
    });
    clearAuthToken();
    storeSessionNotice(getSessionExpiredMessage());
    router.replace("/");
  }, [router]);

  const loadDashboardData = useCallback(async (authToken: string) => {
    try {
      setLoading(true);
      setErrorMessage(null);

      const authMeResponse = await requestAmls<AuthUserResponse>("/auth/me", authToken);
      const coursesResponse = await requestAmls<CourseResponse[]>("/courses", authToken);
      let activeResponse: CourseResponse[] = [];

      if (authMeResponse.user.role === "student") {
        activeResponse = await requestAmls<CourseResponse[]>("/courses/active", authToken);
      } else {
        console.log(`${DASHBOARD_LOG_SCOPE} Skipped active courses request for non-student role`, {
          role: authMeResponse.user.role,
        });
      }

      setCurrentUser(authMeResponse.user);
      setAllCourses(coursesResponse);
      setActiveCourses(activeResponse);

      console.log(`${DASHBOARD_LOG_SCOPE} Dashboard loaded`, {
        allCourseCount: coursesResponse.length,
        email: authMeResponse.user.email,
        activeCourseCount: activeResponse.length,
      });
    } catch (error: unknown) {
      if (isRecoverableAuthError(error)) {
        handleSessionRecovery(error.backendMessage);
        return;
      }

      const message = error instanceof Error ? error.message : "Failed to load dashboard";
      console.warn(`${DASHBOARD_LOG_SCOPE} Dashboard load failed`, {
        message,
      });
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
    void loadDashboardData(storedToken);
  }, [loadDashboardData, router]);

  const handleEnroll = useCallback(async (courseId: string) => {
    if (!token) {
      return;
    }

    try {
      setPendingCourseActionId(`enroll-${courseId}`);
      await requestAmls(`/courses/${courseId}/enroll`, token, {
        method: "POST",
      });
      await loadDashboardData(token);
    } catch (error: unknown) {
      if (isRecoverableAuthError(error)) {
        handleSessionRecovery(error.backendMessage);
        return;
      }

      const message = error instanceof Error ? error.message : "Failed to enroll";
      setErrorMessage(message);
    } finally {
      setPendingCourseActionId(null);
    }
  }, [handleSessionRecovery, loadDashboardData, token]);

  const handleUnenroll = useCallback(async (courseId: string) => {
    if (!token) {
      return;
    }

    try {
      setPendingCourseActionId(`unenroll-${courseId}`);
      await requestAmls(`/courses/${courseId}/unenroll`, token, {
        method: "POST",
      });
      await loadDashboardData(token);
    } catch (error: unknown) {
      if (isRecoverableAuthError(error)) {
        handleSessionRecovery(error.backendMessage);
        return;
      }

      const message = error instanceof Error ? error.message : "Failed to unenroll";
      setErrorMessage(message);
    } finally {
      setPendingCourseActionId(null);
    }
  }, [handleSessionRecovery, loadDashboardData, token]);

  const handleLogout = useCallback(() => {
    clearAuthToken();
    router.replace("/");
  }, [router]);

  return (
    <div className="min-h-screen px-4 py-5 lg:px-6 lg:py-6">
      {shouldShowBlockingOverlay ? (
        <FullscreenLoadingOverlay
          title={blockingOverlayTitle}
          message={blockingOverlayMessage}
        />
      ) : null}
      <div className="mx-auto flex max-w-[1600px] flex-col gap-5">
        <header className="app-surface rounded-[1.9rem] px-5 py-4 sm:px-6">
          <div className="flex flex-col gap-4 md:flex-row md:items-center md:justify-between">
            <div>
              <p className="brand-mark text-[2.15rem] leading-none">AMLS</p>
              <p className="brand-caption mt-1">Student dashboard</p>
              <p className="mt-2 text-sm text-muted-foreground">
                {currentUser ? `${currentUser.first_name} ${currentUser.last_name}` : "Loading profile..."}
              </p>
            </div>
            <div className="flex flex-wrap items-center gap-2">
              <ThemeToggleButton />
              <Button variant="outline" size="sm" onClick={() => {
                if (token) {
                  void loadDashboardData(token);
                }
              }} disabled={loading}>
                <RefreshCw />
                <InlineLoadingLabel loading={loading} idleText="Refresh" loadingText="Refreshing" />
              </Button>
              <Link href="/profile" className={buttonVariants({ variant: "outline", size: "sm" })}>
                <UserRound />
                Profile
              </Link>
              <Button variant="outline" size="sm" onClick={handleLogout}>
                <LogOut />
                Logout
              </Button>
            </div>
          </div>
        </header>

        {errorMessage ? (
          <div className="rounded-[1.3rem] border border-destructive/35 bg-destructive/12 px-4 py-3 text-sm text-destructive">
            {errorMessage}
          </div>
        ) : null}

        <div className="grid gap-5 lg:grid-cols-2">
          <Card>
            <CardHeader>
              <p className="section-kicker">My Courses</p>
              <CardTitle>Enrolled courses</CardTitle>
            </CardHeader>
            <CardContent>
              {loading ? (
                <SectionLoadingSkeleton lines={4} />
              ) : activeCourses.length === 0 ? (
                <p className="text-sm text-muted-foreground">No enrolled courses yet.</p>
              ) : (
                <div className="space-y-3">
                  {activeCourses.map((course) => (
                    <div
                      key={course.id}
                      className="rounded-[1rem] border border-border/70 bg-background/78 px-3 py-3"
                    >
                      <p className="font-semibold text-foreground">{course.title}</p>
                      <p className="mt-1 text-sm text-muted-foreground">{course.description ?? "No description."}</p>
                      <div className="mt-3 flex flex-wrap gap-2">
                        <Link href={`/courses/${course.id}/workspace`} className={buttonVariants({ size: "sm" })}>
                          <BookOpenCheck />
                          Open workspace
                        </Link>
                        <Button
                          size="sm"
                          variant="outline"
                          onClick={() => {
                            void handleUnenroll(course.id);
                          }}
                          disabled={pendingCourseActionId === `unenroll-${course.id}`}
                        >
                          <InlineLoadingLabel
                            loading={pendingCourseActionId === `unenroll-${course.id}`}
                            idleText="Unenroll"
                            loadingText="Unenrolling"
                          />
                        </Button>
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <p className="section-kicker">Available Courses</p>
              <CardTitle>Course catalog</CardTitle>
            </CardHeader>
            <CardContent>
              {loading ? (
                <SectionLoadingSkeleton lines={4} />
              ) : availableCourses.length === 0 ? (
                <p className="text-sm text-muted-foreground">No additional courses available.</p>
              ) : (
                <div className="space-y-3">
                  {availableCourses.map((course) => (
                    <div
                      key={course.id}
                      className="rounded-[1rem] border border-border/70 bg-background/78 px-3 py-3"
                    >
                      <p className="font-semibold text-foreground">{course.title}</p>
                      <p className="mt-1 text-sm text-muted-foreground">{course.description ?? "No description."}</p>
                      <div className="mt-3">
                        <Button
                          size="sm"
                          variant="outline"
                          onClick={() => {
                            void handleEnroll(course.id);
                          }}
                          disabled={pendingCourseActionId === `enroll-${course.id}`}
                        >
                          <InlineLoadingLabel
                            loading={pendingCourseActionId === `enroll-${course.id}`}
                            idleText="Enroll"
                            loadingText="Enrolling"
                          />
                        </Button>
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </CardContent>
          </Card>
        </div>
      </div>
    </div>
  );
}
