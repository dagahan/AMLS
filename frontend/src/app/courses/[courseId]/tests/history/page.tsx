"use client";

import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { ArrowLeft, RefreshCw } from "lucide-react";
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
import type {
  CourseTestAttemptHistoryItemResponse,
  CourseTestHistoryResponse,
  TestAttemptReviewResponse,
} from "@/lib/api-types";
import { formatTestKindLabel, formatTestStatusLabel } from "@/lib/test-kind";
import { buildTestReviewSummary } from "@/lib/test-review-summary";
import { Button, buttonVariants } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";

const TEST_HISTORY_LOG_SCOPE = "[TestHistoryPage]";

type ScoreSummaryByAttemptId = Record<string, ReturnType<typeof buildTestReviewSummary> | null>;


function isRecoverableAuthError(error: unknown): error is AmlsRequestError {
  return error instanceof AmlsRequestError && error.recoverSession;
}


function formatAttemptTimestamp(rawValue: string | null): string {
  if (!rawValue) {
    return "Not set";
  }

  const parsedValue = new Date(rawValue);
  if (Number.isNaN(parsedValue.valueOf())) {
    return rawValue;
  }

  return parsedValue.toLocaleString();
}


export default function CourseTestHistoryPage() {
  const router = useRouter();
  const params = useParams<{ courseId: string }>();
  const rawCourseId = params.courseId;
  const courseId = Array.isArray(rawCourseId) ? rawCourseId[0] : rawCourseId;

  const [token, setToken] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [historyPayload, setHistoryPayload] = useState<CourseTestHistoryResponse | null>(null);
  const [scoreSummaryByAttemptId, setScoreSummaryByAttemptId] = useState<ScoreSummaryByAttemptId>({});
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const hasInitializedRef = useRef(false);

  const sortedAttempts = useMemo(() => {
    if (!historyPayload) {
      return [];
    }

    return [...historyPayload.attempts].sort((leftAttempt, rightAttempt) => (
      Date.parse(rightAttempt.created_at) - Date.parse(leftAttempt.created_at)
    ));
  }, [historyPayload]);
  const shouldShowBlockingOverlay = loading;

  const handleSessionRecovery = useCallback((backendMessage: string) => {
    console.warn(`${TEST_HISTORY_LOG_SCOPE} Session recovery required`, {
      backendMessage,
      courseId,
    });
    clearAuthToken();
    storeSessionNotice(getSessionExpiredMessage());
    router.replace("/");
  }, [courseId, router]);

  const loadAttemptScoreSummaries = useCallback(async (
    authToken: string,
    attempts: CourseTestAttemptHistoryItemResponse[],
  ) => {
    const summaryEntries = await Promise.all(
      attempts.map(async (attempt) => {
        try {
          const reviewPayload = await requestAmls<TestAttemptReviewResponse>(
            `/tests/${attempt.id}/review`,
            authToken,
          );

          return [
            attempt.id,
            buildTestReviewSummary(reviewPayload.items),
          ] as const;
        } catch (error: unknown) {
          if (isRecoverableAuthError(error)) {
            handleSessionRecovery(error.backendMessage);
            throw error;
          }

          return [
            attempt.id,
            null,
          ] as const;
        }
      }),
    );

    const scoreSummary: ScoreSummaryByAttemptId = {};
    for (const [attemptId, summary] of summaryEntries) {
      scoreSummary[attemptId] = summary;
    }
    setScoreSummaryByAttemptId(scoreSummary);
  }, [handleSessionRecovery]);

  const loadHistory = useCallback(async (authToken: string) => {
    try {
      setLoading(true);
      setErrorMessage(null);
      const payload = await requestAmls<CourseTestHistoryResponse>(
        `/courses/${courseId}/tests/history`,
        authToken,
      );
      setHistoryPayload(payload);
      await loadAttemptScoreSummaries(authToken, payload.attempts);
      console.log(`${TEST_HISTORY_LOG_SCOPE} Loaded test history`, {
        courseId,
        attemptCount: payload.attempts.length,
      });
    } catch (error: unknown) {
      if (isRecoverableAuthError(error)) {
        handleSessionRecovery(error.backendMessage);
        return;
      }

      const message = error instanceof Error ? error.message : "Failed to load test history";
      setErrorMessage(message);
    } finally {
      setLoading(false);
    }
  }, [courseId, handleSessionRecovery, loadAttemptScoreSummaries]);

  useEffect(() => {
    if (hasInitializedRef.current) {
      return;
    }

    hasInitializedRef.current = true;

    if (!courseId) {
      router.replace("/dashboard");
      return;
    }

    const storedToken = getStoredAuthToken();
    if (!storedToken) {
      router.replace("/");
      return;
    }

    setToken(storedToken);
    void loadHistory(storedToken);
  }, [courseId, loadHistory, router]);

  return (
    <div className="min-h-screen px-4 py-5 lg:px-6 lg:py-6">
      {shouldShowBlockingOverlay ? (
        <FullscreenLoadingOverlay
          title="Loading test history"
          message="Collecting attempt records and score summaries."
        />
      ) : null}
      <div className="mx-auto flex max-w-[1200px] flex-col gap-5">
        <header className="app-surface rounded-[1.9rem] px-5 py-4 sm:px-6">
          <div className="flex flex-col gap-4 md:flex-row md:items-center md:justify-between">
            <div>
              <p className="section-kicker">Test history</p>
              <p className="section-title text-3xl text-foreground">All attempts for this course</p>
            </div>
            <div className="flex flex-wrap gap-2">
              <ThemeToggleButton />
              <Link href={`/courses/${courseId}/workspace`} className={buttonVariants({ variant: "outline", size: "sm" })}>
                <ArrowLeft />
                Workspace
              </Link>
              <Button
                variant="outline"
                size="sm"
                onClick={() => {
                  if (token) {
                    void loadHistory(token);
                  }
                }}
                disabled={loading}
              >
                <RefreshCw />
                <InlineLoadingLabel loading={loading} idleText="Refresh" loadingText="Refreshing" />
              </Button>
            </div>
          </div>
        </header>

        {errorMessage ? (
          <div className="rounded-[1.3rem] border border-destructive/35 bg-destructive/12 px-4 py-3 text-sm text-destructive">
            {errorMessage}
          </div>
        ) : null}

        <Card>
          <CardHeader>
            <CardTitle>Attempt list</CardTitle>
          </CardHeader>
          <CardContent className="space-y-3">
            {loading ? (
              <SectionLoadingSkeleton lines={8} />
            ) : sortedAttempts.length === 0 ? (
              <p className="text-sm text-muted-foreground">No attempts yet for this course.</p>
            ) : (
              sortedAttempts.map((attempt) => {
                const scoreSummary = scoreSummaryByAttemptId[attempt.id];

                return (
                  <div
                    key={attempt.id}
                    className="rounded-[1rem] border border-border/70 bg-background/80 px-3 py-3"
                  >
                    <div className="flex flex-wrap items-center justify-between gap-2">
                      <p className="font-semibold text-foreground">
                        {formatTestKindLabel(attempt.kind)} • {formatTestStatusLabel(attempt.status)}
                      </p>
                      <Link
                        href={`/courses/${courseId}/tests/${attempt.id}/review`}
                        className={buttonVariants({ size: "sm", variant: "outline" })}
                      >
                        Open review
                      </Link>
                    </div>
                    <div className="mt-2 rounded-[0.8rem] border border-border/70 bg-background/75 px-3 py-2 text-sm text-muted-foreground">
                      Started: {formatAttemptTimestamp(attempt.started_at)} • Ended: {formatAttemptTimestamp(attempt.ended_at)}
                    </div>
                    <div className="mt-2 rounded-[0.8rem] border border-border/70 bg-background/75 px-3 py-2 text-sm text-muted-foreground">
                      {scoreSummary
                        ? `Score: ${scoreSummary.correctCount}/${scoreSummary.totalCount} (${scoreSummary.scorePercent}%)`
                        : "Score summary is not available for this attempt yet."}
                    </div>
                  </div>
                );
              })
            )}
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
