"use client";

import { Background, Controls, type NodeTypes, ReactFlow } from "@xyflow/react";
import { useCallback, useEffect, useState } from "react";
import { CheckCircle2, CircleDot, Lock, Radar } from "lucide-react";
import MathFlowNode from "@/components/MathFlowNode";
import MathText from "@/components/MathText";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardFooter, CardHeader, CardTitle } from "@/components/ui/card";
import { Label } from "@/components/ui/label";
import {
  type EntranceTestResultGraphModel,
  buildEntranceTestResultGraph,
} from "@/lib/entrance-test-result-graph";
import {
  EntranceTestAnswerResponse,
  EntranceTestCurrentProblemResponse,
  EntranceTestResultResponse,
  EntranceTestSessionResponse,
  ProblemResponse,
} from "@/lib/api-types";

const ENTRANCE_TEST_LOG_SCOPE = "[EntranceTest]";

const resultGraphNodeTypes = {
  mathNode: MathFlowNode,
} satisfies NodeTypes;

const RESULT_METRIC_ITEMS = [
  {
    key: "learned",
    label: "Learned",
    accentClassName: "text-emerald-600 dark:text-emerald-300",
    icon: CheckCircle2,
  },
  {
    key: "ready",
    label: "Ready",
    accentClassName: "text-primary",
    icon: CircleDot,
  },
  {
    key: "locked",
    label: "Locked",
    accentClassName: "text-foreground",
    icon: Lock,
  },
  {
    key: "frontier",
    label: "Frontier",
    accentClassName: "text-amber-500 dark:text-amber-300",
    icon: Radar,
  },
] as const;

const RESULT_LEGEND_ITEMS = [
  {
    label: "Learned",
    className: "border-emerald-200 bg-emerald-50 text-emerald-700 dark:border-emerald-900/60 dark:bg-emerald-950/40 dark:text-emerald-200",
  },
  {
    label: "Ready",
    className: "border-primary/20 bg-primary/10 text-primary",
  },
  {
    label: "Locked",
    className: "border-border bg-muted/70 text-foreground",
  },
  {
    label: "Frontier",
    className: "border-amber-200 bg-amber-50 text-amber-700 dark:border-amber-900/60 dark:bg-amber-950/30 dark:text-amber-200",
  },
] as const;

interface EntranceTestProps {
  token: string;
}


function getCaughtErrorMessage(error: unknown, fallbackMessage: string): string {
  if (error instanceof Error) {
    return error.message;
  }

  return fallbackMessage;
}


function getResponseErrorMessage(
  payload: unknown,
  fallbackMessage: string,
): string {
  if (typeof payload !== "object" || payload === null) {
    return fallbackMessage;
  }

  const responsePayload = payload as {
    detail?: unknown;
    error?: unknown;
  };

  if (typeof responsePayload.detail === "string") {
    return responsePayload.detail;
  }

  if (Array.isArray(responsePayload.detail) && responsePayload.detail.length > 0) {
    const firstDetail = responsePayload.detail[0];

    if (typeof firstDetail === "string") {
      return firstDetail;
    }

    if (
      typeof firstDetail === "object"
      && firstDetail !== null
      && "msg" in firstDetail
      && typeof firstDetail.msg === "string"
    ) {
      return firstDetail.msg;
    }
  }

  if (typeof responsePayload.error === "string") {
    return responsePayload.error;
  }

  return fallbackMessage;
}


function formatProbabilityAsPercentage(probability: number): string {
  return `${(probability * 100).toFixed(1)}%`;
}


