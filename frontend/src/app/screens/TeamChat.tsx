import { useNavigate, useLocation } from "react-router";
import { ArrowLeft, Send, Loader2 } from "lucide-react";
import { Button } from "../components/ui/button";
import { Input } from "../components/ui/input";
import { useState, useRef, useEffect } from "react";
import { toast } from "sonner";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { getChatSessionId } from "@/lib/auth-storage";
import {
  isChatSendInFlightForScope,
  startBackgroundChatSend,
} from "@/lib/background-chat";
import { useRequireAuth } from "../hooks/useRequireAuth";

interface Message {
  id: string;
  text: string;
  isUser: boolean;
  time: string;
  sender?: string;
}

export default function TeamChat() {
  useRequireAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const chatState = (location.state as { taskTitle?: string; taskId?: number } | null) ?? null;
  const taskTitleForApi = chatState?.taskTitle?.trim() || undefined;
  const headerTitle = taskTitleForApi ?? "Общий чат команды";
  const chatScope = chatState?.taskId ? `task:${chatState.taskId}` : "general_v2";
  const historyKey = `chat_messages:${chatScope}`;

  const [message, setMessage] = useState("");
  const [messages, setMessages] = useState<Message[]>([]);
  const [sending, setSending] = useState(false);
  const sessionIdRef = useRef(getChatSessionId(chatScope));
  const bottomRef = useRef<HTMLDivElement>(null);
  const responderIndexRef = useRef(0);

  useEffect(() => {
    sessionIdRef.current = getChatSessionId(chatScope);
  }, [chatScope]);

  useEffect(() => {
    try {
      const raw = localStorage.getItem(historyKey);
      if (!raw) return;
      const parsed = JSON.parse(raw) as Message[];
      if (Array.isArray(parsed)) {
        setMessages(parsed);
      }
    } catch {
      /* ignore */
    }
  }, [historyKey]);

  useEffect(() => {
    localStorage.setItem(historyKey, JSON.stringify(messages));
  }, [messages, historyKey]);

  useEffect(() => {
    if (isChatSendInFlightForScope(chatScope)) {
      setSending(true);
    }
  }, [chatScope]);

  useEffect(() => {
    const onComplete = (ev: Event) => {
      const d = (ev as CustomEvent<{ historyKey: string }>).detail;
      if (d.historyKey !== historyKey) return;
      try {
        const raw = localStorage.getItem(historyKey);
        if (raw) {
          const parsed = JSON.parse(raw) as Message[];
          if (Array.isArray(parsed)) setMessages(parsed);
        }
      } catch {
        /* ignore */
      }
      sessionIdRef.current = getChatSessionId(chatScope);
      setSending(false);
    };
    window.addEventListener("chat-background-complete", onComplete);
    return () => window.removeEventListener("chat-background-complete", onComplete);
  }, [historyKey, chatScope]);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  const handleSendMessage = (e: React.FormEvent) => {
    e.preventDefault();
    const text = message.trim();
    if (!text || sending || isChatSendInFlightForScope(chatScope)) return;

    const now = new Date().toLocaleTimeString(undefined, {
      hour: "numeric",
      minute: "2-digit",
    });
    const userMsg: Message = {
      id: crypto.randomUUID(),
      text,
      isUser: true,
      time: now,
    };
    const nextMessages = [...messages, userMsg];
    localStorage.setItem(historyKey, JSON.stringify(nextMessages));
    setMessages(nextMessages);
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

    startBackgroundChatSend({
      historyKey,
      chatScope,
      sessionId: sessionIdRef.current,
      userText: text,
      taskTitleForApi,
      responderIndex,
      chatRestore,
    });

    if (chatState?.taskId != null) {
      const t = taskTitleForApi ?? chatState.taskTitle ?? "задаче";
      toast.info("Сообщение отправлено", {
        description: `Ответ появится в чате по задаче «${t}». Можно уйти со страницы — когда ответ будет готов, придёт уведомление с кнопкой «К чату задачи».`,
        duration: 9000,
      });
    } else {
      toast.info("Сообщение отправлено", {
        description:
          "Ответ появится в общем чате команды. Можно уйти со страницы — когда ответ будет готов, придёт уведомление с кнопкой «Открыть общий чат».",
        duration: 9000,
      });
    }
  };

  return (
    <div className="min-h-screen p-6 md:p-12">
      <div className="max-w-3xl mx-auto">
        <div className="flex items-center justify-between mb-6 gap-4">
          <button
            type="button"
            onClick={() => navigate("/dashboard")}
            className="flex items-center gap-2 text-[#9E9E9E] hover:text-[#FF9BB5] transition-colors shrink-0"
          >
            <ArrowLeft className="w-5 h-5" />
            <span>Назад</span>
          </button>
          <h2 className="text-xl text-center flex-1 truncate px-2">{headerTitle}</h2>
          <span className="w-16 shrink-0" aria-hidden />
        </div>

        <div className="bg-white rounded-[20px] shadow-lg overflow-hidden flex flex-col h-[600px]">
          <div className="flex-1 p-6 space-y-4 overflow-y-auto">
            {messages.length === 0 && (
              <p className="text-center text-[#9E9E9E] text-sm pt-8">
                Напишите вопрос, и вам ответит один из участников команды.
              </p>
            )}
            {messages.map((msg) => (
              <div
                key={msg.id}
                className={`flex ${msg.isUser ? "justify-end" : "justify-start"}`}
              >
                <div
                  className={`max-w-[70%] rounded-[20px] px-5 py-3 ${
                    msg.isUser
                      ? "bg-gradient-to-r from-[#FF9BB5] to-[#FFC2D4] text-white"
                      : "bg-[#FFF5F8] text-[#4A4A4A]"
                  }`}
                >
                  {!msg.isUser && (
                    <p className="text-xs mb-1 opacity-70">{msg.sender ?? "Команда"}</p>
                  )}
                  {msg.isUser ? (
                    <p className="leading-relaxed whitespace-pre-wrap">{msg.text}</p>
                  ) : (
                    <div className="leading-relaxed prose prose-sm max-w-none prose-p:my-2 prose-strong:text-inherit">
                      <ReactMarkdown remarkPlugins={[remarkGfm]}>
                        {msg.text}
                      </ReactMarkdown>
                    </div>
                  )}
                  <p
                    className={`text-xs mt-1 ${
                      msg.isUser ? "text-white/70" : "text-[#9E9E9E]"
                    }`}
                  >
                    {msg.time}
                  </p>
                </div>
              </div>
            ))}
            <div ref={bottomRef} />
          </div>

          <div className="p-6 border-t border-[#FFE5EC]">
            <form onSubmit={handleSendMessage} className="flex gap-3">
              <Input
                type="text"
                placeholder="Введите сообщение…"
                value={message}
                onChange={(e) => setMessage(e.target.value)}
                disabled={sending}
                className="flex-1 h-12 rounded-[20px] border-2 border-[#FFE5EC] bg-white px-5 focus:border-[#FF9BB5] transition-colors"
              />
              <Button
                type="submit"
                disabled={sending || !message.trim() || isChatSendInFlightForScope(chatScope)}
                className="h-12 w-12 rounded-full bg-gradient-to-r from-[#FF9BB5] to-[#FFC2D4] hover:from-[#FF8AAA] hover:to-[#FFB1C9] text-white shadow-md flex items-center justify-center p-0 shrink-0"
              >
                {sending || isChatSendInFlightForScope(chatScope) ? (
                  <Loader2 className="w-5 h-5 animate-spin" />
                ) : (
                  <Send className="w-5 h-5" />
                )}
              </Button>
            </form>
          </div>
        </div>
      </div>
    </div>
  );
}
