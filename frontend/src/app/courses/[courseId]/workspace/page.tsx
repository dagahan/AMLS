"use client";

import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { useCallback, useEffect, useMemo, useState } from "react";
import { Background, Controls, MiniMap, ReactFlow, useEdgesState, useNodesState } from "@xyflow/react";
import type { Edge, Node, NodeMouseHandler } from "@xyflow/react";
import "@xyflow/react/dist/style.css";
import {
  ArrowLeft,
  BookOpenCheck,
  ChartLine,
  History,
  LogOut,
  Play,
  Radar,
  RefreshCw,
  Route,
  Sparkles,
  TestTube2,
  UserRound,
} from "lucide-react";
import { FullscreenLoadingOverlay, InlineLoadingLabel, SectionLoadingSkeleton } from "@/components/AppLoading";
import MathFlowNode from "@/components/MathFlowNode";
import ThemeToggleButton from "@/components/ThemeToggleButton";
import type { WorkspaceGraphNodeData, WorkspaceGraphStatusCounts } from "@/lib/course-workspace-graph";
import { buildCourseWorkspaceGraph } from "@/lib/course-workspace-graph";
import {
  AmlsRequestError,
  clearAuthToken,
  getSessionExpiredMessage,
  getStoredAuthToken,
  requestAmls,
  storeSessionNotice,
} from "@/lib/amls-client";
import type {
  CourseWorkspaceResponse,
  TestAttemptKind,
  TestCurrentProblemResponse,
} from "@/lib/api-types";
import { formatTestKindLabel } from "@/lib/test-kind";
import { Button, buttonVariants } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";

const WORKSPACE_LOG_SCOPE = "[Workspace]";

type SelectionTestKind = "general" | "exam";

const emptyStatusCounts: WorkspaceGraphStatusCounts = {
  learned: 0,
  ready: 0,
  locked: 0,
  failed: 0,
  unknown: 0,
  frontier: 0,
};

const workspaceGraphNodeTypes = {
  mathNode: MathFlowNode,
};


function isRecoverableAuthError(error: unknown): error is AmlsRequestError {
  return error instanceof AmlsRequestError && error.recoverSession;
}


function formatProbabilityAsPercentage(value: number): string {
  return `${Math.round(value * 100)}%`;
}


