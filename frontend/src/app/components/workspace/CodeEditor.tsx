import { useEffect } from "react";
import Editor, { loader } from "@monaco-editor/react";
import * as monaco from "monaco-editor";
import editorWorker from "monaco-editor/editor/editor.worker.js?worker";
import jsonWorker from "monaco-editor/language/json/json.worker.js?worker";
import tsWorker from "monaco-editor/language/typescript/ts.worker.js?worker";

self.MonacoEnvironment = {
  getWorker(_, label) {
    if (label === "json") return new jsonWorker();
    if (label === "typescript" || label === "javascript") return new tsWorker();
    return new editorWorker();
  },
};

loader.config({ monaco });

const LANGS = [
  { id: "python", label: "Python" },
  { id: "typescript", label: "TS" },
  { id: "javascript", label: "JS" },
] as const;

export type EditorLang = (typeof LANGS)[number]["id"];

export function languageFromDirection(direction: string | null | undefined): EditorLang {
  if (direction === "frontend" || direction === "fullstack") return "typescript";
  return "python";
}

function defineDeskTheme() {
  monaco.editor.defineTheme("desk-dark", {
    base: "vs-dark",
    inherit: true,
    rules: [],
    colors: {
      "editor.background": "#100e0c",
      "editor.foreground": "#F6F1E8",
      "editorLineNumber.foreground": "#8d8478",
      "editorLineNumber.activeForeground": "#F6F1E8",
      "editor.lineHighlightBackground": "#191714",
      "editorCursor.foreground": "#e4b48a",
      "editor.selectionBackground": "#e4b48a33",
      "editorWidget.background": "#191714",
      "editorGutter.background": "#100e0c",
    },
  });
}

export function CodeEditor({
  value,
  onChange,
  language,
  onLanguageChange,
  readOnly,
}: {
  value: string;
  onChange: (next: string) => void;
  language: EditorLang;
  onLanguageChange: (lang: EditorLang) => void;
  readOnly?: boolean;
}) {
  useEffect(() => {
    defineDeskTheme();
  }, []);

  return (
    <div className="flex min-h-0 flex-1 flex-col">
      <div className="flex items-center justify-between border-b border-border px-3 py-2">
        <div className="flex gap-1">
          {LANGS.map((lang) => (
            <button
              key={lang.id}
              type="button"
              onClick={() => onLanguageChange(lang.id)}
              className={
                language === lang.id
                  ? "rounded-md bg-foreground/10 px-2 py-1 font-mono text-[10px] tracking-wide text-foreground uppercase"
                  : "rounded-md px-2 py-1 font-mono text-[10px] tracking-wide text-muted-foreground uppercase hover:text-foreground"
              }
            >
              {lang.label}
            </button>
          ))}
        </div>
        <span className="font-mono text-[10px] tracking-wide text-muted-foreground uppercase">
          {readOnly ? "только чтение" : "workspace"}
        </span>
      </div>
      <div className="min-h-0 flex-1">
        <Editor
          theme="desk-dark"
          language={language}
          value={value}
          onChange={(next) => onChange(next ?? "")}
          options={{
            readOnly,
            minimap: { enabled: false },
            fontSize: 13,
            fontFamily: "Geist Mono, ui-monospace, SFMono-Regular, Menlo, monospace",
            padding: { top: 16, bottom: 16 },
            scrollBeyondLastLine: false,
            smoothScrolling: true,
            automaticLayout: true,
            tabSize: 2,
            wordWrap: "on",
            renderLineHighlight: "line",
            cursorBlinking: "smooth",
            overviewRulerLanes: 0,
          }}
        />
      </div>
    </div>
  );
}
