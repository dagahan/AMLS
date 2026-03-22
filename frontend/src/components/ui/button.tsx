"use client";

import { Button as ButtonPrimitive } from "@base-ui/react/button";
import { cva, type VariantProps } from "class-variance-authority";
import { cn } from "@/lib/utils";

const buttonVariants = cva(
  "group/button inline-flex shrink-0 items-center justify-center gap-2 whitespace-nowrap rounded-2xl border text-sm font-semibold transition-all outline-none select-none focus-visible:border-ring focus-visible:ring-4 focus-visible:ring-ring/60 disabled:pointer-events-none disabled:cursor-not-allowed disabled:opacity-50 [&_svg]:pointer-events-none [&_svg]:size-4 [&_svg]:shrink-0",
  {
    variants: {
      variant: {
        default:
          "border-primary bg-primary text-primary-foreground shadow-[0_18px_40px_rgba(82,112,235,0.22)] hover:border-primary hover:bg-primary/92",
        outline:
          "border-border bg-background/80 text-foreground hover:border-primary/35 hover:bg-accent hover:text-foreground",
        secondary:
          "border-secondary/25 bg-secondary/12 text-secondary hover:border-secondary/45 hover:bg-secondary/18",
        ghost:
          "border-transparent bg-transparent text-muted-foreground hover:border-border hover:bg-muted hover:text-foreground",
        destructive:
          "border-destructive/25 bg-destructive/10 text-destructive hover:border-destructive/45 hover:bg-destructive/16",
        link: "h-auto border-transparent bg-transparent p-0 text-primary underline-offset-4 hover:underline",
      },
      size: {
        default: "h-11 px-5",
        xs: "h-8 rounded-xl px-3 text-xs",
        sm: "h-9 rounded-xl px-4 text-sm",
        lg: "h-12 px-6 text-base",
        icon: "size-10",
        "icon-xs": "size-8 rounded-xl",
        "icon-sm": "size-9 rounded-xl",
        "icon-lg": "size-11",
      },
    },
    defaultVariants: {
      variant: "default",
      size: "default",
    },
  },
);


function Button({
  className,
  variant = "default",
  size = "default",
  ...props
}: ButtonPrimitive.Props & VariantProps<typeof buttonVariants>) {
  return (
    <ButtonPrimitive
      data-slot="button"
      className={cn(buttonVariants({ variant, size, className }))}
      {...props}
    />
  );
}


export { Button, buttonVariants };
