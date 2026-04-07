"use client";

import Link from "next/link";
import { useParams, useRouter, useSearchParams } from "next/navigation";
import { useCallback, useEffect, useMemo, useState } from "react";
import { ArrowLeft, RefreshCw } from "lucide-react";
import { FullscreenLoadingOverlay, InlineLoadingLabel, SectionLoadingSkeleton } from "@/components/AppLoading";
import MathText from "@/components/MathText";
import ThemeToggleButton from "@/components/ThemeToggleButton";
import {
  AmlsRequestError,
  clearAuthToken,
  getSessionExpiredMessage,
  getStoredAuthToken,
  requestAmls,
  storeSessionNotice,
} from "@/lib/amls-client";
import type { LectureDetailResponse } from "@/lib/api-types";
import { Button, buttonVariants } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";

const LECTURE_LOG_SCOPE = "[LecturePage]";


function isRecoverableAuthError(error: unknown): error is AmlsRequestError {
  return error instanceof AmlsRequestError && error.recoverSession;
}


export default function CourseLecturePage() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const params = useParams<{ courseId: string; lectureId: string }>();
  const rawCourseId = params.courseId;
  const rawLectureId = params.lectureId;
  const courseId = Array.isArray(rawCourseId) ? rawCourseId[0] : rawCourseId;
  const lectureId = Array.isArray(rawLectureId) ? rawLectureId[0] : rawLectureId;
  const [token, setToken] = useState<string | null>(null);
  const [lectureDetail, setLectureDetail] = useState<LectureDetailResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const rawPageNumber = searchParams.get("page");
  const pageNumber = Number(rawPageNumber ?? "1");
  const normalizedPageNumber = Number.isInteger(pageNumber) ? pageNumber : 1;
  const shouldShowBlockingOverlay = loading;

  const handleSessionRecovery = useCallback((backendMessage: string) => {
    console.warn(`${LECTURE_LOG_SCOPE} Session recovery required`, {
      backendMessage,
      lectureId,
    });
    clearAuthToken();
    storeSessionNotice(getSessionExpiredMessage());
    router.replace("/");
  }, [lectureId, router]);

  const loadLecture = useCallback(async (authToken: string) => {
    try {
      setLoading(true);
      setErrorMessage(null);
      const payload = await requestAmls<LectureDetailResponse>(`/lectures/${lectureId}`, authToken);
      setLectureDetail(payload);
    } catch (error: unknown) {
      if (isRecoverableAuthError(error)) {
        handleSessionRecovery(error.backendMessage);
        return;
      }

      const message = error instanceof Error ? error.message : "Failed to load lecture";
      setErrorMessage(message);
    } finally {
      setLoading(false);
    }
  }, [handleSessionRecovery, lectureId]);

  const orderedPages = useMemo(() => {
    if (!lectureDetail) {
      return [];
    }

    return [...lectureDetail.pages].sort((left, right) => left.page_number - right.page_number);
  }, [lectureDetail]);

  const currentPageIndex = useMemo(() => {
    if (orderedPages.length === 0) {
      return -1;
    }

    const pageIndex = orderedPages.findIndex((page) => page.page_number === normalizedPageNumber);
    if (pageIndex >= 0) {
      return pageIndex;
    }
    return 0;
  }, [normalizedPageNumber, orderedPages]);

  const currentPage = currentPageIndex >= 0 ? orderedPages[currentPageIndex] : null;

  const navigateToPage = useCallback((nextPageNumber: number) => {
    const nextSearchParams = new URLSearchParams(searchParams.toString());
    nextSearchParams.set("page", String(nextPageNumber));
    router.replace(`/courses/${courseId}/lectures/${lectureId}?${nextSearchParams.toString()}`);
    console.log(`${LECTURE_LOG_SCOPE} Navigated to lecture page`, {
      lectureId,
      pageNumber: nextPageNumber,
    });
  }, [courseId, lectureId, router, searchParams]);

  useEffect(() => {
    if (!courseId || !lectureId) {
      router.replace("/dashboard");
      return;
    }

    const storedToken = getStoredAuthToken();
    if (!storedToken) {
      router.replace("/");
      return;
    }

    setToken(storedToken);
    void loadLecture(storedToken);
  }, [courseId, lectureId, loadLecture, router]);

  useEffect(() => {
    if (!courseId || !lectureId || loading || orderedPages.length === 0) {
      return;
    }
    const validPageNumbers = new Set(orderedPages.map((page) => page.page_number));
    if (rawPageNumber === null || !Number.isInteger(pageNumber) || !validPageNumbers.has(normalizedPageNumber)) {
      navigateToPage(orderedPages[0].page_number);
    }
  }, [
    courseId,
    lectureId,
    loading,
    navigateToPage,
    pageNumber,
    normalizedPageNumber,
    orderedPages,
    rawPageNumber,
  ]);

  return (
    <div className="min-h-screen px-4 py-5 lg:px-6 lg:py-6">
      {shouldShowBlockingOverlay ? (
        <FullscreenLoadingOverlay
          title="Loading lecture"
          message="Preparing lecture content and page navigation."
        />
      ) : null}
      <div className="mx-auto flex max-w-[1200px] flex-col gap-5">
        <header className="app-surface rounded-[1.9rem] px-5 py-4 sm:px-6">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div>
              <p className="section-kicker">Lecture</p>
              <p className="section-title text-3xl text-foreground">{lectureDetail?.lecture.title ?? "Loading lecture"}</p>
            </div>
            <div className="flex flex-wrap items-center gap-2">
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
                    void loadLecture(token);
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
            <CardTitle>{lectureDetail?.lecture.title ?? "Lecture details"}</CardTitle>
          </CardHeader>
          <CardContent>
            {loading ? (
              <SectionLoadingSkeleton lines={6} />
            ) : currentPage ? (
              <div className="space-y-3">
                <div className="rounded-[1rem] border border-border/70 bg-background/76 px-3 py-3">
                  <p className="text-xs font-semibold uppercase tracking-[0.15em] text-primary">
                    Page {currentPage.page_number}
                  </p>
                  <MathText content={currentPage.page_content} className="mt-2 text-sm leading-7 text-foreground" />
                </div>
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <Button
                    variant="outline"
                    size="sm"
                    disabled={currentPageIndex <= 0}
                    onClick={() => {
                      if (currentPageIndex > 0) {
                        navigateToPage(orderedPages[currentPageIndex - 1].page_number);
                      }
                    }}
                  >
                    Previous page
                  </Button>
                  <p className="text-sm text-muted-foreground">
                    Page {currentPageIndex + 1} of {orderedPages.length}
                  </p>
                  <Button
                    variant="outline"
                    size="sm"
                    disabled={currentPageIndex < 0 || currentPageIndex >= orderedPages.length - 1}
                    onClick={() => {
                      if (currentPageIndex >= 0 && currentPageIndex < orderedPages.length - 1) {
                        navigateToPage(orderedPages[currentPageIndex + 1].page_number);
                      }
                    }}
                  >
                    Next page
                  </Button>
                </div>
              </div>
            ) : (
              <p className="text-sm text-muted-foreground">No lecture pages are available.</p>
            )}
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
