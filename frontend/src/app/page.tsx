"use client";

import { useCallback, useEffect, useState } from "react";
import type { CSSProperties, FormEvent } from "react";
import {
  Background,
  Controls,
  MiniMap,
  type NodeTypes,
  Position,
  ReactFlow,
  useEdgesState,
  useNodesState,
} from "@xyflow/react";
import type { Edge, Node } from "@xyflow/react";
import "@xyflow/react/dist/style.css";
import dagre from "dagre";
import {
  BarChart3,
  BookOpenCheck,
  BrainCircuit,
  LogOut,
  MoonStar,
  RefreshCw,
  Sparkles,
  SunMedium,
  Waypoints,
} from "lucide-react";
import EntranceTest from "@/components/EntranceTest";
import MathFlowNode, { type MathFlowNodeData } from "@/components/MathFlowNode";
import MathText from "@/components/MathText";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";

const HOME_LOG_SCOPE = "[Home]";
const AUTH_TOKEN_STORAGE_KEY = "auth_token";
const APP_THEME_STORAGE_KEY = "amls_theme";
const KNOWLEDGE_NODE_WIDTH = 232;
const KNOWLEDGE_NODE_HEIGHT = 114;

const knowledgeGraphLayout = new dagre.graphlib.Graph().setDefaultEdgeLabel(() => ({}));

const knowledgeGraphNodeTypes = {
  mathNode: MathFlowNode,
} satisfies NodeTypes;

const TAB_ITEMS = [
  {
    id: "graph",
    label: "Knowledge Graph",
    signal: "Graph view",
    description: "Inspect the dependency map of problem types and refresh it from the backend.",
  },
  {
    id: "entrance",
    label: "Entrance Test",
    signal: "Diagnostic view",
    description: "Run the adaptive entrance assessment and review the projected graph state.",
  },
] as const;

const AUTH_HIGHLIGHTS = [
  {
    label: "Adaptive diagnostics",
    value: "The entrance test calibrates each learner before the first study step.",
  },
  {
    label: "Graph-based mastery",
    value: "Every result is projected back onto the problem-type graph for a clear overview.",
  },
  {
    label: "Math-ready content",
    value: "Tasks, choices, and graph labels can render LaTeX through MathJax.",
  },
] as const;

const DEMO_BENEFITS = [
  {
    label: "Personalized start",
    value: "New users begin with a short diagnostic instead of a fixed learning path.",
  },
  {
    label: "Visual transparency",
    value: "The demo makes prerequisite structure and readiness status easy to inspect.",
  },
  {
    label: "Teacher-friendly output",
    value: "Topic summaries help explain what was learned, what is ready, and what is still locked.",
  },
] as const;

type AppTheme = "dark" | "light";
type ActiveTab = (typeof TAB_ITEMS)[number]["id"];
type AuthMode = "login" | "register";

interface RawGraphNode {
  id: string;
  name: string;
  prerequisite_ids: string[];
  children?: RawGraphNode[];
}

interface GraphDataResponse {
  roots: RawGraphNode[];
}

interface KnowledgeGraphNodeData extends MathFlowNodeData {
  label: string;
}

interface KnowledgeGraphLayoutResult {
  nodes: Node<KnowledgeGraphNodeData>[];
  edges: Edge[];
}

interface ThemeToggleButtonProps {
  theme: AppTheme;
  onToggle: () => void;
  testId?: string;
}


function applyAppTheme(theme: AppTheme): void {
  const rootElement = document.documentElement;

  rootElement.classList.remove("dark", "light");
  rootElement.classList.add(theme);
  rootElement.style.colorScheme = theme;
  rootElement.dataset.theme = theme;
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

  if (typeof responsePayload.error === "string") {
    return responsePayload.error;
  }

  if (Array.isArray(responsePayload.detail) && responsePayload.detail.length > 0) {
    const firstDetail = responsePayload.detail[0];

    if (
      typeof firstDetail === "object"
      && firstDetail !== null
      && "msg" in firstDetail
      && typeof firstDetail.msg === "string"
    ) {
      return firstDetail.msg;
    }

    if (typeof firstDetail === "string") {
      return firstDetail;
    }
  }

  return fallbackMessage;
}


