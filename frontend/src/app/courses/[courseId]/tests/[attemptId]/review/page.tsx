"use client";

import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { useCallback, useEffect, useRef, useState } from "react";
import { ArrowLeft, RefreshCw } from "lucide-react";
import { FullscreenLoadingOverlay, InlineLoadingLabel, SectionLoadingSkeleton } from "@/components/AppLoading";
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
import type { GraphAssessmentResponse, TestAttemptReviewResponse } from "@/lib/api-types";
import { Button, buttonVariants } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";

const TEST_REVIEW_PAGE_LOG_SCOPE = "[TestReviewPage]";


function isRecoverableAuthError(error: unknown): error is AmlsRequestError {
  return error instanceof AmlsRequestError && error.recoverSession;
}


function findAssessmentForAttempt(
  assessments: GraphAssessmentResponse[],
  attemptId: string,
): GraphAssessmentResponse | null {
  return assessments.find((assessment) => assessment.source_test_attempt_id === attemptId) ?? null;
}


export default function CourseTestReviewPage() {
  const router = useRouter();
  const params = useParams<{ courseId: string; attemptId: string }>();
  const rawCourseId = params.courseId;
  const rawAttemptId = params.attemptId;
  const courseId = Array.isArray(rawCourseId) ? rawCourseId[0] : rawCourseId;
  const attemptId = Array.isArray(rawAttemptId) ? rawAttemptId[0] : rawAttemptId;

  const [token, setToken] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [reviewPayload, setReviewPayload] = useState<TestAttemptReviewResponse | null>(null);
  const [linkedAssessment, setLinkedAssessment] = useState<GraphAssessmentResponse | null>(null);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const hasInitializedRef = useRef(false);
  const shouldShowBlockingOverlay = loading;

  const handleSessionRecovery = useCallback((backendMessage: string) => {
    console.warn(`${TEST_REVIEW_PAGE_LOG_SCOPE} Session recovery required`, {
      backendMessage,
      courseId,
      attemptId,
    });
    clearAuthToken();
    storeSessionNotice(getSessionExpiredMessage());
    router.replace("/");
  }, [attemptId, courseId, router]);

  const loadReview = useCallback(async (authToken: string) => {
    try {
      setLoading(true);
      setErrorMessage(null);
      const [attemptReviewPayload, assessments] = await Promise.all([
        requestAmls<TestAttemptReviewResponse>(
          `/tests/${attemptId}/review`,
          authToken,
        ),
        requestAmls<GraphAssessmentResponse[]>(
          `/courses/${courseId}/graph-assessments`,
          authToken,
        ),
      ]);

      setReviewPayload(attemptReviewPayload);
      setLinkedAssessment(findAssessmentForAttempt(assessments, attemptId));
      console.log(`${TEST_REVIEW_PAGE_LOG_SCOPE} Loaded detailed review`, {
        attemptId,
        itemCount: attemptReviewPayload.items.length,
      });
    } catch (error: unknown) {
      if (isRecoverableAuthError(error)) {
        handleSessionRecovery(error.backendMessage);
        return;
      }

      const message = error instanceof Error ? error.message : "Failed to load detailed review";
      setErrorMessage(message);
    } finally {
      setLoading(false);
    }
  }, [attemptId, courseId, handleSessionRecovery]);

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
    void loadReview(storedToken);
  }, [attemptId, courseId, loadReview, router]);

  return (
    <div className="min-h-screen px-4 py-5 lg:px-6 lg:py-6">
      {shouldShowBlockingOverlay ? (
        <FullscreenLoadingOverlay
          title="Loading detailed review"
          message="Preparing score details and advice for this attempt."
        />
      ) : null}
      <div className="mx-auto flex max-w-[1200px] flex-col gap-5">
        <header className="app-surface rounded-[1.9rem] px-5 py-4 sm:px-6">
          <div className="flex flex-col gap-4 md:flex-row md:items-center md:justify-between">
            <div>
              <p className="section-kicker">Attempt review</p>
              <p className="section-title text-3xl text-foreground">Detailed test analysis</p>
            </div>
            <div className="flex flex-wrap gap-2">
              <ThemeToggleButton />
              <Link href={`/courses/${courseId}/tests/history`} className={buttonVariants({ variant: "outline", size: "sm" })}>
                <ArrowLeft />
                Test history
              </Link>
              <Link href={`/courses/${courseId}/workspace`} className={buttonVariants({ variant: "outline", size: "sm" })}>
                Workspace
              </Link>
              <Button
                variant="outline"
                size="sm"
                onClick={() => {
                  if (token) {
                    void loadReview(token);
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
              <SectionLoadingSkeleton lines={10} />
            </CardContent>
          </Card>
        ) : reviewPayload ? (
          <TestAttemptReviewPanel
            reviewPayload={reviewPayload}
            linkedAssessment={linkedAssessment}
          />
        ) : (
          <Card>
            <CardContent className="py-6 text-sm text-muted-foreground">
              No review details are available for this attempt.
            </CardContent>
          </Card>
        )}
      </div>
    </div>
  );
}
