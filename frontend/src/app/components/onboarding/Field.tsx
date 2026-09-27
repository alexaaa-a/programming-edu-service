import type { ComponentProps } from "react";
import { Input } from "../ui/input";
import { cn } from "../ui/utils";

export const fieldClass =
  "h-12 rounded-[10px] border border-foreground/15 bg-[#1c1916] px-4 text-[15px] text-foreground placeholder:text-muted-foreground/70 transition-colors focus-visible:border-primary/80 focus-visible:ring-2 focus-visible:ring-primary/25";

export const selectClass =
  "h-12 w-full rounded-[10px] border border-foreground/15 bg-[#1c1916] px-4 text-[15px] text-foreground outline-none focus:border-primary/80 focus:ring-2 focus:ring-primary/25";

export function Field({
  label,
  className,
  ...props
}: ComponentProps<"input"> & { label: string }) {
  const id = props.id ?? props.name ?? label;
  return (
    <label className="block space-y-2">
      <span className="text-[12px] font-medium text-muted-foreground">{label}</span>
      <Input id={id} className={cn(fieldClass, className)} {...props} />
    </label>
  );
}

export function PrimaryButton({
  className,
  ...props
}: ComponentProps<"button">) {
  return (
    <button
      className={cn(
        "inline-flex h-12 w-full items-center justify-center gap-2 rounded-[10px] bg-primary px-6 text-[15px] font-medium text-primary-foreground transition-[transform,background-color,opacity] duration-200 hover:bg-[#efc49a] active:scale-[0.985] disabled:cursor-not-allowed disabled:opacity-40 disabled:active:scale-100",
        className,
      )}
      {...props}
    />
  );
}
