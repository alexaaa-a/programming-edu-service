import { useEffect, useState } from "react";
import Editor, { DiffEditor, loader } from "@monaco-editor/react";
import * as monaco from "monaco-editor";
import type { ReviewMark } from "@/lib/review-marks";
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

const MARK_OWNER = "desk-review";

const SEVERITY: Record<ReviewMark["severity"], monaco.MarkerSeverity> = {
  error: monaco.MarkerSeverity.Error,
  warning: monaco.MarkerSeverity.Warning,
  info: monaco.MarkerSeverity.Info,
};

export function CodeEditor({
  value,
  onChange,
  language,
  onLanguageChange,
  readOnly,
  marks = [],
  compareWith = null,
  focusLine = null,
}: {
  value: string;
  onChange: (next: string) => void;
  language: EditorLang;
  onLanguageChange: (lang: EditorLang) => void;
  readOnly?: boolean;
  marks?: ReviewMark[];
  compareWith?: string | null;
  focusLine?: number | null;
}) {
  const [editor, setEditor] = useState<monaco.editor.IStandaloneCodeEditor | null>(null);

  useEffect(() => {
    defineDeskTheme();
  }, []);

  useEffect(() => {
    const model = editor?.getModel();
    if (!model) return;
    monaco.editor.setModelMarkers(
      model,
      MARK_OWNER,
      marks
        .filter((mark) => mark.line <= model.getLineCount())
        .map((mark) => ({
          severity: SEVERITY[mark.severity],
          message: `${mark.title}: ${mark.message}`,
          startLineNumber: mark.line,
          endLineNumber: mark.line,
          startColumn: model.getLineFirstNonWhitespaceColumn(mark.line) || 1,
          endColumn: model.getLineMaxColumn(mark.line),
        })),
    );
    return () => {
      const current = editor?.getModel();
      if (current) monaco.editor.setModelMarkers(current, MARK_OWNER, []);
    };
  }, [editor, marks, value, compareWith]);

  useEffect(() => {
    if (!focusLine || !editor) return;
    editor.revealLineInCenter(focusLine);
    editor.setPosition({ lineNumber: focusLine, column: 1 });
  }, [editor, focusLine]);

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
          {compareWith !== null ? "сравнение" : readOnly ? "только чтение" : "workspace"}
        </span>
      </div>
      <div className="min-h-0 flex-1">
        {compareWith !== null ? (
          <DiffEditor
            theme="desk-dark"
            language={language}
            original={compareWith}
            modified={value}
            options={{
              readOnly: true,
              renderSideBySide: false,
              minimap: { enabled: false },
              fontSize: 13,
              fontFamily: "Geist Mono, ui-monospace, SFMono-Regular, Menlo, monospace",
              scrollBeyondLastLine: false,
              automaticLayout: true,
              wordWrap: "on",
              overviewRulerLanes: 0,
            }}
          />
        ) : (
        <Editor
          theme="desk-dark"
          language={language}
          value={value}
          onChange={(next) => onChange(next ?? "")}
          onMount={(instance) => setEditor(instance)}
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
            renderValidationDecorations: "on",
          }}
        />
        )}
      </div>
    </div>
  );
}
