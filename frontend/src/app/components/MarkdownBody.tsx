import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { cn } from "./ui/utils";

export function MarkdownBody({ text, className }: { text: string; className?: string }) {
  return (
    <div
      className={cn(
        "text-sm leading-relaxed [&_p]:my-2 [&_p:first-child]:mt-0 [&_p:last-child]:mb-0",
        "[&_ul]:my-2 [&_ul]:list-disc [&_ul]:pl-4 [&_ol]:my-2 [&_ol]:list-decimal [&_ol]:pl-4",
        "[&_code]:rounded [&_code]:bg-foreground/10 [&_code]:px-1 [&_code]:font-mono [&_code]:text-[12px]",
        "[&_pre]:my-2 [&_pre]:overflow-x-auto [&_pre]:rounded-lg [&_pre]:bg-black/40 [&_pre]:p-3",
        "[&_a]:text-primary [&_a]:underline-offset-2 [&_strong]:text-foreground",
        className,
      )}
    >
      <ReactMarkdown remarkPlugins={[remarkGfm]}>{text}</ReactMarkdown>
    </div>
  );
}