export default function EntranceTest({ token }: EntranceTestProps) {
  const [session, setSession] = useState<EntranceTestSessionResponse | null>(null);
  const [currentProblem, setCurrentProblem] = useState<ProblemResponse | null>(null);
  const [result, setResult] = useState<EntranceTestResultResponse | null>(null);
  const [resultGraph, setResultGraph] = useState<EntranceTestResultGraphModel | null>(null);
  const [loading, setLoading] = useState(true);
  const [loadingResult, setLoadingResult] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [selectedAnswerId, setSelectedAnswerId] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);


  const fetchCurrentProblem = useCallback(async () => {
    const response = await fetch("/api/entrance-test/current-problem", {
      headers: { Authorization: `Bearer ${token}` },
    });

    const payload = await response.json().catch(() => null);

    if (!response.ok) {
      throw new Error(
        getResponseErrorMessage(payload, "Failed to fetch current problem"),
      );
    }

    const data = payload as EntranceTestCurrentProblemResponse;

    setCurrentProblem(data.problem);
  }, [token]);


  const fetchResult = useCallback(async () => {
    const startedAt = Date.now();

    console.log(`${ENTRANCE_TEST_LOG_SCOPE} Fetching personalized graph state`, {
      startedAt,
    });

    setLoadingResult(true);

    try {
      const response = await fetch("/api/entrance-test/result", {
        headers: { Authorization: `Bearer ${token}` },
      });

      const payload = await response.json().catch(() => null);

      if (!response.ok) {
        const message = getResponseErrorMessage(payload, "Failed to fetch result");

        console.error(`${ENTRANCE_TEST_LOG_SCOPE} Personalized graph fetch failed`, {
          durationInMilliseconds: Date.now() - startedAt,
          message,
          statusCode: response.status,
        });

        throw new Error(message);
      }

      const data = payload as EntranceTestResultResponse;

      console.log(`${ENTRANCE_TEST_LOG_SCOPE} Personalized graph fetched`, {
        durationInMilliseconds: Date.now() - startedAt,
        edgeCount: data.edges.length,
        nodeCount: data.nodes.length,
        stateIndex: data.final_result.state_index,
        stateProbability: data.final_result.state_probability,
        subtopicSummaryCount: data.subtopic_summaries.length,
        topicSummaryCount: data.topic_summaries.length,
      });

      setCurrentProblem(null);
      setResult(data);

      return data;
    } finally {
      setLoadingResult(false);
    }
  }, [token]);


  const fetchSession = useCallback(async () => {
    try {
      setLoading(true);
      setError(null);

      const response = await fetch("/api/entrance-test", {
        headers: { Authorization: `Bearer ${token}` },
      });

      const payload = await response.json().catch(() => null);

      if (!response.ok) {
        throw new Error(getResponseErrorMessage(payload, "Failed to fetch session"));
      }

      const data = payload as EntranceTestSessionResponse;

      console.log(`${ENTRANCE_TEST_LOG_SCOPE} Session fetched`, {
        currentProblemId: data.current_problem_id,
        sessionId: data.id,
        status: data.status,
        structureVersion: data.structure_version,
      });

      setSession(data);

      if (data.status === "active") {
        setResult(null);
        await fetchCurrentProblem();
      } else if (data.status === "completed") {
        await fetchResult();
      } else {
        setCurrentProblem(null);
        setResult(null);
      }
    } catch (caughtError: unknown) {
      setError(getCaughtErrorMessage(caughtError, "An unknown error occurred"));
    } finally {
      setLoading(false);
    }
  }, [fetchCurrentProblem, fetchResult, token]);


  useEffect(() => {
    void fetchSession();
  }, [fetchSession]);


  useEffect(() => {
    if (!result) {
      setResultGraph(null);
      return;
    }

    const nextResultGraph = buildEntranceTestResultGraph(result);

    console.log(`${ENTRANCE_TEST_LOG_SCOPE} Prepared personalized graph model`, {
      edgeCount: nextResultGraph.edges.length,
      nodeCount: nextResultGraph.nodes.length,
      statusCounts: nextResultGraph.statusCounts,
    });

    setResultGraph(nextResultGraph);
  }, [result]);


  useEffect(() => {
    if (!resultGraph) {
      return;
    }

    console.log(`${ENTRANCE_TEST_LOG_SCOPE} Rendering personalized graph`, {
      edgeCount: resultGraph.edges.length,
      nodeCount: resultGraph.nodes.length,
      statusCounts: resultGraph.statusCounts,
    });
  }, [resultGraph]);


  const handleStart = async () => {
    try {
      setLoading(true);
      setError(null);
      setResult(null);
      setResultGraph(null);

      const response = await fetch("/api/entrance-test/start", {
        method: "POST",
        headers: { Authorization: `Bearer ${token}` },
      });

      const payload = await response.json().catch(() => null);

      if (!response.ok) {
        throw new Error(getResponseErrorMessage(payload, "Failed to start test"));
      }

      const data = payload as EntranceTestCurrentProblemResponse;

      setSession(data.session);
      setCurrentProblem(data.problem);
    } catch (caughtError: unknown) {
      setError(getCaughtErrorMessage(caughtError, "Failed to start test"));
    } finally {
      setLoading(false);
    }
  };


  const handleSubmit = async () => {
    if (!selectedAnswerId || !currentProblem) {
      return;
    }

    try {
      setSubmitting(true);
      setError(null);

      const response = await fetch("/api/entrance-test/answers", {
        method: "POST",
        headers: {
          Authorization: `Bearer ${token}`,
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          problem_id: currentProblem.id,
          answer_option_id: selectedAnswerId,
        }),
      });

      const payload = await response.json().catch(() => null);

      if (!response.ok) {
        throw new Error(getResponseErrorMessage(payload, "Failed to submit answer"));
      }

      const data = payload as EntranceTestAnswerResponse;

      setSession(data.session);
      setCurrentProblem(data.next_problem);
      setSelectedAnswerId(null);

      if (data.session.status === "completed") {
        console.log(`${ENTRANCE_TEST_LOG_SCOPE} Entrance test completed after answer`, {
          answerOptionId: selectedAnswerId,
          finalStateIndex: data.final_result?.state_index ?? null,
          finalStateProbability: data.final_result?.state_probability ?? null,
          problemId: currentProblem.id,
          sessionId: data.session.id,
        });

        await fetchResult();
      }
    } catch (caughtError: unknown) {
      setError(getCaughtErrorMessage(caughtError, "Failed to submit answer"));
    } finally {
      setSubmitting(false);
    }
  };


  const handleComplete = async () => {
    try {
      setSubmitting(true);
      setError(null);

      const response = await fetch("/api/entrance-test/complete", {
        method: "POST",
        headers: { Authorization: `Bearer ${token}` },
      });

      const payload = await response.json().catch(() => null);

      if (!response.ok) {
        throw new Error(getResponseErrorMessage(payload, "Failed to complete test"));
      }

      const data = payload as EntranceTestSessionResponse;

      console.log(`${ENTRANCE_TEST_LOG_SCOPE} Completing entrance test session`, {
        sessionId: data.id,
        status: data.status,
      });

      setSession(data);
      await fetchResult();
    } catch (caughtError: unknown) {
      setError(getCaughtErrorMessage(caughtError, "Failed to complete test"));
    } finally {
      setSubmitting(false);
    }
  };


  if (loading) {
    return (
      <div className="flex h-full items-center justify-center p-6">
        <Card className="w-full max-w-2xl">
          <CardHeader>
            <p className="section-kicker">Entrance diagnostic</p>
            <CardTitle>Loading Entrance Test</CardTitle>
          </CardHeader>
          <CardContent>
            <p className="text-sm leading-7 text-muted-foreground">
              Syncing the session, current prompt, and projected learner state.
            </p>
          </CardContent>
        </Card>
      </div>
    );
  }

  if (error) {
    return (
      <div className="flex h-full items-center justify-center p-6">
        <Card className="w-full max-w-2xl">
          <CardHeader>
            <p className="section-kicker">Entrance diagnostic</p>
            <CardTitle>Entrance Test Error</CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            <p className="text-sm leading-7 text-muted-foreground">{error}</p>
            <div>
              <Button
                variant="outline"
                onClick={() => {
                  void fetchSession();
                }}
              >
                Retry session sync
              </Button>
            </div>
          </CardContent>
        </Card>
      </div>
    );
  }

  if (session?.status === "completed" && (loadingResult || !result || !resultGraph)) {
    return (
      <div className="flex h-full items-center justify-center p-6">
        <Card className="w-full max-w-3xl">
          <CardHeader>
            <p className="section-kicker">Result projection</p>
            <CardTitle>Loading Personalized Graph</CardTitle>
          </CardHeader>
          <CardContent>
            <p className="text-sm leading-7 text-muted-foreground">
              Mapping the final learner state onto the graph and preparing topic summaries.
            </p>
          </CardContent>
        </Card>
      </div>
    );
  }

  if (!session || session.status === "pending" || session.status === "skipped") {
    return (
      <div className="flex h-full items-center justify-center p-4 lg:p-6">
        <Card className="w-full max-w-5xl">
          <CardHeader>
            <p className="section-kicker">Entrance diagnostic</p>
            <CardTitle>Entrance Test</CardTitle>
          </CardHeader>
          <CardContent className="space-y-6">
            <p className="max-w-3xl text-sm leading-7 text-muted-foreground">
              Run a short adaptive test to estimate the learner state, highlight what is already
              learned, and show the next ready frontier on the graph.
            </p>
            <div className="grid gap-3 md:grid-cols-3">
              <div className="rounded-[1.5rem] border border-border/70 bg-background/72 p-4">
                <p className="text-sm font-semibold text-foreground">Adaptive questions</p>
                <p className="mt-3 text-sm leading-6 text-muted-foreground">
                  Each answer shifts the estimated position in the mastery graph.
                </p>
              </div>
              <div className="rounded-[1.5rem] border border-border/70 bg-background/72 p-4">
                <p className="text-sm font-semibold text-foreground">Graph projection</p>
                <p className="mt-3 text-sm leading-6 text-muted-foreground">
                  The final result marks learned, ready, locked, and frontier nodes.
                </p>
              </div>
              <div className="rounded-[1.5rem] border border-border/70 bg-background/72 p-4">
                <p className="text-sm font-semibold text-foreground">Readable summaries</p>
                <p className="mt-3 text-sm leading-6 text-muted-foreground">
                  Topic and subtopic cards make the result easy to present in a demo.
                </p>
              </div>
            </div>
          </CardContent>
          <CardFooter>
            <Button onClick={handleStart} className="w-full sm:w-auto">
              Start Entrance Test
            </Button>
          </CardFooter>
        </Card>
      </div>
    );
  }

  if (session.status === "active" && currentProblem) {
    return (
      <div className="flex h-full items-start justify-center p-4 lg:p-6">
        <Card className="w-full max-w-5xl">
          <CardHeader>
            <p className="section-kicker">Current question</p>
            <CardTitle>Entrance Test Question</CardTitle>
          </CardHeader>
          <CardContent className="space-y-6">
            <div className="rounded-[1.7rem] border border-border/70 bg-background/74 p-5">
              <p className="text-sm font-semibold text-foreground">Current prompt</p>
              <MathText
                content={currentProblem.condition}
                className="mt-4 text-lg font-semibold leading-8 text-foreground"
              />
            </div>

            <div className="space-y-4">
              <Label>Choose an answer</Label>
              <div className="grid gap-3">
                {currentProblem.answer_options.map((option) => {
                  const isSelected = selectedAnswerId === option.id;

                  return (
                    <button
                      key={option.id}
                      type="button"
                      className={`rounded-[1.5rem] border px-4 py-4 text-left transition-all ${
                        isSelected
                          ? "border-primary/25 bg-primary/10 shadow-[0_16px_36px_rgba(82,112,235,0.14)]"
                          : "border-border/70 bg-background/74 hover:border-primary/20 hover:bg-accent"
                      }`}
                      onClick={() => setSelectedAnswerId(option.id)}
                    >
                      <div className="flex items-center justify-between gap-4">
                        <span className="text-sm font-semibold text-foreground">
                          Answer option
                        </span>
                        <span
                          className={`rounded-full px-3 py-1 text-xs font-semibold ${
                            isSelected
                              ? "border border-primary/20 bg-primary/10 text-primary"
                              : "border border-border/70 bg-background/80 text-muted-foreground"
                          }`}
                        >
                          {isSelected ? "Selected" : "Available"}
                        </span>
                      </div>
                      <MathText
                        content={option.text}
                        className="mt-3 text-sm leading-7 text-foreground"
                      />
                    </button>
                  );
                })}
              </div>
            </div>
          </CardContent>
          <CardFooter className="flex flex-col gap-3 sm:flex-row sm:justify-between">
            <Button variant="outline" onClick={handleComplete} disabled={submitting}>
              Finish and get results
            </Button>
            <Button onClick={handleSubmit} disabled={!selectedAnswerId || submitting}>
              {submitting ? "Submitting" : "Next Question"}
            </Button>
          </CardFooter>
        </Card>
      </div>
    );
  }

  if (session.status === "completed" && result && resultGraph) {
    return (
      <div className="flex h-full items-start justify-center p-4 lg:p-6">
        <Card className="w-full max-w-7xl">
          <CardHeader>
            <p className="section-kicker">Personalized result</p>
            <CardTitle>Entrance Test Completed</CardTitle>
          </CardHeader>
          <CardContent className="space-y-6">
            <div className="grid gap-4 xl:grid-cols-[minmax(0,1.08fr)_minmax(0,0.92fr)]">
              <div className="rounded-[1.7rem] border border-border/70 bg-background/74 p-5">
                <p className="text-sm font-semibold text-primary">Estimated Knowledge State</p>
                <div className="mt-3 space-y-2">
                  <p className="section-title text-3xl text-foreground">
                    State {result.final_result.state_index}
                  </p>
                  <p className="text-sm text-muted-foreground">
                    Confidence {formatProbabilityAsPercentage(result.final_result.state_probability)}
                  </p>
                </div>
                <p className="mt-4 max-w-2xl text-sm leading-7 text-muted-foreground">
                  The entrance assessment projected the learner onto a feasible mastery state and
                  mapped the result back onto the nearest graph frontier.
                </p>
              </div>

              <div className="grid gap-3 md:grid-cols-4 xl:grid-cols-2">
                {RESULT_METRIC_ITEMS.map((metricItem) => {
                  const Icon = metricItem.icon;

                  return (
                    <div
                      key={metricItem.key}
                      className="rounded-[1.5rem] border border-border/70 bg-background/74 p-4"
                    >
                      <div className="flex items-center gap-2 text-muted-foreground">
                        <Icon className="size-4" />
                        <p className="text-sm font-semibold">{metricItem.label}</p>
                      </div>
                      <p className={`mt-3 text-3xl font-semibold ${metricItem.accentClassName}`}>
                        {resultGraph.statusCounts[metricItem.key]}
                      </p>
                    </div>
                  );
                })}
              </div>
            </div>

            <div className="flex flex-wrap gap-3">
              {RESULT_LEGEND_ITEMS.map((legendItem) => (
                <div
                  key={legendItem.label}
                  className={`rounded-full border px-3 py-2 text-xs font-semibold ${legendItem.className}`}
                >
                  {legendItem.label}
                </div>
              ))}
            </div>

            <div
              data-testid="entrance-test-result-graph"
              className="graph-stage graph-flow overflow-hidden rounded-[1.9rem]"
            >
              <div className="h-[34rem] w-full">
                <ReactFlow
                  nodes={resultGraph.nodes}
                  edges={resultGraph.edges}
                  nodeTypes={resultGraphNodeTypes}
                  fitView
                  nodesDraggable={false}
                  nodesConnectable={false}
                  elementsSelectable={false}
                  panOnDrag
                >
                  <Background color="var(--surface-grid)" gap={30} size={1} />
                  <Controls />
                </ReactFlow>
              </div>
            </div>

            <div className="grid gap-4 lg:grid-cols-2">
              <Card size="sm">
                <CardHeader>
                  <CardTitle>Topic Summaries</CardTitle>
                </CardHeader>
                <CardContent className="space-y-3">
                  {result.topic_summaries.map((topicSummary) => (
                    <div
                      key={topicSummary.topic_id}
                      className="rounded-[1.3rem] border border-border/70 bg-background/72 p-4"
                    >
                      <div className="flex items-center justify-between gap-4">
                        <MathText
                          content={topicSummary.topic_name}
                          className="font-semibold text-foreground"
                        />
                        <p className="text-xs font-semibold text-muted-foreground">
                          {topicSummary.total_problem_types} nodes
                        </p>
                      </div>
                      <p className="mt-3 text-sm leading-7 text-muted-foreground">
                        {topicSummary.learned_count} learned / {topicSummary.ready_count} ready / {topicSummary.frontier_count} frontier / {topicSummary.locked_count} locked
                      </p>
                    </div>
                  ))}
                </CardContent>
              </Card>

              <Card size="sm">
                <CardHeader>
                  <CardTitle>Subtopic Summaries</CardTitle>
                </CardHeader>
                <CardContent className="max-h-80 space-y-3 overflow-auto">
                  {result.subtopic_summaries.map((subtopicSummary) => (
                    <div
                      key={subtopicSummary.subtopic_id}
                      className="rounded-[1.3rem] border border-border/70 bg-background/72 p-4"
                    >
                      <div className="flex flex-col gap-1">
                        <MathText
                          content={subtopicSummary.subtopic_name}
                          className="font-semibold text-foreground"
                        />
                        <MathText
                          content={subtopicSummary.topic_name}
                          className="text-xs font-semibold text-muted-foreground"
                        />
                      </div>
                      <p className="mt-3 text-sm leading-7 text-muted-foreground">
                        {subtopicSummary.learned_count} learned / {subtopicSummary.ready_count} ready / {subtopicSummary.frontier_count} frontier / {subtopicSummary.locked_count} locked
                      </p>
                    </div>
                  ))}
                </CardContent>
              </Card>
            </div>
          </CardContent>
          <CardFooter className="justify-end">
            <Button
              variant="outline"
              onClick={() => {
                void fetchResult();
              }}
              disabled={loadingResult}
            >
              {loadingResult ? "Refreshing" : "Refresh Result"}
            </Button>
          </CardFooter>
        </Card>
      </div>
    );
  }

  return (
    <div className="flex h-full items-center justify-center p-6">
      <Card className="w-full max-w-2xl">
        <CardHeader>
          <p className="section-kicker">Entrance diagnostic</p>
          <CardTitle>Unknown Session Status</CardTitle>
        </CardHeader>
        <CardContent>
          <p className="text-sm leading-7 text-muted-foreground">{session.status}</p>
        </CardContent>
      </Card>
    </div>
  );
}
