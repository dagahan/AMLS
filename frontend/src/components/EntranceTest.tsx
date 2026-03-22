"use client";

import { useState, useEffect, useCallback } from "react";
import { Card, CardHeader, CardTitle, CardContent, CardFooter } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import {
  EntranceTestSessionResponse,
  EntranceTestCurrentProblemResponse,
  EntranceTestAnswerResponse,
  EntranceTestResultResponse,
  ProblemResponse,
} from "@/lib/api-types";

interface EntranceTestProps {
  token: string;
}

export default function EntranceTest({ token }: EntranceTestProps) {
  const [session, setSession] = useState<EntranceTestSessionResponse | null>(null);
  const [currentProblem, setCurrentProblem] = useState<ProblemResponse | null>(null);
  const [result, setResult] = useState<EntranceTestResultResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [selectedAnswerId, setSelectedAnswerId] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  const fetchCurrentProblem = useCallback(async () => {
    const res = await fetch("/api/entrance-test/current-problem", {
      headers: { Authorization: `Bearer ${token}` },
    });
    if (res.ok) {
      const data: EntranceTestCurrentProblemResponse = await res.json();
      setCurrentProblem(data.problem);
    }
  }, [token]);

  const fetchResult = useCallback(async () => {
    const res = await fetch("/api/entrance-test/result", {
      headers: { Authorization: `Bearer ${token}` },
    });
    if (res.ok) {
      const data: EntranceTestResultResponse = await res.json();
      setResult(data);
    }
  }, [token]);

  const fetchSession = useCallback(async () => {
    try {
      setLoading(true);
      const res = await fetch("/api/entrance-test", {
        headers: { Authorization: `Bearer ${token}` },
      });
      if (!res.ok) throw new Error("Failed to fetch session");
      const data: EntranceTestSessionResponse = await res.json();
      setSession(data);

      if (data.status === "active") {
        await fetchCurrentProblem();
      } else if (data.status === "completed") {
        await fetchResult();
      }
    } catch (err: unknown) {
      if (err instanceof Error) {
        setError(err.message);
      } else {
        setError("An unknown error occurred");
      }
    } finally {
      setLoading(false);
    }
  }, [token, fetchCurrentProblem, fetchResult]);

  useEffect(() => {
    fetchSession();
  }, [fetchSession]);

  const handleStart = async () => {
    try {
      setLoading(true);
      const res = await fetch("/api/entrance-test/start", {
        method: "POST",
        headers: { Authorization: `Bearer ${token}` },
      });
      if (!res.ok) throw new Error("Failed to start test");
      const data: EntranceTestCurrentProblemResponse = await res.json();
      setSession(data.session);
      setCurrentProblem(data.problem);
    } catch (err: unknown) {
      if (err instanceof Error) {
        setError(err.message);
      } else {
        setError("Failed to start test");
      }
    } finally {
      setLoading(false);
    }
  };

  const handleSubmit = async () => {
    if (!selectedAnswerId || !currentProblem) return;
    try {
      setSubmitting(true);
      const res = await fetch("/api/entrance-test/answers", {
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
      if (!res.ok) throw new Error("Failed to submit answer");
      const data: EntranceTestAnswerResponse = await res.json();
      setSession(data.session);
      setCurrentProblem(data.next_problem);
      setSelectedAnswerId(null);

      if (data.session.status === "completed") {
        await fetchResult();
      }
    } catch (err: unknown) {
      if (err instanceof Error) {
        setError(err.message);
      } else {
        setError("Failed to submit answer");
      }
    } finally {
      setSubmitting(false);
    }
  };

  const handleComplete = async () => {
    try {
      setSubmitting(true);
      const res = await fetch("/api/entrance-test/complete", {
        method: "POST",
        headers: { Authorization: `Bearer ${token}` },
      });
      if (!res.ok) throw new Error("Failed to complete test");
      const data: EntranceTestSessionResponse = await res.json();
      setSession(data);
      await fetchResult();
    } catch (err: unknown) {
      if (err instanceof Error) {
        setError(err.message);
      } else {
        setError("Failed to complete test");
      }
    } finally {
      setSubmitting(false);
    }
  };

  if (loading) return <div>Loading Entrance Test...</div>;
  if (error) return <div className="text-red-500">{error}</div>;

  if (!session || session.status === "pending" || session.status === "skipped") {
    return (
      <div className="flex flex-col items-center justify-center p-8">
        <Card className="max-w-md w-full">
          <CardHeader>
            <CardTitle>Entrance Test</CardTitle>
          </CardHeader>
          <CardContent>
            <p>To personalize your learning path, we recommend taking a short entrance test.</p>
          </CardContent>
          <CardFooter>
            <Button onClick={handleStart} className="w-full">Start Entrance Test</Button>
          </CardFooter>
        </Card>
      </div>
    );
  }

  if (session.status === "active" && currentProblem) {
    return (
      <div className="flex flex-col items-center p-8">
        <Card className="max-w-2xl w-full">
          <CardHeader>
            <CardTitle>Entrance Test - Question</CardTitle>
          </CardHeader>
          <CardContent className="space-y-6">
            <div className="text-lg font-medium p-4 bg-slate-50 rounded-md border">
              {currentProblem.condition}
            </div>
            <div className="space-y-3">
              <Label>Choose an answer:</Label>
              {currentProblem.answer_options.map((option) => (
                <div
                  key={option.id}
                  className={`p-4 border rounded-lg cursor-pointer transition-colors ${
                    selectedAnswerId === option.id
                      ? "bg-primary/10 border-primary"
                      : "hover:bg-slate-50"
                  }`}
                  onClick={() => setSelectedAnswerId(option.id)}
                >
                  {option.text}
                </div>
              ))}
            </div>
          </CardContent>
          <CardFooter className="flex justify-between">
            <Button variant="outline" onClick={handleComplete} disabled={submitting}>
              Finish & Get Results
            </Button>
            <Button onClick={handleSubmit} disabled={!selectedAnswerId || submitting}>
              {submitting ? "Submitting..." : "Next Question"}
            </Button>
          </CardFooter>
        </Card>
      </div>
    );
  }

  if (session.status === "completed" && result) {
    return (
      <div className="flex flex-col items-center p-8">
        <Card className="max-w-2xl w-full">
          <CardHeader>
            <CardTitle>Entrance Test Completed!</CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            <p className="text-lg">Thank you for completing the entrance test.</p>
            <div className="p-4 bg-green-50 text-green-800 rounded-md">
              <p className="font-bold">Summary:</p>
              <ul className="list-disc ml-6 mt-2">
                <li>Total Problem Types Evaluated: {result.nodes.length}</li>
                <li>Learned Topics: {result.final_result.learned_problem_type_ids.length}</li>
              </ul>
            </div>
            <div className="mt-6">
              <h3 className="font-bold mb-2">Topic Summaries:</h3>
              <div className="grid grid-cols-1 gap-2">
                {result.topic_summaries.map(topic => (
                  <div key={topic.topic_id} className="p-2 border rounded flex justify-between">
                    <span>{topic.topic_name}</span>
                    <span className="text-sm text-slate-500">
                      {topic.learned_count}/{topic.total_problem_types} learned
                    </span>
                  </div>
                ))}
              </div>
            </div>
          </CardContent>
          <CardFooter>
            <Button variant="outline" onClick={handleStart} className="w-full">
              Retake Test
            </Button>
          </CardFooter>
        </Card>
      </div>
    );
  }

  return <div>Unknown Session Status: {session.status}</div>;
}
