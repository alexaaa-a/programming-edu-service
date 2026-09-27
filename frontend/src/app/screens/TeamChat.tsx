import { useNavigate, useLocation } from "react-router";
import { Send, Loader2 } from "lucide-react";
import { useState, useRef, useEffect, type FormEvent } from "react";
import { toast } from "sonner";
import {
  isChatSendInFlightForScope,
  startBackgroundChatSend,
} from "@/lib/background-chat";
import { useRequireAuth } from "../hooks/useRequireAuth";
import { WorkspaceShell } from "../components/workspace/WorkspaceShell";
import { MarkdownBody } from "../components/MarkdownBody";
import { EmptyState } from "../components/EmptyState";
import { TEAM, memberFromSender } from "@/lib/team";
import { consumeEmmaSession, getCareer, getChatHistory, getMe, getMyAdminRole, getMyTrajectory } from "@/lib/api";
import { careerRights, keepOneMention } from "@/lib/career-rights";
import type { AdminRole, ChatHistoryItem, UserTrajectory } from "@/lib/types";
import { chatEmptyCopy } from "@/lib/trajectory";
import { ChatBriefing } from "../components/workspace/ChatBriefing";

interface Message {
  id: string;
  text: string;
  isUser: boolean;
  time: string;
  sender?: string;
}

function formatChatTime(iso: string): string {
  const normalized = /(?:Z|[+-]\d{2}:\d{2})$/.test(iso) ? iso : `${iso}Z`;
  const date = new Date(normalized);
  if (Number.isNaN(date.getTime())) return "";
  return date.toLocaleTimeString(undefined, { hour: "2-digit", minute: "2-digit" });
}

function historyToMessages(rows: ChatHistoryItem[]): Message[] {
  return rows.map((row) => ({
    id: row.id,
    text: row.text,
    isUser: row.role === "user",
    time: formatChatTime(row.created_at),
    sender: row.sender || undefined,
  }));
}

