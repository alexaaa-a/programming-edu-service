import type { LucideIcon } from "lucide-react";
import { cn } from "../ui/utils";

export function ChoiceCard({
  title,
  description,
  icon: Icon,
  selected,
  onSelect,
}: {
  title: string;
  description: string;
  icon: LucideIcon;
  selected: boolean;
  onSelect: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onSelect}
      className={cn(
        "group rounded-[10px] border bg-card p-7 text-left transition-[border-color,background-color,transform] duration-300",
        selected
          ? "border-primary/70 bg-primary/[0.06]"
          : "border-border hover:-translate-y-0.5 hover:border-foreground/15",
      )}
    >
      <div
        className={cn(
          "mb-8 flex size-10 items-center justify-center rounded-[10px] transition-colors",
          selected ? "bg-primary text-primary-foreground" : "bg-secondary text-muted-foreground",
        )}
      >
        <Icon className="size-[18px]" strokeWidth={1.5} />
      </div>
      <h3 className="font-display mb-2 text-[26px] leading-none">{title}</h3>
      <p className="text-sm leading-relaxed text-muted-foreground">{description}</p>
    </button>
  );
}
