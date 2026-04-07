"use client";

import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { ArrowLeft, PauseCircle, Play, RefreshCw, Send, Sparkles } from "lucide-react";
import { FullscreenLoadingOverlay, InlineLoadingLabel, SectionLoadingSkeleton } from "@/components/AppLoading";
import MathText from "@/components/MathText";
import TestAttemptReviewPanel from "@/components/TestAttemptReviewPanel";
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
  GraphAssessmentResponse,
  ProblemResponse,
  TestAnswerResponse,
  TestAttemptReviewResponse,
  TestAttemptResponse,
  TestCurrentProblemResponse,
  TestRevealSolutionResponse,
} from "@/lib/api-types";
import { computeLiveElapsedSeconds, formatElapsedSeconds } from "@/lib/test-timer";
import { formatTestKindLabel } from "@/lib/test-kind";
import { Button, buttonVariants } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";

const TEST_PAGE_LOG_SCOPE = "[TestPage]";


function isRecoverableAuthError(error: unknown): error is AmlsRequestError {
  return error instanceof AmlsRequestError && error.recoverSession;
}


function isTerminalAttemptStatus(status: TestAttemptResponse["status"]): boolean {
  return status === "completed" || status === "cancelled";
}


function findAssessmentForAttempt(
  assessments: GraphAssessmentResponse[],
  attemptId: string,
): GraphAssessmentResponse | null {
  const matchingAssessment = assessments.find(
    (assessment) => assessment.source_test_attempt_id === attemptId,
  );

  return matchingAssessment ?? null;
}