export default function TeamChat() {
  useRequireAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const chatState =
    (location.state as { taskTitle?: string; taskId?: number; emmaBriefing?: string } | null) ??
    null;
  const emmaBriefing = chatState?.emmaBriefing?.trim() || "";
  const taskTitleForApi = chatState?.taskTitle?.trim() || undefined;
  const headerTitle =
    taskTitleForApi ??
    (chatState?.taskId != null ? `Задача #${chatState.taskId}` : "Общий чат");
  const chatScope = chatState?.taskId ? `task:${chatState.taskId}` : "general";
  const sessionId = chatScope;

  const [userName, setUserName] = useState<string | undefined>();
  const [oneSpeaker, setOneSpeaker] = useState(false);
  const [emmaArmed, setEmmaArmed] = useState(Boolean(emmaBriefing));
  const [adminRole, setAdminRole] = useState<AdminRole>("user");
  const [message, setMessage] = useState("");
  const [messages, setMessages] = useState<Message[]>([]);
  const [historyReady, setHistoryReady] = useState(false);
  const [sending, setSending] = useState(false);
  const [trajectory, setTrajectory] = useState<UserTrajectory | null>(null);
  const bottomRef = useRef<HTMLDivElement>(null);
  const responderIndexRef = useRef(0);

  useEffect(() => {
    void (async () => {
      try {
        const [me, role, career] = await Promise.all([getMe(), getMyAdminRole(), getCareer()]);
        setUserName(me.name);
        setAdminRole(role.role);
        setOneSpeaker(careerRights(career?.grade).oneSpeaker);
      } catch {
        /* rail still works */
      }
    })();
  }, []);

  useEffect(() => {
    let cancelled = false;
    const loadTrajectory = async () => {
      try {
        const next = await getMyTrajectory(chatState?.taskId);
        if (!cancelled) setTrajectory(next);
      } catch {
        if (!cancelled) setTrajectory(null);
      }
    };
    void loadTrajectory();
    const onReviewReady = () => {
      void loadTrajectory();
    };
    const onFocus = () => {
      void loadTrajectory();
    };
    window.addEventListener("submission-review-ready", onReviewReady);
    window.addEventListener("focus", onFocus);
    return () => {
      cancelled = true;
      window.removeEventListener("submission-review-ready", onReviewReady);
      window.removeEventListener("focus", onFocus);
    };
  }, [chatState?.taskId]);

  useEffect(() => {
    let cancelled = false;
    let ticket = 0;
    let announced = false;
    const loadHistory = async (announce: boolean) => {
      const mine = ++ticket;
      try {
        const rows = await getChatHistory(chatState?.taskId);
        if (cancelled || mine !== ticket || isChatSendInFlightForScope(chatScope)) return;
        setMessages(historyToMessages(rows));
      } catch (err) {
        if (!cancelled && announce && !announced) {
          announced = true;
          toast.error(err instanceof Error ? err.message : "Не удалось открыть переписку");
        }
      } finally {
        if (!cancelled && mine === ticket) setHistoryReady(true);
      }
    };
    setHistoryReady(false);
    void loadHistory(true);
    const onFocus = () => {
      if (document.visibilityState === "hidden") return;
      if (isChatSendInFlightForScope(chatScope)) return;
      void loadHistory(false);
    };
    window.addEventListener("focus", onFocus);
    document.addEventListener("visibilitychange", onFocus);
    return () => {
      cancelled = true;
      window.removeEventListener("focus", onFocus);
      document.removeEventListener("visibilitychange", onFocus);
    };
  }, [chatScope, chatState?.taskId]);

  useEffect(() => {
    if (isChatSendInFlightForScope(chatScope)) setSending(true);
  }, [chatScope]);

  useEffect(() => {
    const onComplete = (ev: Event) => {
      const d = (ev as CustomEvent<{ chatScope: string; failed?: boolean; assistant?: Message }>).detail;
      if (d.chatScope !== chatScope) return;
      setSending(false);
      void (async () => {
        try {
          const rows = await getChatHistory(chatState?.taskId);
          setMessages(historyToMessages(rows));
        } catch {
          if (d.assistant) {
            setMessages((prev) =>
              prev.some((item) => item.id === d.assistant?.id) ? prev : [...prev, d.assistant!],
            );
          }
        }
      })();
    };
    window.addEventListener("chat-background-complete", onComplete);
    return () => window.removeEventListener("chat-background-complete", onComplete);
  }, [chatScope, chatState?.taskId]);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, sending]);

  const handleSendMessage = async (e: FormEvent) => {
    e.preventDefault();
    let text = message.trim();
    if (!text || sending || isChatSendInFlightForScope(chatScope)) return;
    let briefing: string | undefined;
    if (emmaArmed && emmaBriefing) {
      try {
        await consumeEmmaSession();
      } catch (err) {
        toast.error(err instanceof Error ? err.message : "Сессия Эммы уже использована");
        setEmmaArmed(false);
        return;
      }
      briefing = emmaBriefing;
      setEmmaArmed(false);
      if (!/@эмма\b/i.test(text)) text = `@Эмма ${text}`;
    }
    if (oneSpeaker) {
      const kept = keepOneMention(text);
      if (kept.trimmed) {
        toast.message("На стажёрском грейде за ход отвечает один человек");
      }
      text = kept.text;
    }

    const now = new Date().toLocaleTimeString(undefined, {
      hour: "2-digit",
      minute: "2-digit",
    });
    const userMsg: Message = {
      id: crypto.randomUUID(),
      text,
      isUser: true,
      time: now,
    };
    setMessages((prev) => [...prev, userMsg]);
    setMessage("");
    setSending(true);

    const responderIndex = responderIndexRef.current;
    responderIndexRef.current += 1;

    const chatRestore =
      chatState?.taskId != null
        ? {
            taskId: chatState.taskId,
            taskTitle: taskTitleForApi ?? chatState.taskTitle ?? "",
          }
        : null;

    const turnId = crypto.randomUUID();
    startBackgroundChatSend({
      chatScope,
      sessionId,
      userText: text,
      taskTitleForApi,
      taskId: chatState?.taskId,
      responderIndex,
      soloOnly: oneSpeaker || Boolean(briefing),
      emmaBriefing: briefing,
      chatRestore,
      turnId,
    });

    toast.info("Сообщение ушло команде", {
      description: "Можно не ждать на странице — ответ придёт уведомлением.",
      duration: 7000,
    });
  };

  const emptyChat = chatEmptyCopy(trajectory);

  return (
    <WorkspaceShell adminRole={adminRole} userName={userName} fullBleed>
      <div className="flex h-full min-h-0">
        <aside className="hidden w-[220px] shrink-0 flex-col border-r border-border bg-card/50 lg:flex">
          <div className="border-b border-border px-4 py-4">
            <p className="font-mono text-[11px] text-muted-foreground">
              Канал
            </p>
            <p className="mt-1 truncate text-sm font-medium">{headerTitle}</p>
          </div>
          <div className="flex-1 overflow-y-auto p-3">
            <p className="mb-2 px-1 font-mono text-[11px] text-muted-foreground">
              Участники
            </p>
            {TEAM.map((m) => (
              <button
                key={m.name}
                type="button"
                onClick={() =>
                  setMessage((prev) => {
                    if (!oneSpeaker) return prev ? `${prev} @${m.name}` : `@${m.name} `;
                    const rest = prev.replace(/@(?:Сара|Майк|Эмма|Джон)\s*/gi, "").trim();
                    return `@${m.name}${rest ? ` ${rest}` : ""} `;
                  })
                }
                className="mb-1 flex w-full items-center gap-2.5 rounded-[10px] px-2 py-2 text-left hover:bg-foreground/[0.04]"
              >
                <span
                  className="flex size-7 items-center justify-center rounded-full text-[11px] font-medium text-[#1c140e]"
                  style={{ background: m.accent }}
                >
                  {m.name.charAt(0)}
                </span>
                <span className="min-w-0">
                  <span className="block truncate text-[13px]">{m.name}</span>
                  <span className="block truncate text-[11px] text-muted-foreground">{m.role}</span>
                </span>
              </button>
            ))}
          </div>
          {chatState?.taskId != null && (
            <button
              type="button"
              onClick={() => navigate(`/task/${chatState.taskId}`)}
              className="border-t border-border px-4 py-3 text-left text-xs text-primary hover:underline"
            >
              Вернуться к задаче
            </button>
          )}
        </aside>

          <div className="flex min-w-0 flex-1 flex-col">
          <header className="flex shrink-0 items-center justify-between gap-3 border-b border-border px-4 py-3">
            <div className="min-w-0">
              <p className="font-mono text-[11px] text-primary">Команда</p>
              <h1 className="truncate text-lg leading-none">{headerTitle}</h1>
            </div>
          </header>
          {trajectory ? (
            <ChatBriefing trajectory={trajectory} taskTitle={taskTitleForApi} />
          ) : null}

          <div className="flex-1 space-y-5 overflow-y-auto px-4 py-5 sm:px-6">
            {historyReady && messages.length === 0 && (
              <EmptyState
                title={emptyChat.title}
                body={emptyChat.body}
              />
            )}
            {messages.map((msg) => {
              if (msg.isUser) {
                return (
                  <div key={msg.id} className="flex justify-end">
                    <div className="max-w-[min(100%,560px)] rounded-[10px] border border-primary/30 bg-primary/10 px-4 py-3 text-sm">
                      <p className="whitespace-pre-wrap leading-relaxed">{msg.text}</p>
                      <p className="mt-1 text-[11px] text-muted-foreground">{msg.time}</p>
                    </div>
                  </div>
                );
              }
              const member = memberFromSender(msg.sender);
              return (
                <div key={msg.id} className="flex gap-3">
                  <span
                    className="mt-0.5 flex size-8 shrink-0 items-center justify-center rounded-full text-xs font-medium text-[#1c140e]"
                    style={{ background: member.accent }}
                  >
                    {member.name.charAt(0)}
                  </span>
                  <div className="min-w-0 max-w-[min(100%,560px)]">
                    <p className="mb-1 text-[12px]">
                      <span className="font-medium">{member.name}</span>
                      <span className="text-muted-foreground"> · {member.role}</span>
                      <span className="text-muted-foreground"> · {msg.time}</span>
                    </p>
                    <div className="rounded-[10px] rounded-tl-md border border-border bg-card px-4 py-3">
                      <MarkdownBody text={msg.text} />
                    </div>
                  </div>
                </div>
              );
            })}
            {sending && (
              <div className="flex items-center gap-2 text-xs text-muted-foreground">
                <span className="size-1.5 animate-pulse rounded-full bg-primary" />
                Команда печатает…
              </div>
            )}
            <div ref={bottomRef} />
          </div>

          <form onSubmit={(e) => void handleSendMessage(e)} className="shrink-0 border-t border-border p-3 sm:p-4">
            <div className="flex items-end gap-2 rounded-xl border border-border bg-card px-3 py-2">
              <input
                type="text"
                placeholder={
                  emmaArmed
                    ? "Один вопрос Эмме по упавшему тесту — готовое решение она не напишет"
                    : oneSpeaker
                    ? "Один человек за сообщение: @Сара, @Майк, @Эмма или @Джон"
                    : trajectory?.action === "chat"
                      ? "Спроси, что именно не закрыто…"
                      : "Сообщение команде…"
                }
                value={message}
                onChange={(e) => setMessage(e.target.value)}
                disabled={sending}
                className="min-h-10 flex-1 bg-transparent text-sm text-foreground outline-none placeholder:text-muted-foreground"
              />
              <button
                type="submit"
                disabled={sending || !message.trim() || isChatSendInFlightForScope(chatScope)}
                className="flex size-9 shrink-0 items-center justify-center rounded-lg bg-primary text-primary-foreground disabled:opacity-40"
              >
                {sending || isChatSendInFlightForScope(chatScope) ? (
                  <Loader2 className="size-4 animate-spin" />
                ) : (
                  <Send className="size-4" />
                )}
              </button>
            </div>
          </form>
        </div>
      </div>
    </WorkspaceShell>
  );
}