function buildKnowledgeGraphNodeStyle(): CSSProperties {
  return {
    width: KNOWLEDGE_NODE_WIDTH,
    height: KNOWLEDGE_NODE_HEIGHT,
    border: "none",
    borderRadius: 24,
    background: "transparent",
    padding: 0,
  };
}


function layoutKnowledgeGraph(
  nodes: Node<KnowledgeGraphNodeData>[],
  edges: Edge[],
): KnowledgeGraphLayoutResult {
  knowledgeGraphLayout.setGraph({
    rankdir: "TB",
    nodesep: 40,
    ranksep: 78,
    marginx: 18,
    marginy: 18,
  });

  nodes.forEach((node) => {
    knowledgeGraphLayout.setNode(node.id, {
      width: KNOWLEDGE_NODE_WIDTH,
      height: KNOWLEDGE_NODE_HEIGHT,
    });
  });

  edges.forEach((edge) => {
    knowledgeGraphLayout.setEdge(edge.source, edge.target);
  });

  dagre.layout(knowledgeGraphLayout);

  return {
    nodes: nodes.map((node) => {
      const positionedNode = knowledgeGraphLayout.node(node.id);

      return {
        ...node,
        targetPosition: Position.Top,
        sourcePosition: Position.Bottom,
        position: {
          x: positionedNode.x - KNOWLEDGE_NODE_WIDTH / 2,
          y: positionedNode.y - KNOWLEDGE_NODE_HEIGHT / 2,
        },
      };
    }),
    edges,
  };
}


function buildKnowledgeGraphElements(
  graphData: GraphDataResponse,
): KnowledgeGraphLayoutResult {
  const nodes: Node<KnowledgeGraphNodeData>[] = [];
  const edges: Edge[] = [];
  const seenNodeIds = new Set<string>();

  const visitNode = (graphNode: RawGraphNode): void => {
    if (!seenNodeIds.has(graphNode.id)) {
      const prerequisiteCount = graphNode.prerequisite_ids.length;
      const childCount = graphNode.children?.length ?? 0;

      nodes.push({
        id: graphNode.id,
        position: { x: 0, y: 0 },
        data: {
          label: graphNode.name,
          badge: prerequisiteCount === 0 ? "Starting concept" : `${prerequisiteCount} prerequisite${prerequisiteCount === 1 ? "" : "s"}`,
          subtitle: childCount === 0 ? "Leaf concept" : `${childCount} follow-up step${childCount === 1 ? "" : "s"}`,
          tone: "default",
        },
        type: "mathNode",
        style: buildKnowledgeGraphNodeStyle(),
      });
      seenNodeIds.add(graphNode.id);
    }

    graphNode.prerequisite_ids.forEach((prerequisiteId) => {
      edges.push({
        id: `knowledge-graph-edge-${prerequisiteId}-${graphNode.id}`,
        source: prerequisiteId,
        target: graphNode.id,
        type: "smoothstep",
        animated: true,
        style: {
          stroke: "var(--graph-edge)",
          strokeWidth: 1.5,
        },
      });
    });

    graphNode.children?.forEach(visitNode);
  };

  graphData.roots.forEach(visitNode);

  return layoutKnowledgeGraph(nodes, edges);
}


function ThemeToggleButton({
  theme,
  onToggle,
  testId,
}: ThemeToggleButtonProps) {
  const nextThemeLabel = theme === "dark" ? "Switch to light theme" : "Switch to dark theme";

  return (
    <Button
      variant="outline"
      size="sm"
      onClick={onToggle}
      data-testid={testId}
      aria-label={nextThemeLabel}
    >
      {theme === "dark" ? <SunMedium /> : <MoonStar />}
      {theme === "dark" ? "Light theme" : "Dark theme"}
    </Button>
  );
}