export default function CourseTestPage() {
  const router = useRouter();
  const params = useParams<{ courseId: string; attemptId: string }>();
  const rawCourseId = params.courseId;
  const rawAttemptId = params.attemptId;
  const courseId = Array.isArray(rawCourseId) ? rawCourseId[0] : rawCourseId;
  const attemptId = Array.isArray(rawAttemptId) ? rawAttemptId[0] : rawAttemptId;

  const [token, setToken] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [submitting, setSubmitting] = useState(false);
  const [loadingReviewData, setLoadingReviewData] = useState(false);
  const [calculatingScore, setCalculatingScore] = useState(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [testAttempt, setTestAttempt] = useState<TestAttemptResponse | null>(null);
  const [currentProblem, setCurrentProblem] = useState<ProblemResponse | null>(null);
  const [selectedAnswerId, setSelectedAnswerId] = useState<string | null>(null);
  const [revealedSolution, setRevealedSolution] = useState<TestRevealSolutionResponse["revealed_solution"] | null>(null);
  const [attemptReview, setAttemptReview] = useState<TestAttemptReviewResponse | null>(null);
  const [linkedAssessment, setLinkedAssessment] = useState<GraphAssessmentResponse | null>(null);
  const [elapsedSeconds, setElapsedSeconds] = useState(0);
  const hasInitializedRef = useRef(false);

  const isPaused = testAttempt?.status === "paused";
  const isTerminal = testAttempt ? isTerminalAttemptStatus(testAttempt.status) : false;
  const mismatchedAttempt = testAttempt !== null && testAttempt.id !== attemptId;
  const shouldShowTestOperationOverlay = (loading || submitting) && !calculatingScore;
  const testOperationOverlayTitle = submitting ? "Updating test..." : "Loading test";
  const testOperationOverlayMessage = submitting
    ? "Saving your action and refreshing the current test state."
    : "Preparing your current attempt.";

  const handleSessionRecovery = useCallback((backendMessage: string) => {
    console.warn(`${TEST_PAGE_LOG_SCOPE} Session recovery required`, {
      backendMessage,
      attemptId,
      courseId,
    });
    clearAuthToken();
    storeSessionNotice(getSessionExpiredMessage());
    router.replace("/");
  }, [attemptId, courseId, router]);

  const loadAttemptReviewData = useCallback(async (
    authToken: string,
    targetAttemptId: string,
    showCalculatingOverlay: boolean,
  ) => {
    try {
      if (showCalculatingOverlay) {
        setCalculatingScore(true);
      }
      setLoadingReviewData(true);
      const [reviewPayload, assessments] = await Promise.all([
        requestAmls<TestAttemptReviewResponse>(
          `/tests/${targetAttemptId}/review`,
          authToken,
        ),
        requestAmls<GraphAssessmentResponse[]>(
          `/courses/${courseId}/graph-assessments`,
          authToken,
        ),
      ]);
      setAttemptReview(reviewPayload);
      setLinkedAssessment(findAssessmentForAttempt(assessments, targetAttemptId));
      console.log(`${TEST_PAGE_LOG_SCOPE} Loaded review payload`, {
        attemptId: targetAttemptId,
        itemCount: reviewPayload.items.length,
      });
    } catch (error: unknown) {
      if (isRecoverableAuthError(error)) {
        handleSessionRecovery(error.backendMessage);
        return;
      }

      const message = error instanceof Error ? error.message : "Failed to load test review";
      setErrorMessage(message);
    } finally {
      setLoadingReviewData(false);
      if (showCalculatingOverlay) {
        setCalculatingScore(false);
      }
    }
  }, [courseId, handleSessionRecovery]);

  const loadCurrentTest = useCallback(async (authToken: string) => {
    try {
      setLoading(true);
      setErrorMessage(null);

      const payload = await requestAmls<TestCurrentProblemResponse>(
        `/courses/${courseId}/tests/current`,
        authToken,
      );
      setTestAttempt(payload.test_attempt);
      setCurrentProblem(payload.problem);
      setSelectedAnswerId(null);
      setElapsedSeconds(payload.test_attempt.elapsed_solve_seconds);

      if (isTerminalAttemptStatus(payload.test_attempt.status)) {
        await loadAttemptReviewData(authToken, payload.test_attempt.id, false);
      } else {
        setAttemptReview(null);
        setLinkedAssessment(null);
      }

      console.log(`${TEST_PAGE_LOG_SCOPE} Loaded current test`, {
        attemptId: payload.test_attempt.id,
        status: payload.test_attempt.status,
        hasProblem: payload.problem !== null,
      });
    } catch (error: unknown) {
      if (isRecoverableAuthError(error)) {
        handleSessionRecovery(error.backendMessage);
        return;
      }

      const message = error instanceof Error ? error.message : "Failed to load current test";
      setErrorMessage(message);
    } finally {
      setLoading(false);
    }
  }, [courseId, handleSessionRecovery, loadAttemptReviewData]);

  useEffect(() => {
    if (hasInitializedRef.current) {
      return;
    }

    hasInitializedRef.current = true;

    if (!courseId || !attemptId) {
      router.replace("/dashboard");
      return;
    }

    const storedToken = getStoredAuthToken();
    if (!storedToken) {
      router.replace("/");
      return;
    }

    setToken(storedToken);
    void loadCurrentTest(storedToken);
  }, [attemptId, courseId, loadCurrentTest, router]);

  useEffect(() => {
    if (!testAttempt) {
      return;
    }

    setElapsedSeconds(testAttempt.elapsed_solve_seconds);
  }, [testAttempt]);

  useEffect(() => {
    if (!testAttempt || testAttempt.status !== "active" || submitting || calculatingScore) {
      return;
    }

    const intervalId = window.setInterval(() => {
      setElapsedSeconds(computeLiveElapsedSeconds(testAttempt, Date.now()));
    }, 1000);

    return () => {
      window.clearInterval(intervalId);
    };
  }, [calculatingScore, submitting, testAttempt]);

  const handleSubmitAnswer = useCallback(async () => {
    if (!token || !testAttempt || !currentProblem || !selectedAnswerId || submitting) {
      return;
    }

    try {
      setSubmitting(true);
      setErrorMessage(null);
      const payload = await requestAmls<TestAnswerResponse>(
        `/tests/${testAttempt.id}/answers`,
        token,
        {
          method: "POST",
          body: JSON.stringify({
            problem_id: currentProblem.id,
            answer_option_id: selectedAnswerId,
          }),
        },
      );
      setTestAttempt(payload.test_attempt);
      setCurrentProblem(payload.next_problem);
      setSelectedAnswerId(null);
      setRevealedSolution(null);
      if (isTerminalAttemptStatus(payload.test_attempt.status)) {
        await loadAttemptReviewData(token, payload.test_attempt.id, true);
      }
    } catch (error: unknown) {
      if (isRecoverableAuthError(error)) {
        handleSessionRecovery(error.backendMessage);
        return;
      }

      const message = error instanceof Error ? error.message : "Failed to submit answer";
      setErrorMessage(message);
    } finally {
      setSubmitting(false);
    }
  }, [currentProblem, handleSessionRecovery, loadAttemptReviewData, selectedAnswerId, submitting, testAttempt, token]);

  const handleRevealSolution = useCallback(async () => {
    if (!token || !testAttempt || submitting) {
      return;
    }

    try {
      setSubmitting(true);
      setErrorMessage(null);
      const payload = await requestAmls<TestRevealSolutionResponse>(
        `/tests/${testAttempt.id}/reveal-solution`,
        token,
        {
          method: "POST",
        },
      );
      setTestAttempt(payload.test_attempt);
      setCurrentProblem(payload.next_problem);
      setSelectedAnswerId(null);
      setRevealedSolution(payload.revealed_solution);
      if (isTerminalAttemptStatus(payload.test_attempt.status)) {
        await loadAttemptReviewData(token, payload.test_attempt.id, true);
      }
    } catch (error: unknown) {
      if (isRecoverableAuthError(error)) {
        handleSessionRecovery(error.backendMessage);
        return;
      }

      const message = error instanceof Error ? error.message : "Failed to reveal solution";
      setErrorMessage(message);
    } finally {
      setSubmitting(false);
    }
  }, [handleSessionRecovery, loadAttemptReviewData, submitting, testAttempt, token]);

  const handlePauseTest = useCallback(async () => {
    if (!token || !testAttempt || submitting || testAttempt.status !== "active") {
      return;
    }

    try {
      setSubmitting(true);
      setErrorMessage(null);
      const payload = await requestAmls<TestAttemptResponse>(
        `/tests/${testAttempt.id}/pause`,
        token,
        {
          method: "POST",
        },
      );
      setTestAttempt(payload);
      setCurrentProblem(null);
      setSelectedAnswerId(null);
    } catch (error: unknown) {
      if (isRecoverableAuthError(error)) {
        handleSessionRecovery(error.backendMessage);
        return;
      }

      const message = error instanceof Error ? error.message : "Failed to pause test";
      setErrorMessage(message);
    } finally {
      setSubmitting(false);
    }
  }, [handleSessionRecovery, submitting, testAttempt, token]);

  const handleResumeTest = useCallback(async () => {
    if (!token || !testAttempt || submitting || testAttempt.status !== "paused") {
      return;
    }

    try {
      setSubmitting(true);
      setErrorMessage(null);
      const payload = await requestAmls<TestCurrentProblemResponse>(
        `/tests/${testAttempt.id}/resume`,
        token,
        {
          method: "POST",
        },
      );
      setTestAttempt(payload.test_attempt);
      setCurrentProblem(payload.problem);
      setSelectedAnswerId(null);
      setRevealedSolution(null);
    } catch (error: unknown) {
      if (isRecoverableAuthError(error)) {
        handleSessionRecovery(error.backendMessage);
        return;
      }

      const message = error instanceof Error ? error.message : "Failed to resume test";
      setErrorMessage(message);
    } finally {
      setSubmitting(false);
    }
  }, [handleSessionRecovery, submitting, testAttempt, token]);

  const timerLabel = useMemo(() => formatElapsedSeconds(elapsedSeconds), [elapsedSeconds]);

  return (
    <div className="min-h-screen px-4 py-5 lg:px-6 lg:py-6">
      {calculatingScore ? (
        <FullscreenLoadingOverlay
          title="Calculating your score..."
          message="Finalizing results and preparing the full review."
        />
      ) : null}
      {shouldShowTestOperationOverlay ? (
        <FullscreenLoadingOverlay
          title={testOperationOverlayTitle}
          message={testOperationOverlayMessage}
        />
      ) : null}
      <div className="mx-auto flex max-w-[1200px] flex-col gap-5">
        <header className="app-surface rounded-[1.9rem] px-5 py-4 sm:px-6">
          <div className="flex flex-col gap-4 md:flex-row md:items-center md:justify-between">
            <div>
              <p className="section-kicker">Test runner</p>
              <p className="section-title text-3xl text-foreground">
                {testAttempt ? `${formatTestKindLabel(testAttempt.kind)} test` : "Loading test"}
              </p>
              <p className="mt-2 text-sm text-muted-foreground">
                Dedicated test page with pause-aware timer and detailed final review.
              </p>
            </div>
            <div className="flex flex-wrap gap-2">
              <ThemeToggleButton />
              <Link href={`/courses/${courseId}/workspace`} className={buttonVariants({ variant: "outline", size: "sm" })}>
                <ArrowLeft />
                Workspace
              </Link>
              <Link href={`/courses/${courseId}/tests/history`} className={buttonVariants({ variant: "outline", size: "sm" })}>
                Review history
              </Link>
              <Button
                variant="outline"
                size="sm"
                onClick={() => {
                  if (token) {
                    void loadCurrentTest(token);
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

        {loading ? (
          <Card>
            <CardContent className="py-6">
              <SectionLoadingSkeleton lines={7} />
            </CardContent>
          </Card>
        ) : mismatchedAttempt ? (
          <Card>
            <CardContent className="space-y-3 py-6">
              <p className="text-sm text-muted-foreground">
                Active test attempt is {testAttempt?.id}. Open that test to continue.
              </p>
              {testAttempt ? (
                <Link href={`/courses/${courseId}/tests/${testAttempt.id}`} className={buttonVariants()}>
                  Open active attempt
                </Link>
              ) : null}
            </CardContent>
          </Card>
        ) : (
          <Card>
            <CardHeader>
              <p className="section-kicker">Current attempt</p>
              <CardTitle>
                Status: {testAttempt?.status ?? "unknown"} • Elapsed solving time: {timerLabel}
              </CardTitle>
            </CardHeader>
            <CardContent className="space-y-4">
              {isPaused ? (
                <div className="space-y-3">
                  <p className="text-sm text-muted-foreground">
                    This test is paused. Resume to continue answering.
                  </p>
                  <Button disabled={submitting} onClick={() => {
                    void handleResumeTest();
                  }}>
                    <Play />
                    <InlineLoadingLabel loading={submitting} idleText="Resume test" loadingText="Resuming test" />
                  </Button>
                </div>
              ) : null}

              {isTerminal ? (
                <div className="space-y-3">
                  {loadingReviewData ? (
                    <SectionLoadingSkeleton lines={6} />
                  ) : attemptReview ? (
                    <TestAttemptReviewPanel
                      reviewPayload={attemptReview}
                      linkedAssessment={linkedAssessment}
                    />
                  ) : (
                    <div className="rounded-[1rem] border border-border/70 bg-background/80 px-3 py-3 text-sm text-muted-foreground">
                      Review details are unavailable right now. Refresh to try loading them again.
                    </div>
                  )}
                </div>
              ) : null}

              {!isPaused && !isTerminal && currentProblem ? (
                <div className="space-y-3">
                  <div className="rounded-[1rem] border border-border/70 bg-background/80 px-3 py-3">
                    <p className="text-xs font-semibold uppercase tracking-[0.15em] text-primary">Condition</p>
                    <MathText content={currentProblem.condition} className="mt-2 text-sm leading-7 text-foreground" />
                  </div>
                  <div className="space-y-2">
                    {currentProblem.answer_options.map((answerOption) => (
                      <button
                        key={answerOption.id}
                        type="button"
                        className={`w-full rounded-[1.2rem] border px-4 py-3 text-left transition ${selectedAnswerId === answerOption.id ? "border-primary bg-primary/12 text-foreground" : "border-border/70 bg-background/78 text-foreground hover:border-primary/40 hover:bg-primary/8"}`}
                        onClick={() => setSelectedAnswerId(answerOption.id)}
                        disabled={submitting}
                      >
                        <MathText content={answerOption.text} className="text-sm leading-7" />
                      </button>
                    ))}
                  </div>
                  <div className="flex flex-wrap gap-2">
                    <Button
                      disabled={!selectedAnswerId || submitting}
                      onClick={() => {
                        void handleSubmitAnswer();
                      }}
                    >
                      <Send />
                      <InlineLoadingLabel loading={submitting} idleText="Submit answer" loadingText="Submitting answer" />
                    </Button>
                    <Button
                      variant="outline"
                      disabled={submitting}
                      onClick={() => {
                        void handleRevealSolution();
                      }}
                    >
                      <Sparkles />
                      <InlineLoadingLabel loading={submitting} idleText="Reveal solution" loadingText="Revealing solution" />
                    </Button>
                    <Button
                      variant="outline"
                      disabled={submitting}
                      onClick={() => {
                        void handlePauseTest();
                      }}
                    >
                      <PauseCircle />
                      <InlineLoadingLabel loading={submitting} idleText="Pause" loadingText="Pausing" />
                    </Button>
                  </div>
                </div>
              ) : null}

              {!isPaused && !isTerminal && !currentProblem ? (
                <div className="space-y-3">
                  <p className="text-sm text-muted-foreground">
                    This attempt has no active question right now.
                  </p>
                  <Button
                    variant="outline"
                    disabled={submitting}
                    onClick={() => {
                      if (token) {
                        void loadCurrentTest(token);
                      }
                    }}
                  >
                    <RefreshCw />
                    Refresh test state
                  </Button>
                </div>
              ) : null}

              {revealedSolution && !isTerminal ? (
                <div className="rounded-[1rem] border border-border/70 bg-background/80 px-3 py-3">
                  <p className="text-xs font-semibold uppercase tracking-[0.15em] text-primary">Revealed solution</p>
                  <MathText content={revealedSolution.solution} className="mt-2 text-sm leading-7 text-foreground" />
                </div>
              ) : null}
            </CardContent>
          </Card>
        )}
      </div>
    </div>
  );
}
