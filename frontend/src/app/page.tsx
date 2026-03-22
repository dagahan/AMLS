"use client";

import { useState, useEffect, useCallback } from "react";
import { ReactFlow, Background, Controls, Node, Edge, useNodesState, useEdgesState, Position } from "@xyflow/react";
import "@xyflow/react/dist/style.css";
import dagre from "dagre";
import { Card, CardHeader, CardTitle, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";

import EntranceTest from "@/components/EntranceTest";

type RawGraphNode = {
  id: string;
  name: string;
  prerequisite_ids: string[];
  children?: RawGraphNode[];
};

type GraphDataResponse = {
  roots: RawGraphNode[];
};

const dagreGraph = new dagre.graphlib.Graph().setDefaultEdgeLabel(() => ({}));

const nodeWidth = 250;
const nodeHeight = 50;

const getLayoutedElements = (nodes: Node[], edges: Edge[], direction = "TB") => {
  const isHorizontal = direction === "LR";
  dagreGraph.setGraph({ rankdir: direction });

  nodes.forEach((node) => {
    dagreGraph.setNode(node.id, { width: nodeWidth, height: nodeHeight });
  });

  edges.forEach((edge) => {
    dagreGraph.setEdge(edge.source, edge.target);
  });

  dagre.layout(dagreGraph);

  const newNodes = nodes.map((node) => {
    const nodeWithPosition = dagreGraph.node(node.id);
    const newNode = {
      ...node,
      targetPosition: isHorizontal ? Position.Left : Position.Top,
      sourcePosition: isHorizontal ? Position.Right : Position.Bottom,
      position: {
        x: nodeWithPosition.x - nodeWidth / 2,
        y: nodeWithPosition.y - nodeHeight / 2,
      },
    };

    return newNode;
  });

  return { nodes: newNodes, edges };
};

export default function Home() {
  const [token, setToken] = useState<string | null>(null);
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [firstName, setFirstName] = useState("");
  const [lastName, setLastName] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [activeTab, setActiveTab] = useState<"graph" | "entrance">("graph");
  const [authMode, setAuthMode] = useState<"login" | "register">("login");

  const [nodes, setNodes, onNodesChange] = useNodesState<Node>([]);
  const [edges, setEdges, onEdgesChange] = useEdgesState<Edge>([]);

  useEffect(() => {
    const savedToken = localStorage.getItem("auth_token");
    if (savedToken) {
      setToken(savedToken);
    }
  }, []);

  const fetchGraphData = useCallback(async (authToken: string) => {
    try {
      setLoading(true);
      setError(null);
      const res = await fetch("/api/graph", {
        headers: {
          Authorization: `Bearer ${authToken}`,
        },
      });

      if (!res.ok) {
        if (res.status === 401) {
          setToken(null);
          localStorage.removeItem("auth_token");
        }
        const data = await res.json().catch(() => ({}));
        throw new Error(data.detail || data.error || "Failed to fetch graph data");
      }

      const data: GraphDataResponse = await res.json();

      const initialNodes: Node[] = [];
      const initialEdges: Edge[] = [];

      const processNode = (node: RawGraphNode) => {
        if (!initialNodes.find((n) => n.id === node.id)) {
          initialNodes.push({
            id: node.id,
            position: { x: 0, y: 0 },
            data: { label: node.name },
            style: {
              borderRadius: "50%",
              width: 150,
              height: 150,
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
              textAlign: "center",
              padding: "10px",
              backgroundColor: "#fff",
              border: "2px solid #333",
              fontSize: "12px",
            },
          });
        }

        if (node.prerequisite_ids) {
          node.prerequisite_ids.forEach((reqId) => {
            initialEdges.push({
              id: `e-${reqId}-${node.id}`,
              source: reqId,
              target: node.id,
              type: "straight",
              animated: true,
            });
          });
        }

        if (node.children) {
          node.children.forEach(processNode);
        }
      };

      if (data.roots) {
        data.roots.forEach(processNode);
      }

      const { nodes: layoutedNodes, edges: layoutedEdges } = getLayoutedElements(
        initialNodes,
        initialEdges
      );

      setNodes(layoutedNodes);
      setEdges(layoutedEdges);
    } catch (err: unknown) {
      if (err instanceof Error) {
        setError(err.message);
      } else {
        setError("Unknown error occurred");
      }
    } finally {
      setLoading(false);
    }
  }, [setNodes, setEdges]);

  useEffect(() => {
    if (token && activeTab === "graph") {
      fetchGraphData(token);
    }
  }, [token, activeTab, fetchGraphData]);

  const handleLogin = async (e: React.FormEvent) => {
    e.preventDefault();
    console.log("Login attempt with:", email);
    setLoading(true);
    setError(null);
    try {
      const res = await fetch("/api/auth", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({ email, password }),
      });

      console.log("Login response status:", res.status);
      const data = await res.json().catch(() => ({}));

      if (!res.ok) {
        throw new Error(data.detail || data.error || "Invalid credentials");
      }

      if (data.access_token) {
        console.log("Login successful, token received");
        setToken(data.access_token);
        localStorage.setItem("auth_token", data.access_token);
      } else {
        throw new Error("No access token returned");
      }
    } catch (err: unknown) {
      console.error("Login error:", err);
      if (err instanceof Error) {
        setError(err.message);
      } else {
        setError("Login failed");
      }
    } finally {
      setLoading(false);
    }
  };

  const handleRegister = async (e: React.FormEvent) => {
    e.preventDefault();
    console.log("Registration attempt with:", email, firstName, lastName);
    setLoading(true);
    setError(null);
    try {
      const res = await fetch("/api/auth/register", {
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

      console.log("Registration response status:", res.status);
      const data = await res.json().catch(() => ({}));

      if (!res.ok) {
        const detail = data.detail;
        let errorMessage = "Registration failed";
        if (Array.isArray(detail)) {
          errorMessage = detail[0]?.msg || errorMessage;
        } else if (typeof detail === "string") {
          errorMessage = detail;
        } else if (data.error) {
          errorMessage = data.error;
        }
        throw new Error(errorMessage);
      }

      console.log("Registration successful, attempting auto-login...");
      // Automatically login after successful registration
      const loginRes = await fetch("/api/auth", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({ email, password }),
      });

      const loginData = await loginRes.json().catch(() => ({}));
      if (loginData.access_token) {
        console.log("Auto-login successful");
        setToken(loginData.access_token);
        localStorage.setItem("auth_token", loginData.access_token);
      } else {
        console.warn("Auto-login failed after registration");
        setAuthMode("login");
        setError("Registration successful, please login.");
      }
    } catch (err: unknown) {
      console.error("Registration error:", err);
      if (err instanceof Error) {
        setError(err.message);
      } else {
        setError("Registration failed");
      }
    } finally {
      setLoading(false);
    }
  };

  const handleLogout = () => {
    setToken(null);
    localStorage.removeItem("auth_token");
    setNodes([]);
    setEdges([]);
  };

  if (!token) {
    return (
      <div className="flex items-center justify-center min-h-screen bg-slate-50 p-4">
        <Card className="w-full max-w-[450px]">
          <CardHeader>
            <CardTitle>{authMode === "login" ? "Login to AMLS" : "Create your AMLS account"}</CardTitle>
          </CardHeader>
          <CardContent>
            {authMode === "login" ? (
              <form onSubmit={handleLogin} className="space-y-4">
                <div className="space-y-2">
                  <Label htmlFor="email">Email</Label>
                  <Input
                    id="email"
                    type="email"
                    placeholder="john@example.com"
                    value={email}
                    onChange={(e) => setEmail(e.target.value)}
                    required
                  />
                </div>
                <div className="space-y-2">
                  <Label htmlFor="password">Password</Label>
                  <Input
                    id="password"
                    type="password"
                    value={password}
                    onChange={(e) => setPassword(e.target.value)}
                    required
                  />
                </div>
                {error && <p className="text-red-500 text-sm font-medium">{error}</p>}
                <Button type="submit" className="w-full" disabled={loading}>
                  {loading ? "Logging in..." : "Login"}
                </Button>
                <div className="text-center mt-4">
                  <p className="text-sm text-slate-600">
                    Don't have an account?{" "}
                    <button
                      type="button"
                      className="text-primary font-bold hover:underline"
                      onClick={() => {
                        setAuthMode("register");
                        setError(null);
                      }}
                    >
                      Register
                    </button>
                  </p>
                </div>
              </form>
            ) : (
              <form onSubmit={handleRegister} className="space-y-4">
                <div className="grid grid-cols-2 gap-4">
                  <div className="space-y-2">
                    <Label htmlFor="firstName">First Name</Label>
                    <Input
                      id="firstName"
                      placeholder="John"
                      value={firstName}
                      onChange={(e) => setFirstName(e.target.value)}
                      required
                    />
                  </div>
                  <div className="space-y-2">
                    <Label htmlFor="lastName">Last Name</Label>
                    <Input
                      id="lastName"
                      placeholder="Doe"
                      value={lastName}
                      onChange={(e) => setLastName(e.target.value)}
                      required
                    />
                  </div>
                </div>
                <div className="space-y-2">
                  <Label htmlFor="email">Email</Label>
                  <Input
                    id="email"
                    type="email"
                    placeholder="john@example.com"
                    value={email}
                    onChange={(e) => setEmail(e.target.value)}
                    required
                  />
                </div>
                <div className="space-y-2">
                  <Label htmlFor="password">Password</Label>
                  <Input
                    id="password"
                    type="password"
                    value={password}
                    onChange={(e) => setPassword(e.target.value)}
                    required
                  />
                </div>
                {error && <p className="text-red-500 text-sm font-medium">{error}</p>}
                <Button type="submit" className="w-full" disabled={loading}>
                  {loading ? "Creating account..." : "Register"}
                </Button>
                <div className="text-center mt-4">
                  <p className="text-sm text-slate-600">
                    Already have an account?{" "}
                    <button
                      type="button"
                      className="text-primary font-bold hover:underline"
                      onClick={() => {
                        setAuthMode("login");
                        setError(null);
                      }}
                    >
                      Login
                    </button>
                  </p>
                </div>
              </form>
            )}
          </CardContent>
        </Card>
      </div>
    );
  }

  return (
    <div className="flex flex-col h-screen">
      <div className="flex items-center justify-between p-4 bg-white border-b">
        <h1 className="text-xl font-bold">Adaptive Math Learning System</h1>
        <div className="flex items-center space-x-4">
          <Button variant="destructive" onClick={handleLogout}>
            Logout
          </Button>
        </div>
      </div>
      
      <div className="flex-1 overflow-hidden flex flex-col">
        <div className="px-4 py-2 border-b bg-white flex space-x-2">
          <Button 
            variant={activeTab === "graph" ? "default" : "outline"} 
            size="sm"
            onClick={() => setActiveTab("graph")}
          >
            Knowledge Graph
          </Button>
          <Button 
            variant={activeTab === "entrance" ? "default" : "outline"} 
            size="sm"
            onClick={() => setActiveTab("entrance")}
          >
            Entrance Test
          </Button>
        </div>
        
        <div className="flex-1 overflow-hidden relative bg-slate-50">
          {activeTab === "graph" ? (
            loading && nodes.length === 0 ? (
              <div className="flex items-center justify-center h-full">Loading graph...</div>
            ) : error ? (
              <div className="flex items-center justify-center h-full text-red-500">{error}</div>
            ) : (
              <>
                <div className="absolute top-4 right-4 z-10">
                  <Button variant="outline" size="sm" onClick={() => fetchGraphData(token)} disabled={loading}>
                    Refresh Graph
                  </Button>
                </div>
                <ReactFlow
                  nodes={nodes}
                  edges={edges}
                  onNodesChange={onNodesChange}
                  onEdgesChange={onEdgesChange}
                  fitView
                >
                  <Background />
                  <Controls />
                </ReactFlow>
              </>
            )
          ) : (
            <div className="h-full overflow-auto">
              <EntranceTest token={token} />
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
