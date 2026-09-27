import type { ReactNode } from "react";

export function EmptyState({
  kicker,
  title,
  body,
  action,
}: {
  kicker?: string;
  title: string;
  body: string;
  action?: ReactNode;
}) {
  return (
    <div className="mx-auto max-w-md py-16 text-center">
      {kicker && (
        <p className="font-mono text-[11px] text-primary">{kicker}</p>
      )}
      <h2 className="mt-3 text-3xl">{title}</h2>
      <p className="mt-2 text-sm leading-relaxed text-muted-foreground">{body}</p>
      {action && <div className="mt-6 flex justify-center">{action}</div>}
    </div>
  );
}
