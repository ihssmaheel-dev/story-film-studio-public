import type { ReactNode } from "react";
import { Card, CardContent, CardHeader } from "@/components/ui/card";
import { cn } from "@/lib/utils";

export function SectionPanel({
  title,
  description,
  action,
  children,
  className,
  contentClassName,
}: {
  title: string;
  description?: string;
  action?: ReactNode;
  children: ReactNode;
  className?: string;
  contentClassName?: string;
}) {
  return (
    <Card className={cn("panel", className)}>
      <CardHeader className="panel-heading">
        <div className="min-w-0">
          <h2 className="panel-title">{title}</h2>
          {description && <p className="panel-description">{description}</p>}
        </div>
        {action}
      </CardHeader>
      <CardContent className={cn("panel-content", contentClassName)}>
        {children}
      </CardContent>
    </Card>
  );
}
