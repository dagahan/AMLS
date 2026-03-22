import * as React from "react";
import { cn } from "@/lib/utils";


function Card({
  className,
  size = "default",
  ...props
}: React.ComponentProps<"div"> & { size?: "default" | "sm" }) {
  return (
    <div
      data-slot="card"
      data-size={size}
      className={cn(
        "group/card app-surface flex flex-col gap-5 rounded-[1.75rem] py-5 text-sm text-card-foreground data-[size=sm]:gap-4 data-[size=sm]:py-4 has-data-[slot=card-footer]:pb-0",
        className,
      )}
      {...props}
    />
  );
}


function CardHeader({ className, ...props }: React.ComponentProps<"div">) {
  return (
    <div
      data-slot="card-header"
      className={cn(
        "grid auto-rows-min items-start gap-2 px-5 data-[slot=card-header]:relative group-data-[size=sm]/card:px-4 has-data-[slot=card-action]:grid-cols-[1fr_auto]",
        className,
      )}
      {...props}
    />
  );
}


function CardTitle({ className, ...props }: React.ComponentProps<"div">) {
  return (
    <div
      data-slot="card-title"
      className={cn(
        "font-heading text-xl leading-tight font-semibold tracking-[-0.03em] group-data-[size=sm]/card:text-lg",
        className,
      )}
      {...props}
    />
  );
}


function CardDescription({ className, ...props }: React.ComponentProps<"div">) {
  return (
    <div
      data-slot="card-description"
      className={cn("text-sm leading-6 text-muted-foreground", className)}
      {...props}
    />
  );
}


function CardAction({ className, ...props }: React.ComponentProps<"div">) {
  return (
    <div
      data-slot="card-action"
      className={cn("col-start-2 row-start-1 self-start justify-self-end", className)}
      {...props}
    />
  );
}


function CardContent({ className, ...props }: React.ComponentProps<"div">) {
  return (
    <div
      data-slot="card-content"
      className={cn("px-5 group-data-[size=sm]/card:px-4", className)}
      {...props}
    />
  );
}


function CardFooter({ className, ...props }: React.ComponentProps<"div">) {
  return (
    <div
      data-slot="card-footer"
      className={cn(
        "flex items-center border-t border-border/70 bg-muted/55 px-5 py-4 group-data-[size=sm]/card:px-4 group-data-[size=sm]/card:py-3",
        className,
      )}
      {...props}
    />
  );
}


export {
  Card,
  CardHeader,
  CardFooter,
  CardTitle,
  CardAction,
  CardDescription,
  CardContent,
};
