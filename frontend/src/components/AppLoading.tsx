import { LoaderCircle } from "lucide-react";
import { cn } from "@/lib/utils";


interface RouteLoadingScreenProps {
  title: string;
  message: string;
}


interface FullscreenLoadingOverlayProps {
  title: string;
  message: string;
}


interface SectionLoadingSkeletonProps {
  lines?: number;
  className?: string;
}


interface InlineLoadingLabelProps {
  idleText: string;
  loadingText: string;
  loading: boolean;
}


export function RouteLoadingScreen({ title, message }: RouteLoadingScreenProps) {
  return (
    <div className="min-h-screen px-4 py-5 lg:px-6 lg:py-6">
      <div className="mx-auto flex max-w-[1200px] flex-col gap-5">
        <div className="app-surface flex min-h-[38vh] flex-col items-center justify-center rounded-[1.9rem] px-6 py-10">
          <LoaderCircle className="size-8 animate-spin text-primary" />
          <p className="section-title mt-4 text-2xl text-foreground">{title}</p>
          <p className="mt-2 text-sm text-muted-foreground">{message}</p>
        </div>
      </div>
    </div>
  );
}


export function FullscreenLoadingOverlay({
  title,
  message,
}: FullscreenLoadingOverlayProps) {
  return (
    <div className="fixed inset-0 z-[70] flex items-center justify-center bg-background/88 backdrop-blur-md">
      <div className="app-surface mx-4 w-full max-w-[560px] rounded-[1.8rem] px-6 py-7 text-center">
        <LoaderCircle className="mx-auto size-9 animate-spin text-primary" />
        <p className="section-title mt-4 text-2xl text-foreground">{title}</p>
        <p className="mt-2 text-sm text-muted-foreground">{message}</p>
      </div>
    </div>
  );
}


export function SectionLoadingSkeleton({
  lines = 3,
  className,
}: SectionLoadingSkeletonProps) {
  return (
    <div className={cn("space-y-2", className)}>
      {Array.from({ length: Math.max(1, lines) }).map((_, index) => (
        <div
          key={`loading-line-${index}`}
          className={cn(
            "h-9 animate-pulse rounded-[0.9rem] border border-border/60 bg-muted/45",
            index === lines - 1 ? "w-4/5" : "w-full",
          )}
        />
      ))}
    </div>
  );
}


export function InlineLoadingLabel({
  idleText,
  loadingText,
  loading,
}: InlineLoadingLabelProps) {
  if (loading) {
    return (
      <span className="inline-flex items-center gap-2">
        <LoaderCircle className="size-4 animate-spin" />
        {loadingText}
      </span>
    );
  }

  return <span>{idleText}</span>;
}
