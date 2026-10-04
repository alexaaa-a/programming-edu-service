import { useEffect, useMemo, useState } from "react";
import { Trash2 } from "lucide-react";
import { toast } from "sonner";
import { useRequireAuth } from "../hooks/useRequireAuth";
import {
  addAdmin,
  createProjectTemplate,
  getAdmins,
  getMe,
  getMyAdminRole,
  removeAdmin,
} from "@/lib/api";
import type { AdminRole, AdminUser, CreateProjectTemplatePayload } from "@/lib/types";
import { WorkspaceShell } from "../components/workspace/WorkspaceShell";
import { LoadingState } from "../components/LoadingState";
import { EmptyState } from "../components/EmptyState";
import { Field, PrimaryButton, fieldClass, selectClass } from "../components/onboarding/Field";
import { TemplateGenerator, type TemplateDraft } from "../components/admin/TemplateGenerator";
import { cn } from "../components/ui/utils";

const sampleSprints = [
  {
    order: 1,
    title: "Спринт 1",
    tasks: [
      {
        title: "Настроить проект",
        description: "Создать базовую структуру и README",
        tests: "",
      },
    ],
  },
];

export default function AdminPanel() {
  useRequireAuth();

  const [role, setRole] = useState<AdminRole>("user");
  const [userName, setUserName] = useState<string | undefined>();
  const [loading, setLoading] = useState(true);

  const [admins, setAdmins] = useState<AdminUser[]>([]);
  const [newAdminId, setNewAdminId] = useState("");
  const [adminBusy, setAdminBusy] = useState(false);

  const [title, setTitle] = useState("");
  const [description, setDescription] = useState("");
  const [direction, setDirection] = useState("backend");
  const [level, setLevel] = useState("junior");
  const [sprintsJson, setSprintsJson] = useState(JSON.stringify(sampleSprints, null, 2));
  const [templateBusy, setTemplateBusy] = useState(false);

  const canManageAdmins = role === "superadmin";
  const canCreateTemplates = role === "admin" || role === "superadmin";

  const sprintsPreviewError = useMemo(() => {
    try {
      const parsed = JSON.parse(sprintsJson);
      if (!Array.isArray(parsed)) return "Спринты должны быть массивом.";
      return "";
    } catch {
      return "Некорректный JSON спринтов.";
    }
  }, [sprintsJson]);

  const loadAdmins = async () => {
    const data = await getAdmins();
    setAdmins(data);
  };

  useEffect(() => {
    void (async () => {
      try {
        const [me, meRole] = await Promise.all([getMe(), getMyAdminRole()]);
        setUserName(me.name);
        setRole(meRole.role);
        if (meRole.role === "superadmin") {
          setAdmins(await getAdmins());
        }
      } catch (e) {
        toast.error(e instanceof Error ? e.message : "Не удалось загрузить доступы");
      } finally {
        setLoading(false);
      }
    })();
  }, []);

  const handleAddAdmin = async () => {
    const id = Number(newAdminId);
    if (!Number.isFinite(id) || id <= 0) {
      toast.error("Введите корректный user_id");
      return;
    }
    setAdminBusy(true);
    try {
      await addAdmin(id);
      toast.success("Админ добавлен");
      setNewAdminId("");
      await loadAdmins();
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Не удалось добавить админа");
    } finally {
      setAdminBusy(false);
    }
  };

  const handleRemoveAdmin = async (userId: number) => {
    setAdminBusy(true);
    try {
      await removeAdmin(userId);
      toast.success("Админ удалён");
      await loadAdmins();
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Не удалось удалить админа");
    } finally {
      setAdminBusy(false);
    }
  };

  const handleDraft = (draft: TemplateDraft) => {
    setTitle(draft.title);
    setDescription(draft.description);
    setSprintsJson(JSON.stringify(draft.sprints, null, 2));
    toast.success("Черновик готов, проверь и создавай шаблон");
  };

  const handleCreateTemplate = async () => {
    if (!title.trim() || !description.trim()) {
      toast.error("Заполните название и описание");
      return;
    }
    let parsedSprints: CreateProjectTemplatePayload["sprints"];
    try {
      const parsed = JSON.parse(sprintsJson) as unknown;
      if (!Array.isArray(parsed)) throw new Error();
      parsedSprints = parsed as CreateProjectTemplatePayload["sprints"];
    } catch {
      toast.error("Проверьте JSON в поле спринтов");
      return;
    }

    const payload: CreateProjectTemplatePayload = {
      project_template_id: null,
      title: title.trim(),
      description: description.trim(),
      direction: direction.trim(),
      level: level.trim(),
      sprints: parsedSprints,
    };

    setTemplateBusy(true);
    try {
      await createProjectTemplate(payload);
      toast.success("Шаблон проекта создан");
      setTitle("");
      setDescription("");
      setSprintsJson(JSON.stringify(sampleSprints, null, 2));
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Не удалось создать шаблон");
    } finally {
      setTemplateBusy(false);
    }
  };

  return (
    <WorkspaceShell adminRole={role} userName={userName}>
      <div className="mx-auto max-w-3xl px-5 py-8 sm:px-8 lg:py-10">
        <p className="font-mono text-[11px] text-primary">Служебное</p>
        <h1 className="mt-3 text-4xl leading-[1.1]">Админка</h1>
        <p className="mt-2 text-sm text-muted-foreground">
          Шаблоны спринтов и доступы. Сюда заходят только admin и superadmin.
        </p>

        {loading && <LoadingState label="Проверяем доступ…" />}

        {!loading && !canCreateTemplates && (
          <EmptyState
            kicker="403"
            title="Нет доступа"
            body="Панель только для admin и superadmin. Если это ошибка — попроси суперadmin выдать роль."
          />
        )}

        {!loading && canCreateTemplates && (
          <>
            <p className="mt-6 font-mono text-[11px] text-muted-foreground">
              Роль: {role}
            </p>

            <TemplateGenerator
              direction={direction}
              level={level}
              onDraft={handleDraft}
            />

            <section className="mt-6 rounded-[10px] border border-border bg-card p-6 sm:p-8">
              <h2 className="text-lg font-medium tracking-tight">Шаблон проекта</h2>
              <p className="mt-1 text-sm text-muted-foreground">
                JSON спринтов как в API: поле tests у задачи — скрытые тесты, студент их
                не видит. Направление и уровень — те же, что на онбординге, и генератор
                берёт их отсюда же.
              </p>
              <div className="mt-6 space-y-4">
                <Field
                  label="Название"
                  value={title}
                  onChange={(e) => setTitle(e.target.value)}
                />
                <Field
                  label="Описание"
                  value={description}
                  onChange={(e) => setDescription(e.target.value)}
                />
                <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
                  <label className="block space-y-2">
                    <span className="text-xs font-medium tracking-wide text-muted-foreground">
                      Направление
                    </span>
                    <select
                      value={direction}
                      onChange={(e) => setDirection(e.target.value)}
                      className={selectClass}
                    >
                      <option value="backend">Backend</option>
                      <option value="frontend">Frontend</option>
                      <option value="fullstack">Fullstack</option>
                    </select>
                  </label>
                  <label className="block space-y-2">
                    <span className="text-xs font-medium tracking-wide text-muted-foreground">
                      Уровень
                    </span>
                    <select
                      value={level}
                      onChange={(e) => setLevel(e.target.value)}
                      className={selectClass}
                    >
                      <option value="junior">Junior</option>
                      <option value="junior-plus">Junior+</option>
                    </select>
                  </label>
                </div>
                <label className="block space-y-2">
                  <span className="text-xs font-medium tracking-wide text-muted-foreground">
                    Спринты (JSON)
                  </span>
                  <textarea
                    value={sprintsJson}
                    onChange={(e) => setSprintsJson(e.target.value)}
                    className={cn(
                      fieldClass,
                      "block w-full min-h-[220px] h-auto py-3 font-mono text-[13px] leading-relaxed",
                    )}
                  />
                </label>
                {sprintsPreviewError && (
                  <p className="text-sm text-destructive">{sprintsPreviewError}</p>
                )}
                <PrimaryButton
                  type="button"
                  className="w-auto min-w-[180px]"
                  disabled={templateBusy || Boolean(sprintsPreviewError)}
                  onClick={() => void handleCreateTemplate()}
                >
                  {templateBusy ? "Создаём…" : "Создать шаблон"}
                </PrimaryButton>
              </div>
            </section>

            {canManageAdmins && (
              <section className="mt-6 rounded-[10px] border border-border bg-card p-6 sm:p-8">
                <h2 className="text-lg font-medium tracking-tight">Админы</h2>
                <p className="mt-1 text-sm text-muted-foreground">
                  Выдаёшь роль по user_id. Superadmin снять с себя нельзя.
                </p>
                <div className="mt-6 flex flex-col gap-3 sm:flex-row">
                  <Field
                    label="user_id"
                    value={newAdminId}
                    onChange={(e) => setNewAdminId(e.target.value)}
                    className="sm:min-w-[200px]"
                  />
                  <PrimaryButton
                    type="button"
                    className="w-auto shrink-0 sm:mt-7 sm:h-12"
                    disabled={adminBusy}
                    onClick={() => void handleAddAdmin()}
                  >
                    Добавить
                  </PrimaryButton>
                </div>
                <div className="mt-6 space-y-2">
                  {admins.length === 0 && (
                    <p className="py-6 text-sm text-muted-foreground">Пока никого нет в списке.</p>
                  )}
                  {admins.map((a) => (
                    <div
                      key={a.user_id}
                      className="flex items-center justify-between gap-3 rounded-xl border border-border px-4 py-3"
                    >
                      <p className="text-sm">
                        <span className="font-medium">{a.user_id}</span>
                        <span className="text-muted-foreground"> · {a.role}</span>
                      </p>
                      {a.role === "admin" && (
                        <button
                          type="button"
                          disabled={adminBusy}
                          onClick={() => void handleRemoveAdmin(a.user_id)}
                          className="inline-flex items-center gap-1.5 text-sm text-muted-foreground hover:text-destructive disabled:opacity-40"
                        >
                          <Trash2 className="size-3.5" />
                          Снять
                        </button>
                      )}
                    </div>
                  ))}
                </div>
              </section>
            )}
          </>
        )}
      </div>
    </WorkspaceShell>
  );
}
