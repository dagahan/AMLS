import MathText from "@/components/MathText";
import type { GraphAssessmentResponse, TestAttemptReviewResponse } from "@/lib/api-types";
import { buildTestReviewSummary } from "@/lib/test-review-summary";
import { formatElapsedSeconds } from "@/lib/test-timer";
import { formatTestKindLabel, formatTestStatusLabel } from "@/lib/test-kind";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";


interface TestAttemptReviewPanelProps {
  reviewPayload: TestAttemptReviewResponse;
  linkedAssessment: GraphAssessmentResponse | null;
}


function formatTimestamp(rawValue: string | null): string {
  if (!rawValue) {
    return "Not set";
  }

  const parsedTimestamp = new Date(rawValue);
  if (Number.isNaN(parsedTimestamp.valueOf())) {
    return rawValue;
  }

  return parsedTimestamp.toLocaleString();
}


function findAnswerTextForItem(item: TestAttemptReviewResponse["items"][number]): string {
  if (!item.chosen_answer_option_id) {
    return "No answer selected";
  }

  const matchingAnswerOption = item.problem.answer_options.find(
    (answerOption) => answerOption.id === item.chosen_answer_option_id,
  );

  if (!matchingAnswerOption) {
    return "Selected option is not available";
  }

  return matchingAnswerOption.text;
}


function normalizeAdviceItems(rawAdviceItems: string[]): string[] {
  const normalizedAdviceItems: string[] = [];

  for (const rawAdviceItem of rawAdviceItems) {
    const normalizedAdviceItem = rawAdviceItem.trim();
    if (normalizedAdviceItem === "") {
      continue;
    }
    if (normalizedAdviceItems.includes(normalizedAdviceItem)) {
      continue;
    }
    normalizedAdviceItems.push(normalizedAdviceItem);
    if (normalizedAdviceItems.length === 3) {
      break;
    }
  }

  return normalizedAdviceItems;
}


export default function TestAttemptReviewPanel({
  reviewPayload,
  linkedAssessment,
}: TestAttemptReviewPanelProps) {
  const scoreSummary = buildTestReviewSummary(reviewPayload.items);
  const adviceItems = normalizeAdviceItems(linkedAssessment?.review_recommendations ?? []);

  return (
    <div className="space-y-5">
      <Card>
        <CardHeader>
          <p className="section-kicker">Result summary</p>
          <CardTitle>
            {formatTestKindLabel(reviewPayload.test_attempt.kind)} • {formatTestStatusLabel(reviewPayload.test_attempt.status)}
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-2">
          <div className="rounded-[1rem] border border-border/70 bg-background/78 px-3 py-2 text-sm text-muted-foreground">
            Score: {scoreSummary.correctCount}/{scoreSummary.totalCount} ({scoreSummary.scorePercent}%)
          </div>
          <div className="rounded-[1rem] border border-border/70 bg-background/78 px-3 py-2 text-sm text-muted-foreground">
            Wrong answers: {scoreSummary.wrongCount} • Revealed solutions: {scoreSummary.revealedCount}
          </div>
          <div className="rounded-[1rem] border border-border/70 bg-background/78 px-3 py-2 text-sm text-muted-foreground">
            Solving time: {formatElapsedSeconds(reviewPayload.test_attempt.elapsed_solve_seconds)}
          </div>
          <div className="rounded-[1rem] border border-border/70 bg-background/78 px-3 py-2 text-sm text-muted-foreground">
            Started: {formatTimestamp(reviewPayload.test_attempt.started_at)} • Finished: {formatTimestamp(reviewPayload.test_attempt.ended_at)}
          </div>
        </CardContent>
      </Card>

      {linkedAssessment ? (
        <Card>
          <CardHeader>
            <p className="section-kicker">Study advice</p>
            <CardTitle>
              Review status: {linkedAssessment.review_status} • Confidence: {Math.round(linkedAssessment.state_confidence * 100)}%
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-2">
            {adviceItems.length > 0 ? (
              <div className="space-y-2">
                {adviceItems.map((adviceItem, index) => (
                  <div
                    key={`${index}-${adviceItem}`}
                    className="rounded-[1rem] border border-primary/35 bg-primary/10 px-3 py-3 text-sm text-foreground"
                  >
                    {adviceItem}
                  </div>
                ))}
              </div>
            ) : (
              <div className="rounded-[1rem] border border-border/70 bg-background/78 px-3 py-3 text-sm text-muted-foreground">
                Advice is not available for this attempt yet.
              </div>
            )}
            {linkedAssessment.review_error ? (
              <div className="rounded-[1rem] border border-amber-400/45 bg-amber-500/12 px-3 py-3 text-sm text-amber-200">
                {linkedAssessment.review_error}
              </div>
            ) : null}
          </CardContent>
        </Card>
      ) : null}

      <Card>
        <CardHeader>
          <p className="section-kicker">Question review</p>
          <CardTitle>Detailed attempt analysis</CardTitle>
        </CardHeader>
        <CardContent className="space-y-3">
          {reviewPayload.items.length === 0 ? (
            <p className="text-sm text-muted-foreground">No question records are available for this attempt.</p>
          ) : (
            reviewPayload.items.map((reviewItem, index) => (
              <div
                key={reviewItem.response_id}
                className="rounded-[1.2rem] border border-border/70 bg-background/80 px-3 py-3"
              >
                <p className="text-xs font-semibold uppercase tracking-[0.15em] text-primary">
                  Question {index + 1} • {reviewItem.problem.problem_type.name}
                </p>
                <MathText content={reviewItem.problem.condition} className="mt-2 text-sm leading-7 text-foreground" />
                <div className="mt-3 rounded-[0.9rem] border border-border/70 bg-background/78 px-3 py-2">
                  <p className="text-xs font-semibold uppercase tracking-[0.15em] text-primary">Selected answer</p>
                  <MathText content={findAnswerTextForItem(reviewItem)} className="mt-1 text-sm leading-7 text-foreground" />
                </div>
                <div className="mt-2 rounded-[0.9rem] border border-border/70 bg-background/78 px-3 py-2 text-sm text-muted-foreground">
                  Result: {reviewItem.chosen_answer_option_type === "right" && !reviewItem.revealed_solution ? "Correct" : "Incorrect"}
                  {reviewItem.revealed_solution ? " • Solution was revealed" : ""}
                </div>
                <div className="mt-2 rounded-[0.9rem] border border-border/70 bg-background/78 px-3 py-2">
                  <p className="text-xs font-semibold uppercase tracking-[0.15em] text-primary">Solution</p>
                  <MathText content={reviewItem.solution} className="mt-1 text-sm leading-7 text-foreground" />
                </div>
              </div>
            ))
          )}
        </CardContent>
      </Card>
    </div>
  );
}
