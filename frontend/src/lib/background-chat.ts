import { toast } from "sonner";
import { chatMessage } from "./api";
import { setChatSessionId } from "./auth-storage";
import { appNavigate } from "./app-navigate";
import { pickResponder } from "./chat-persona";

export interface ChatMessageRow {
  id: string;
  text: string;
  isUser: boolean;
  time: string;
  sender?: string;
}

const inFlightByScope = new Map<string, boolean>();

function loadMessages(historyKey: string): ChatMessageRow[] {
  try {
    const raw = localStorage.getItem(historyKey);
    if (!raw) return [];
    const p = JSON.parse(raw) as ChatMessageRow[];
    return Array.isArray(p) ? p : [];
  } catch {
    return [];
  }
}

function saveMessages(historyKey: string, messages: ChatMessageRow[]): void {
  localStorage.setItem(historyKey, JSON.stringify(messages));
}

export function isChatSendInFlightForScope(chatScope: string): boolean {
  return inFlightByScope.get(chatScope) ?? false;
}

export function startBackgroundChatSend(params: {
  historyKey: string;
  chatScope: string;
  sessionId: string;
  userText: string;
  taskTitleForApi?: string;
  responderIndex: number;
  chatRestore?: { taskId: number; taskTitle: string } | null;
}): void {
  const {
    historyKey,
    chatScope,
    sessionId,
    userText,
    taskTitleForApi,
    responderIndex,
    chatRestore,
  } = params;
  if (inFlightByScope.get(chatScope)) return;
  inFlightByScope.set(chatScope, true);

  void (async () => {
    try {
      const res = await chatMessage(
        sessionId,
        userText,
        taskTitleForApi ? { task_title: taskTitleForApi } : undefined,
      );
      setChatSessionId(chatScope, res.session_id);

      const responder = pickResponder(userText, responderIndex);
      const replyTime = new Date().toLocaleTimeString(undefined, {
        hour: "numeric",
        minute: "2-digit",
      });
      const assistantMsg: ChatMessageRow = {
        id: crypto.randomUUID(),
        text: res.answer,
        isUser: false,
        time: replyTime,
        sender: `${responder.name} (${responder.role})`,
      };

      const merged = loadMessages(historyKey);
      merged.push(assistantMsg);
      saveMessages(historyKey, merged);

      window.dispatchEvent(
        new CustomEvent("chat-background-complete", { detail: { historyKey } }),
      );

      const isTaskChat = chatRestore?.taskId != null;
      const taskLabel = chatRestore?.taskTitle?.trim()
        ? ` «${chatRestore.taskTitle.trim()}»`
        : "";

      toast.success(
        isTaskChat ? `Ответ в чате по задаче${taskLabel} готов` : "Ответ в общем чате готов",
        {
          description: isTaskChat
            ? "Сообщение сохранено в чате этой задачи. Можете открыть чат по кнопке ниже или вернуться к задаче."
            : "Сообщение сохранено в общем командном чате. Откройте чат по кнопке ниже.",
          duration: 12_000,
          action: {
            label: isTaskChat ? "К чату задачи" : "Открыть общий чат",
            onClick: () => {
              if (isTaskChat && chatRestore) {
                appNavigate("/chat", {
                  state: {
                    taskId: chatRestore.taskId,
                    taskTitle: chatRestore.taskTitle,
                  },
                });
              } else {
                appNavigate("/chat");
              }
            },
          },
        },
      );
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Не удалось отправить сообщение");
      window.dispatchEvent(
        new CustomEvent("chat-background-complete", { detail: { historyKey } }),
      );
    } finally {
      inFlightByScope.delete(chatScope);
    }
  })();
}
