import type { ReactNode } from "react";
import { BrandMark } from "../brand/BrandMark";

export function OnboardingShell({
  children,
  aside,
  step,
  stepLabel,
}: {
  children: ReactNode;
  aside?: ReactNode;
  step?: number;
  stepLabel?: string;
}) {
  return (
    <div className="theme-night relative min-h-screen overflow-hidden bg-background text-foreground">
      {aside ? (
        <div className="relative mx-auto grid min-h-screen max-w-6xl lg:grid-cols-[1.05fr_0.95fr]">
          <aside className="hidden flex-col justify-between border-r border-border p-12 lg:flex xl:p-16">
            <BrandMark />
            <div className="page-rise max-w-lg space-y-7">{aside}</div>
            <p className="font-mono text-[11px] text-muted-foreground">Симулятор junior-команды</p>
          </aside>
          <main className="flex items-center justify-center p-6 sm:p-12">
            <div className="page-rise w-full max-w-md">
              <div className="mb-10 lg:hidden">
                <BrandMark />
              </div>
              {children}
            </div>
          </main>
        </div>
      ) : (
        <div className="relative mx-auto flex min-h-screen max-w-5xl flex-col px-6 py-8 sm:px-10">
          <header className="mb-16 flex items-center justify-between">
            <BrandMark />
            {step != null && (
              <p className="font-mono text-[11px] text-muted-foreground">
                {stepLabel ?? `Шаг ${step} из 3`}
              </p>
            )}
          </header>
          <main className="page-rise flex flex-1 flex-col justify-center pb-16">{children}</main>
        </div>
      )}
    </div>
  );
}