export default function Home() {
  const [token, setToken] = useState<string | null>(null);
  const [theme, setTheme] = useState<AppTheme>("light");
  const [preferencesLoaded, setPreferencesLoaded] = useState(false);
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [firstName, setFirstName] = useState("");
  const [lastName, setLastName] = useState("");
  const [authError, setAuthError] = useState<string | null>(null);
  const [graphError, setGraphError] = useState<string | null>(null);
  const [isAuthSubmitting, setIsAuthSubmitting] = useState(false);
  const [isGraphLoading, setIsGraphLoading] = useState(false);
  const [activeTab, setActiveTab] = useState<ActiveTab>("graph");
  const [authMode, setAuthMode] = useState<AuthMode>("login");

  const [nodes, setNodes, onNodesChange] = useNodesState<Node<KnowledgeGraphNodeData>>([]);
  const [edges, setEdges, onEdgesChange] = useEdgesState<Edge>([]);


  useEffect(() => {
    const savedToken = window.localStorage.getItem(AUTH_TOKEN_STORAGE_KEY);
    const savedTheme = window.localStorage.getItem(APP_THEME_STORAGE_KEY);
    const nextTheme: AppTheme = savedTheme === "dark" ? "dark" : "light";

    if (savedToken) {
      setToken(savedToken);
    }

    setTheme(nextTheme);
    applyAppTheme(nextTheme);
    setPreferencesLoaded(true);

    console.log(`${HOME_LOG_SCOPE} Loaded client preferences`, {
      hasToken: Boolean(savedToken),
      theme: nextTheme,
    });
  }, []);


  useEffect(() => {
    if (!preferencesLoaded) {
      return;
    }

    applyAppTheme(theme);
    window.localStorage.setItem(APP_THEME_STORAGE_KEY, theme);

    console.log(`${HOME_LOG_SCOPE} Applied theme`, {
      theme,
    });
  }, [preferencesLoaded, theme]);


  const fetchGraphData = useCallback(async (authToken: string) => {
    const startedAt = Date.now();

    try {
      setIsGraphLoading(true);
      setGraphError(null);

      const response = await fetch("/api/graph", {
        headers: {
          Authorization: `Bearer ${authToken}`,
        },
      });

      const payload = await response.json().catch(() => null);

      if (!response.ok) {
        if (response.status === 401) {
          setToken(null);
          window.localStorage.removeItem(AUTH_TOKEN_STORAGE_KEY);
        }

        throw new Error(getResponseErrorMessage(payload, "Failed to fetch graph data"));
      }

      const graphData = payload as GraphDataResponse;
      const graphElements = buildKnowledgeGraphElements(graphData);

      console.log(`${HOME_LOG_SCOPE} Graph data synced`, {
        durationInMilliseconds: Date.now() - startedAt,
        edgeCount: graphElements.edges.length,
        nodeCount: graphElements.nodes.length,
        rootCount: graphData.roots.length,
      });

      setNodes(graphElements.nodes);
      setEdges(graphElements.edges);
    } catch (error: unknown) {
      const message = error instanceof Error ? error.message : "Unknown error occurred";

      console.error(`${HOME_LOG_SCOPE} Graph sync failed`, {
        durationInMilliseconds: Date.now() - startedAt,
        message,
      });

      setGraphError(message);
    } finally {
      setIsGraphLoading(false);
    }
  }, [setEdges, setNodes]);


  useEffect(() => {
    if (token && activeTab === "graph") {
      void fetchGraphData(token);
    }
  }, [activeTab, fetchGraphData, token]);


  const handleThemeToggle = useCallback(() => {
    setTheme((currentTheme) => currentTheme === "dark" ? "light" : "dark");
  }, []);


  const handleLogin = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();

    console.log(`${HOME_LOG_SCOPE} Login attempt`, {
      email,
    });

    try {
      setIsAuthSubmitting(true);
      setAuthError(null);

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

      const authPayload = payload as {
        access_token?: string;
      };

      if (!authPayload.access_token) {
        throw new Error("No access token returned");
      }

      setToken(authPayload.access_token);
      window.localStorage.setItem(AUTH_TOKEN_STORAGE_KEY, authPayload.access_token);

      console.log(`${HOME_LOG_SCOPE} Login successful`, {
        email,
      });
    } catch (error: unknown) {
      const message = error instanceof Error ? error.message : "Login failed";

      console.error(`${HOME_LOG_SCOPE} Login failed`, {
        email,
        message,
      });

      setAuthError(message);
    } finally {
      setIsAuthSubmitting(false);
    }
  };


  const handleRegister = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();

    console.log(`${HOME_LOG_SCOPE} Registration attempt`, {
      email,
      firstName,
      lastName,
    });

    try {
      setIsAuthSubmitting(true);
      setAuthError(null);

      const registerResponse = await fetch("/api/auth/register", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          email,
          password,
          first_name: firstName,
          last_name: lastName,
          avatar_url: null,
        }),
      });

      const registerPayload = await registerResponse.json().catch(() => null);

      if (!registerResponse.ok) {
        throw new Error(getResponseErrorMessage(registerPayload, "Registration failed"));
      }

      const loginResponse = await fetch("/api/auth", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          email,
          password,
        }),
      });

      const loginPayload = await loginResponse.json().catch(() => null);

      if (!loginResponse.ok) {
        setAuthMode("login");
        throw new Error("Registration successful, please login.");
      }

      const authPayload = loginPayload as {
        access_token?: string;
      };

      if (!authPayload.access_token) {
        setAuthMode("login");
        throw new Error("Registration successful, please login.");
      }

      setToken(authPayload.access_token);
      window.localStorage.setItem(AUTH_TOKEN_STORAGE_KEY, authPayload.access_token);

      console.log(`${HOME_LOG_SCOPE} Registration successful`, {
        email,
      });
    } catch (error: unknown) {
      const message = error instanceof Error ? error.message : "Registration failed";

      console.error(`${HOME_LOG_SCOPE} Registration failed`, {
        email,
        message,
      });

      setAuthError(message);
    } finally {
      setIsAuthSubmitting(false);
    }
  };


  const handleLogout = useCallback(() => {
    setToken(null);
    setGraphError(null);
    setAuthError(null);
    setNodes([]);
    setEdges([]);
    window.localStorage.removeItem(AUTH_TOKEN_STORAGE_KEY);

    console.log(`${HOME_LOG_SCOPE} Session cleared`);
  }, [setEdges, setNodes]);


  const activeTabItem = TAB_ITEMS.find((item) => item.id === activeTab) ?? TAB_ITEMS[0];

  const graphTelemetryItems = [
    {
      label: "Nodes",
      value: String(nodes.length),
      icon: Waypoints,
    },
    {
      label: "Edges",
      value: String(edges.length),
      icon: BarChart3,
    },
    {
      label: "Status",
      value: graphError ? "Attention" : isGraphLoading ? "Refreshing" : "Ready",
      icon: BrainCircuit,
    },
  ] as const;

  if (!token) {
    return (
      <div className="min-h-screen px-4 py-6 lg:px-8 lg:py-8">
        <div className="mx-auto flex w-full max-w-7xl flex-col gap-6">
          <header className="flex items-center justify-between gap-4">
            <div>
              <p className="brand-mark leading-none">AMLS</p>
              <p className="brand-caption mt-1">Adaptive learning demo</p>
            </div>
            <ThemeToggleButton
              theme={theme}
              onToggle={handleThemeToggle}
              testId="app-theme-toggle"
            />
          </header>

          <section className="hero-mesh rounded-[2.4rem]">
            <div className="grid lg:grid-cols-[1.08fr_0.92fr]">
              <div className="panel-divider border-b border-border/70 px-6 py-8 lg:border-b-0 lg:border-r lg:px-10 lg:py-10">
                <div className="space-y-5">
                  <p className="section-kicker">Graph-based adaptive learning</p>
                  <div className="space-y-4">
                    <h1 className="section-title text-4xl text-foreground sm:text-5xl lg:text-[4.25rem]">
                      Adaptive Math Learning System
                    </h1>
                    <p className="max-w-2xl text-base leading-8 text-muted-foreground">
                      A clean demo interface for graph-driven diagnostics, entrance testing, and
                      personalized learning-state visualization.
                    </p>
                  </div>

                  <div className="flex flex-wrap gap-2">
                    <span className="rounded-full border border-primary/20 bg-primary/10 px-4 py-2 text-sm font-semibold text-primary">
                      Entrance diagnostics
                    </span>
                    <span className="rounded-full border border-border bg-background/78 px-4 py-2 text-sm font-semibold text-foreground">
                      Knowledge graph
                    </span>
                    <span className="rounded-full border border-border bg-background/78 px-4 py-2 text-sm font-semibold text-foreground">
                      MathJax rendering
                    </span>
                  </div>

                  <div className="grid gap-3 md:grid-cols-3">
                    {AUTH_HIGHLIGHTS.map((highlight) => (
                      <div
                        key={highlight.label}
                        className="rounded-[1.5rem] border border-border/70 bg-background/74 p-4"
                      >
                        <p className="text-sm font-semibold text-foreground">{highlight.label}</p>
                        <p className="mt-3 text-sm leading-6 text-muted-foreground">
                          {highlight.value}
                        </p>
                      </div>
                    ))}
                  </div>

                  <div className="rounded-[1.7rem] border border-primary/18 bg-background/76 p-5">
                    <div className="flex items-center gap-2 text-primary">
                      <Sparkles className="size-4" />
                      <p className="text-sm font-semibold">Math-ready preview</p>
                    </div>
                    <MathText
                      content={"Supports formulas such as $\\sqrt{x^2 + y^2} = r$, $\\int_a^b f(x)\\,dx$, and $a_n = a_1 q^{n-1}$ directly in tasks and graph labels."}
                      className="mt-3 text-sm leading-7 text-muted-foreground"
                    />
                  </div>
                </div>
              </div>

              <div className="px-6 py-8 lg:px-10 lg:py-10">
                <div className="mx-auto flex h-full w-full max-w-md flex-col justify-center space-y-6">
                  <div className="space-y-3">
                    <p className="section-kicker">
                      {authMode === "login" ? "Student sign in" : "Create a demo account"}
                    </p>
                    <h2 className="section-title text-3xl text-foreground">
                      {authMode === "login" ? "Open the demo workspace" : "Start a new learner profile"}
                    </h2>
                    <p className="text-sm leading-7 text-muted-foreground">
                      {authMode === "login"
                        ? "Use an existing student account to explore the knowledge graph and the adaptive entrance test."
                        : "Registration creates a student profile and keeps the entrance-test flow ready for the first session."}
                    </p>
                  </div>

                  {authMode === "login" ? (
                    <form onSubmit={handleLogin} className="space-y-5">
                      <div className="space-y-2">
                        <Label htmlFor="email">Email</Label>
                        <Input
                          id="email"
                          type="email"
                          placeholder="student@example.com"
                          value={email}
                          onChange={(event) => setEmail(event.target.value)}
                          required
                        />
                      </div>
                      <div className="space-y-2">
                        <Label htmlFor="password">Password</Label>
                        <Input
                          id="password"
                          type="password"
                          placeholder="Enter your password"
                          value={password}
                          onChange={(event) => setPassword(event.target.value)}
                          required
                        />
                      </div>
                      {authError ? (
                        <div className="rounded-[1.3rem] border border-destructive/25 bg-destructive/10 px-4 py-3 text-sm text-destructive">
                          {authError}
                        </div>
                      ) : null}
                      <Button type="submit" className="w-full" disabled={isAuthSubmitting}>
                        {isAuthSubmitting ? "Signing in" : "Sign in"}
                      </Button>
                      <p className="text-sm leading-7 text-muted-foreground">
                        Need a demo learner?{" "}
                        <button
                          type="button"
                          className="font-semibold text-primary"
                          onClick={() => {
                            setAuthMode("register");
                            setAuthError(null);
                          }}
                        >
                          Create an account
                        </button>
                      </p>
                    </form>
                  ) : (
                    <form onSubmit={handleRegister} className="space-y-5">
                      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
                        <div className="space-y-2">
                          <Label htmlFor="firstName">First name</Label>
                          <Input
                            id="firstName"
                            placeholder="Ada"
                            value={firstName}
                            onChange={(event) => setFirstName(event.target.value)}
                            required
                          />
                        </div>
                        <div className="space-y-2">
                          <Label htmlFor="lastName">Last name</Label>
                          <Input
                            id="lastName"
                            placeholder="Lovelace"
                            value={lastName}
                            onChange={(event) => setLastName(event.target.value)}
                            required
                          />
                        </div>
                      </div>
                      <div className="space-y-2">
                        <Label htmlFor="registerEmail">Email</Label>
                        <Input
                          id="registerEmail"
                          type="email"
                          placeholder="student@example.com"
                          value={email}
                          onChange={(event) => setEmail(event.target.value)}
                          required
                        />
                      </div>
                      <div className="space-y-2">
                        <Label htmlFor="registerPassword">Password</Label>
                        <Input
                          id="registerPassword"
                          type="password"
                          placeholder="Create a password"
                          value={password}
                          onChange={(event) => setPassword(event.target.value)}
                          required
                        />
                      </div>
                      {authError ? (
                        <div className="rounded-[1.3rem] border border-destructive/25 bg-destructive/10 px-4 py-3 text-sm text-destructive">
                          {authError}
                        </div>
                      ) : null}
                      <Button type="submit" className="w-full" disabled={isAuthSubmitting}>
                        {isAuthSubmitting ? "Creating account" : "Create account"}
                      </Button>
                      <p className="text-sm leading-7 text-muted-foreground">
                        Already have a learner profile?{" "}
                        <button
                          type="button"
                          className="font-semibold text-primary"
                          onClick={() => {
                            setAuthMode("login");
                            setAuthError(null);
                          }}
                        >
                          Sign in
                        </button>
                      </p>
                    </form>
                  )}
                </div>
              </div>
            </div>
          </section>

          <section className="grid gap-4 md:grid-cols-3">
            {DEMO_BENEFITS.map((benefit) => (
              <div
                key={benefit.label}
                className="app-surface rounded-[1.8rem] px-5 py-5"
              >
                <p className="text-base font-semibold text-foreground">{benefit.label}</p>
                <p className="mt-3 text-sm leading-7 text-muted-foreground">{benefit.value}</p>
              </div>
            ))}
          </section>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen px-4 py-4 lg:px-6 lg:py-6">
      <div className="mx-auto flex max-w-[1500px] flex-col gap-5">
        <header className="app-surface rounded-[2.2rem] px-6 py-5 lg:px-7">
          <div className="flex flex-col gap-5 xl:flex-row xl:items-center xl:justify-between">
            <div className="space-y-4">
              <div className="flex flex-wrap items-center gap-4">
                <div>
                  <p className="brand-mark text-[2.5rem] leading-none">AMLS</p>
                  <p className="brand-caption mt-1">Adaptive learning demo</p>
                </div>
                <div
                  data-testid="shell-status"
                  className="rounded-full border border-primary/18 bg-primary/10 px-4 py-2 text-sm font-semibold text-primary"
                >
                  {activeTabItem.signal}
                </div>
              </div>
              <div className="space-y-2">
                <p className="section-kicker">{activeTabItem.signal}</p>
                <h1 className="section-title text-3xl text-foreground md:text-[3rem]">
                  Adaptive Math Learning System
                </h1>
                <p className="max-w-3xl text-sm leading-7 text-muted-foreground">
                  Demo access to the knowledge graph, adaptive entrance test, and projected learner
                  state.
                </p>
              </div>
            </div>

            <div className="flex flex-wrap items-center gap-3">
              <ThemeToggleButton
                theme={theme}
                onToggle={handleThemeToggle}
                testId="app-theme-toggle"
              />
              <Button variant="outline" size="sm" onClick={handleLogout}>
                <LogOut />
                Logout
              </Button>
            </div>
          </div>

          <div className="mt-6 flex flex-wrap gap-2 rounded-[1.5rem] bg-muted/72 p-1.5">
            {TAB_ITEMS.map((tabItem) => (
              <Button
                key={tabItem.id}
                variant={activeTab === tabItem.id ? "default" : "ghost"}
                size="sm"
                onClick={() => setActiveTab(tabItem.id)}
              >
                {tabItem.label}
              </Button>
            ))}
          </div>
        </header>

        {activeTab === "graph" ? (
          <div className="grid gap-5 xl:grid-cols-[0.92fr_1.08fr]">
            <section className="app-surface rounded-[2rem] px-6 py-6">
              <div className="flex h-full flex-col gap-6">
                <div className="space-y-3">
                  <p className="section-kicker">Live dependency map</p>
                  <h2 className="section-title text-3xl text-foreground">
                    Knowledge graph workspace
                  </h2>
                  <p className="text-sm leading-7 text-muted-foreground">
                    Refresh the current problem-type graph, inspect prerequisite chains, and switch
                    to the entrance diagnostic when you want to see the personalized projection.
                  </p>
                </div>

                <div className="grid gap-3 sm:grid-cols-3">
                  {graphTelemetryItems.map((telemetryItem) => {
                    const Icon = telemetryItem.icon;

                    return (
                      <div
                        key={telemetryItem.label}
                        className="rounded-[1.5rem] border border-border/70 bg-background/72 p-4"
                      >
                        <div className="flex items-center gap-2 text-primary">
                          <Icon className="size-4" />
                          <p className="text-sm font-semibold">{telemetryItem.label}</p>
                        </div>
                        <p className="mt-3 text-3xl font-semibold text-foreground">
                          {telemetryItem.value}
                        </p>
                      </div>
                    );
                  })}
                </div>

                <div className="rounded-[1.6rem] border border-border/70 bg-background/72 p-5">
                  <div className="flex items-center gap-2 text-primary">
                    <BookOpenCheck className="size-4" />
                    <p className="text-sm font-semibold">Math-aware labels</p>
                  </div>
                  <MathText
                    content={"Graph nodes can render notation like $f(x)=x^2-4x+3$ or $\\log_a b$ when the backend provides it in the problem-type name."}
                    className="mt-3 text-sm leading-7 text-muted-foreground"
                  />
                </div>

                <div className="mt-auto">
                  <Button
                    variant="outline"
                    onClick={() => {
                      void fetchGraphData(token);
                    }}
                    disabled={isGraphLoading}
                  >
                    <RefreshCw className={isGraphLoading ? "animate-spin" : undefined} />
                    {isGraphLoading ? "Refreshing graph" : "Refresh graph"}
                  </Button>
                </div>
              </div>
            </section>

            <section
              data-testid="knowledge-graph-view"
              className="graph-stage graph-flow relative min-h-[640px] rounded-[2rem] p-3 sm:p-4"
            >
              <div className="absolute left-4 top-4 z-10 flex flex-wrap gap-2">
                <span className="rounded-full border border-primary/18 bg-primary/10 px-4 py-2 text-sm font-semibold text-primary">
                  Knowledge graph
                </span>
                <span className="rounded-full border border-border/70 bg-background/80 px-4 py-2 text-sm font-semibold text-foreground">
                  {graphError ? "Needs attention" : isGraphLoading ? "Refreshing" : "Up to date"}
                </span>
              </div>

              {graphError && nodes.length === 0 ? (
                <div className="flex h-full items-center justify-center px-6 text-center">
                  <div className="max-w-xl space-y-4">
                    <p className="section-title text-2xl text-foreground">Graph sync error</p>
                    <p className="text-sm leading-7 text-muted-foreground">{graphError}</p>
                    <div className="flex justify-center">
                      <Button
                        variant="outline"
                        onClick={() => {
                          void fetchGraphData(token);
                        }}
                      >
                        Retry sync
                      </Button>
                    </div>
                  </div>
                </div>
              ) : isGraphLoading && nodes.length === 0 ? (
                <div className="flex h-full items-center justify-center px-6 text-center">
                  <div className="space-y-3">
                    <p className="section-title text-2xl text-foreground">Loading graph</p>
                    <p className="text-sm leading-7 text-muted-foreground">
                      Fetching the current dependency structure from the backend.
                    </p>
                  </div>
                </div>
              ) : (
                <ReactFlow
                  nodes={nodes}
                  edges={edges}
                  nodeTypes={knowledgeGraphNodeTypes}
                  onNodesChange={onNodesChange}
                  onEdgesChange={onEdgesChange}
                  fitView
                >
                  <Background color="var(--surface-grid)" gap={30} size={1} />
                  <MiniMap
                    pannable
                    zoomable
                    nodeColor="var(--primary)"
                    maskColor="transparent"
                    style={{
                      background: "var(--card)",
                      border: "1px solid var(--border)",
                    }}
                  />
                  <Controls />
                </ReactFlow>
              )}
            </section>
          </div>
        ) : (
          <section
            data-testid="entrance-tab-panel"
            className="app-surface rounded-[2rem] p-1 sm:p-2"
          >
            <EntranceTest token={token} />
          </section>
        )}
      </div>
    </div>
  );
}
