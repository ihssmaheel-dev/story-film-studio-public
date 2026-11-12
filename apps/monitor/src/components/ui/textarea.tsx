import { createElement, type ComponentProps } from "react";
import { Field } from "@base-ui/react/field";
import { cn } from "@/lib/utils";

// Base UI owns labeling, validation, value changes and focus; its render API supplies the multiline element.
export function Textarea({
  className,
  ...props
}: ComponentProps<typeof Field.Control>) {
  return (
    <Field.Control
      render={createElement("textarea", { rows: 5 })}
      className={cn(
        "w-full resize-y rounded-lg border border-input bg-transparent px-3 py-2 text-sm leading-6 outline-none focus-visible:border-ring focus-visible:ring-2 focus-visible:ring-ring/30 disabled:opacity-50",
        className,
      )}
      {...props}
    />
  );
}