export default function CourseWorkspacePage() {
  const router = useRouter();
  const params = useParams<{ courseId: string }>();
  const rawCourseId = params.courseId;
  const courseId = Array.isArray(rawCourseId) ? rawCourseId[0] : rawCourseId;

  const [token, setToken] = useState<string | null>(null);
  const [workspace, setWorkspace] = useState<CourseWorkspaceResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [startingTest, setStartingTest] = useState(false);
  const [pendingStartAction, setPendingStartAction] = useState<string | null>(null);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [focusedCourseNodeId, setFocusedCourseNodeId] = useState<string | null>(null);
  const [isSelectionMode, setIsSelectionMode] = useState(false);
  const [selectionKind, setSelectionKind] = useState<SelectionTestKind>("general");
  const [selectedCourseNodeIds, setSelectedCourseNodeIds] = useState<string[]>([]);
  const [statusCounts, setStatusCounts] = useState<WorkspaceGraphStatusCounts>(emptyStatusCounts);
  const [workspaceGraphNodes, setWorkspaceGraphNodes, onWorkspaceNodesChange] = useNodesState<Node<WorkspaceGraphNodeData>>([]);
  const [workspaceGraphEdges, setWorkspaceGraphEdges, onWorkspaceEdgesChange] = useEdgesState<Edge>([]);

  const focusedWorkspaceNode = useMemo(() => {
    if (!workspace || focusedCourseNodeId === null) {
      return null;
    }

    return workspace.nodes.find((node) => node.course_node_id === focusedCourseNodeId) ?? null;
  }, [focusedCourseNodeId, workspace]);

  const selectedNodeNames = useMemo(() => {
    if (!workspace || selectedCourseNodeIds.length === 0) {
      return [];
    }

    const nameById = new Map(
      workspace.nodes.map((node) => [node.course_node_id, node.name]),
    );

    return selectedCourseNodeIds
      .map((selectedId) => nameById.get(selectedId))
      .filter((name): name is string => typeof name === "string");
  }, [selectedCourseNodeIds, workspace]);

  const latestAssessment = workspace?.latest_graph_assessment ?? workspace?.active_graph_assessment ?? null;

  const handleSessionRecovery = useCallback((backendMessage: string) => {
    console.warn(`${WORKSPACE_LOG_SCOPE} Session recovery required`, {
      backendMessage,
      courseId,
    });
    clearAuthToken();
    storeSessionNotice(getSessionExpiredMessage());
    router.replace("/");
  }, [courseId, router]);

  const hydrateGraph = useCallback((workspacePayload: CourseWorkspaceResponse) => {
    const graphModel = buildCourseWorkspaceGraph(workspacePayload);
    setWorkspaceGraphNodes(graphModel.nodes);
    setWorkspaceGraphEdges(graphModel.edges);
    setStatusCounts(graphModel.statusCounts);
    setFocusedCourseNodeId(graphModel.nodes[0]?.id ?? null);
  }, [setWorkspaceGraphEdges, setWorkspaceGraphNodes]);

  const loadWorkspace = useCallback(async (authToken: string) => {
    try {
      setLoading(true);
      setErrorMessage(null);

      const payload = await requestAmls<CourseWorkspaceResponse>(
        `/courses/${courseId}/workspace`,
        authToken,
      );
      setWorkspace(payload);
      setSelectedCourseNodeIds([]);
      setIsSelectionMode(false);
      hydrateGraph(payload);

      console.log(`${WORKSPACE_LOG_SCOPE} Loaded workspace`, {
        courseId,
        nodeCount: payload.nodes.length,
        edgeCount: payload.edges.length,
        hasActiveAttempt: payload.action_flags.has_active_attempt,
      });
    } catch (error: unknown) {
      if (isRecoverableAuthError(error)) {
        handleSessionRecovery(error.backendMessage);
        return;
      }

      const message = error instanceof Error ? error.message : "Failed to load workspace";
      setErrorMessage(message);
    } finally {
      setLoading(false);
    }
  }, [courseId, handleSessionRecovery, hydrateGraph]);

  useEffect(() => {
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
    void loadWorkspace(storedToken);
  }, [courseId, loadWorkspace, router]);

  useEffect(() => {
    setWorkspaceGraphNodes((previousNodes) => previousNodes.map((node) => {
      const shouldBeSelected = isSelectionMode
        ? selectedCourseNodeIds.includes(node.id)
        : node.id === focusedCourseNodeId;

      if (node.selected === shouldBeSelected) {
        return node;
      }

      return {
        ...node,
        selected: shouldBeSelected,
      };
    }));
  }, [focusedCourseNodeId, isSelectionMode, selectedCourseNodeIds, setWorkspaceGraphNodes]);

  const startCourseTest = useCallback(async (
    kind: TestAttemptKind,
    actionKey: string,
    targetCourseNodeIds?: string[],
  ) => {
    if (!token) {
      return;
    }

    try {
      setStartingTest(true);
      setPendingStartAction(actionKey);
      setErrorMessage(null);

      const payload = await requestAmls<TestCurrentProblemResponse>(
        `/courses/${courseId}/tests/start`,
        token,
        {
          method: "POST",
          body: JSON.stringify({
            kind,
            target_course_node_ids: targetCourseNodeIds && targetCourseNodeIds.length > 0
              ? targetCourseNodeIds
              : undefined,
          }),
        },
      );

      console.log(`${WORKSPACE_LOG_SCOPE} Started test`, {
        courseId,
        kind,
        attemptId: payload.test_attempt.id,
        targetNodeCount: targetCourseNodeIds?.length ?? 0,
      });
      router.push(`/courses/${courseId}/tests/${payload.test_attempt.id}`);
    } catch (error: unknown) {
      if (isRecoverableAuthError(error)) {
        handleSessionRecovery(error.backendMessage);
        return;
      }

      const message = error instanceof Error ? error.message : "Failed to start test";
      setErrorMessage(message);
    } finally {
      setStartingTest(false);
      setPendingStartAction(null);
    }
  }, [courseId, handleSessionRecovery, router, token]);

  const handleLogout = useCallback(() => {
    clearAuthToken();
    router.replace("/");
  }, [router]);

  const handleGraphNodeClick = useCallback<NodeMouseHandler<Node<WorkspaceGraphNodeData>>>(
    (_, node) => {
      if (isSelectionMode) {
        setSelectedCourseNodeIds((previousSelectedNodeIds) => previousSelectedNodeIds.includes(node.id)
          ? previousSelectedNodeIds.filter((courseNodeId) => courseNodeId !== node.id)
          : [...previousSelectedNodeIds, node.id]);
        return;
      }

      setFocusedCourseNodeId(node.id);
    },
    [isSelectionMode],
  );

  const shouldShowBlockingWorkspaceOverlay = loading || startingTest;
  const blockingWorkspaceOverlayTitle = startingTest ? "Starting test..." : "Loading workspace";
  const blockingWorkspaceOverlayMessage = startingTest
    ? "Preparing selected problems and opening the test page."
    : "Building your course graph and loading available actions.";

  return (
    <div className="min-h-screen px-4 py-4 lg:px-6 lg:py-5">
      {shouldShowBlockingWorkspaceOverlay ? (
        <FullscreenLoadingOverlay
          title={blockingWorkspaceOverlayTitle}
          message={blockingWorkspaceOverlayMessage}
        />
      ) : null}
      <div className="mx-auto flex max-w-[1800px] flex-col gap-5">
        <header className="app-surface rounded-[1.9rem] px-5 py-4 sm:px-6">
          <div className="flex flex-col gap-4 lg:flex-row lg:items-center lg:justify-between">
            <div>
              <p className="section-kicker">Graph workspace</p>
              <p className="section-title text-3xl text-foreground">{workspace?.course.title ?? "Course workspace"}</p>
              <p className="mt-2 max-w-3xl text-sm text-muted-foreground">
                Graph-first workspace with dedicated pages for tests, lectures, and history.
              </p>
            </div>
            <div className="flex flex-wrap items-center gap-2">
              <Link href="/dashboard" className={buttonVariants({ variant: "outline", size: "sm" })}>
                <ArrowLeft />
                Dashboard
              </Link>
              <Link href="/profile" className={buttonVariants({ variant: "outline", size: "sm" })}>
                <UserRound />
                Profile
              </Link>
              <Link href={`/courses/${courseId}/tests/history`} className={buttonVariants({ variant: "outline", size: "sm" })}>
                <History />
                Test history
              </Link>
              <ThemeToggleButton />
              <Button
                variant="outline"
                size="sm"
                onClick={() => {
                  if (token) {
                    void loadWorkspace(token);
                  }
                }}
                disabled={loading}
              >
                <RefreshCw />
                <InlineLoadingLabel loading={loading} idleText="Refresh" loadingText="Refreshing" />
              </Button>
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

        <div className="grid gap-5 xl:grid-cols-[1.45fr_0.9fr]">
          <Card className="flex h-[78vh] min-h-[720px] flex-col">
            <CardHeader className="space-y-3">
              <div className="flex flex-wrap items-center gap-2">
                <Button
                  size="sm"
                  variant={isSelectionMode ? "default" : "outline"}
                  onClick={() => {
                    setIsSelectionMode((current) => !current);
                    setSelectedCourseNodeIds([]);
                  }}
                >
                  <Route />
                  {isSelectionMode ? "Selection mode enabled" : "Make custom test"}
                </Button>
              </div>
              {isSelectionMode ? (
                <div className="selection-sticky-panel px-3 py-3">
                  <div className="flex flex-col gap-3">
                    <div className="flex flex-wrap items-center justify-between gap-2">
                      <p className="text-sm font-semibold text-foreground">
                        Selected problem types: {selectedCourseNodeIds.length}
                      </p>
                      <div className="flex flex-wrap gap-2">
                        <Button
                          size="sm"
                          variant={selectionKind === "general" ? "default" : "outline"}
                          onClick={() => setSelectionKind("general")}
                        >
                          Practice
                        </Button>
                        <Button
                          size="sm"
                          variant={selectionKind === "exam" ? "default" : "outline"}
                          onClick={() => setSelectionKind("exam")}
                        >
                          Exam
                        </Button>
                      </div>
                    </div>
                    <div className="rounded-[0.9rem] border border-border/70 bg-background/75 px-3 py-2 text-sm text-muted-foreground">
                      {selectedNodeNames.length > 0 ? selectedNodeNames.join(" • ") : "Click graph cards to select problem types."}
                    </div>
                    <div className="flex flex-wrap items-center gap-2">
                      <Button
                        size="sm"
                        variant="outline"
                        onClick={() => setSelectedCourseNodeIds([])}
                        disabled={selectedCourseNodeIds.length === 0 || startingTest}
                      >
                        Clear selection
                      </Button>
                      <Button
                        size="sm"
                        disabled={selectedCourseNodeIds.length === 0 || startingTest}
                        onClick={() => {
                          void startCourseTest(selectionKind, "start-selected", selectedCourseNodeIds);
                        }}
                      >
                        <Play />
                        <InlineLoadingLabel
                          loading={startingTest && pendingStartAction === "start-selected"}
                          idleText="Start selected"
                          loadingText="Starting selected"
                        />
                      </Button>
                    </div>
                  </div>
                </div>
              ) : null}
            </CardHeader>
            <CardContent className="flex min-h-0 flex-1">
              {loading ? (
                <SectionLoadingSkeleton lines={8} className="w-full pt-4" />
              ) : workspaceGraphNodes.length === 0 ? (
                <div className="flex min-h-[520px] w-full items-center justify-center rounded-[1.5rem] border border-border/70 bg-background/55">
                  <p className="text-sm text-muted-foreground">No graph nodes are available.</p>
                </div>
              ) : (
                <div className="graph-stage h-full min-h-[520px] w-full rounded-[1.5rem]">
                  <ReactFlow
                    fitView
                    minZoom={0.2}
                    maxZoom={2}
                    nodes={workspaceGraphNodes}
                    edges={workspaceGraphEdges}
                    nodeTypes={workspaceGraphNodeTypes}
                    onNodesChange={onWorkspaceNodesChange}
                    onEdgesChange={onWorkspaceEdgesChange}
                    onNodeClick={handleGraphNodeClick}
                    className="graph-flow h-full w-full rounded-[1.5rem] bg-background/55"
                  >
                    <Background gap={20} size={1.2} />
                    <Controls />
                    <MiniMap pannable zoomable />
                  </ReactFlow>
                </div>
              )}
            </CardContent>
          </Card>

          <div className="flex flex-col gap-5">
            <Card>
              <CardHeader>
                <p className="section-kicker">Test actions</p>
                <CardTitle>Start or continue</CardTitle>
              </CardHeader>
              <CardContent className="space-y-2">
                {workspace?.active_test_attempt ? (
                  <Link
                    href={`/courses/${courseId}/tests/${workspace.active_test_attempt.id}`}
                    className={buttonVariants({ className: "w-full" })}
                  >
                    <Play />
                    Continue {formatTestKindLabel(workspace.active_test_attempt.kind)}
                  </Link>
                ) : null}
                <Button
                  className="w-full"
                  disabled={!workspace?.action_flags.can_start_entrance || startingTest}
                  onClick={() => {
                    void startCourseTest("entrance", "start-entrance");
                  }}
                >
                  <Sparkles />
                  <InlineLoadingLabel
                    loading={startingTest && pendingStartAction === "start-entrance"}
                    idleText="Start entrance"
                    loadingText="Starting entrance"
                  />
                </Button>
                <Button
                  className="w-full"
                  variant="outline"
                  disabled={!workspace?.action_flags.can_start_practice || startingTest}
                  onClick={() => {
                    void startCourseTest("general", "start-practice");
                  }}
                >
                  <TestTube2 />
                  <InlineLoadingLabel
                    loading={startingTest && pendingStartAction === "start-practice"}
                    idleText="Start practice"
                    loadingText="Starting practice"
                  />
                </Button>
                <Button
                  className="w-full"
                  variant="outline"
                  disabled={!workspace?.action_flags.can_start_exam || startingTest}
                  onClick={() => {
                    void startCourseTest("exam", "start-exam");
                  }}
                >
                  <ChartLine />
                  <InlineLoadingLabel
                    loading={startingTest && pendingStartAction === "start-exam"}
                    idleText="Start exam"
                    loadingText="Starting exam"
                  />
                </Button>
                <Button
                  className="w-full"
                  variant="outline"
                  disabled={!workspace?.action_flags.can_start_mistakes || startingTest}
                  onClick={() => {
                    void startCourseTest("mistakes", "start-mistakes");
                  }}
                >
                  <Radar />
                  <InlineLoadingLabel
                    loading={startingTest && pendingStartAction === "start-mistakes"}
                    idleText="Mistakes practice"
                    loadingText="Starting mistakes"
                  />
                </Button>
                <Link
                  href={`/courses/${courseId}/tests/history`}
                  className={buttonVariants({ className: "w-full", variant: "outline" })}
                >
                  <History />
                  Open full test history
                </Link>
              </CardContent>
            </Card>

            <Card>
              <CardHeader>
                <p className="section-kicker">Problem type details</p>
                <CardTitle>{focusedWorkspaceNode?.name ?? "Select a problem type"}</CardTitle>
              </CardHeader>
              <CardContent className="space-y-2">
                {focusedWorkspaceNode ? (
                  <>
                    <div className="rounded-[1rem] border border-border/70 bg-background/76 px-3 py-2 text-sm text-muted-foreground">
                      Mastery: {focusedWorkspaceNode.mastery_state}
                      {focusedWorkspaceNode.is_frontier ? " • Frontier" : ""}
                    </div>
                    <Button
                      className="w-full"
                      variant="outline"
                      disabled={!focusedWorkspaceNode.lecture_id}
                      onClick={() => {
                        if (focusedWorkspaceNode.lecture_id) {
                          router.push(`/courses/${courseId}/lectures/${focusedWorkspaceNode.lecture_id}`);
                        }
                      }}
                    >
                      <BookOpenCheck />
                      Open lecture
                    </Button>
                  </>
                ) : (
                  <p className="text-sm text-muted-foreground">
                    Select a graph problem type to open the lecture.
                  </p>
                )}
              </CardContent>
            </Card>

            <Card>
              <CardHeader>
                <p className="section-kicker">Current state</p>
                <CardTitle>Mastery summary</CardTitle>
              </CardHeader>
              <CardContent className="space-y-2">
                <div className="rounded-[1rem] border border-border/70 bg-background/76 px-3 py-2 text-sm text-muted-foreground">
                  Learned: {statusCounts.learned} • Ready: {statusCounts.ready} • Locked: {statusCounts.locked}
                </div>
                <div className="rounded-[1rem] border border-border/70 bg-background/76 px-3 py-2 text-sm text-muted-foreground">
                  Frontier: {statusCounts.frontier} • Failed: {statusCounts.failed}
                </div>
                {latestAssessment ? (
                  <div className="rounded-[1rem] border border-border/70 bg-background/76 px-3 py-2 text-sm text-muted-foreground">
                    Review status: {latestAssessment.review_status} • Confidence: {formatProbabilityAsPercentage(latestAssessment.state_confidence)}
                  </div>
                ) : null}
              </CardContent>
            </Card>
          </div>
        </div>
      </div>
    </div>
  );
}
