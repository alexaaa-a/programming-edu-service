import { Link } from "react-router";
import { cn } from "../ui/utils";

export function BrandMark({
  to = "/",
  compact = false,
  className,
}: {
  to?: string;
  compact?: boolean;
  className?: string;
}) {
  return (
    <Link to={to} className={cn("inline-flex items-center gap-2.5 text-foreground", className)}>
      <span className="font-display flex size-8 items-center justify-center rounded-[10px] bg-primary text-[15px] text-primary-foreground">
        D
      </span>
      {!compact && <span className="font-display text-[22px] leading-none">Desk</span>}
    </Link>
  );
}
