import { toast } from "sonner";
import { chatMessage } from "./api";
import { appNavigate } from "./app-navigate";
import { formatSender, pickResponder } from "./chat-persona";

const inFlightByScope = new Map<string, boolean>();

export function isChatSendInFlightForScope(chatScope: string): boolean {
  return inFlightByScope.get(chatScope) ?? false;
}

export function startBackgroundChatSend(params: {
  chatScope: string;
  sessionId: string;
  userText: string;
  taskTitleForApi?: string;
  taskId?: number;
  responderIndex: number;
  soloOnly?: boolean;
  emmaBriefing?: string;
  chatRestore?: { taskId: number; taskTitle: string } | null;
  turnId?: string;
}): void {
  const {
    chatScope,
    sessionId,
    userText,
    taskTitleForApi,
    taskId,
    responderIndex,
    soloOnly,
    emmaBriefing,
    chatRestore,
    turnId,
  } = params;
  if (inFlightByScope.get(chatScope)) return;
  inFlightByScope.set(chatScope, true);

  const resolvedTurnId = turnId?.trim() || crypto.randomUUID();

  void (async () => {
    try {
      const context: {
        task_title?: string;
        task_id?: number;
        turn_id?: string;
        solo_only?: boolean;
        emma_briefing?: string;
      } = { turn_id: resolvedTurnId };
      if (soloOnly) context.solo_only = true;
      if (emmaBriefing) context.emma_briefing = emmaBriefing;
      if (taskTitleForApi) context.task_title = taskTitleForApi;
      if (taskId != null) context.task_id = taskId;
      const res = await chatMessage(sessionId, userText, context);

      const responder =
        res.speaker && res.role
          ? { name: res.speaker, role: res.role }
          : pickResponder(userText, responderIndex);
      const replyTime = new Date().toLocaleTimeString(undefined, {
        hour: "2-digit",
        minute: "2-digit",
      });
      window.dispatchEvent(
        new CustomEvent("chat-background-complete", {
          detail: {
            chatScope,
            assistant: {
              id: `turn:${resolvedTurnId}`,
              text: res.answer,
              isUser: false,
              time: replyTime,
              sender: formatSender(responder),
            },
          },
        }),
      );

      const isTaskChat = chatRestore?.taskId != null;
      const taskLabel = chatRestore?.taskTitle?.trim()
        ? ` «${chatRestore.taskTitle.trim()}»`
        : "";

      const huddle = res.mode === "huddle";
      toast.success(
        huddle
          ? `${responder.name} ответил после совещания`
          : isTaskChat
            ? `Ответ в чате по задаче${taskLabel} готов`
            : `${responder.name} ответил`,
        {
          description: huddle
            ? "Эмма и Сара скинули заметки, итоговый ответ — от того, кто ведёт."
            : isTaskChat
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
        new CustomEvent("chat-background-complete", {
          detail: { chatScope, failed: true },
        }),
      );
    } finally {
      inFlightByScope.delete(chatScope);
    }
  })();
}
