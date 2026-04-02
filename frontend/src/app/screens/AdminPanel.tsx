import { useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router";
import { ArrowLeft, Shield, UserPlus, Trash2, PlusSquare } from "lucide-react";
import { toast } from "sonner";
import { Button } from "../components/ui/button";
import { Input } from "../components/ui/input";
import { useRequireAuth } from "../hooks/useRequireAuth";
import {
  addAdmin,
  createProjectTemplate,
  getAdmins,
  getMyAdminRole,
  removeAdmin,
} from "@/lib/api";
import type { AdminRole, AdminUser, CreateProjectTemplatePayload } from "@/lib/types";

const sampleSprints = [
  {
    order: 1,
    title: "Спринт 1",
    tasks: [
      { title: "Настроить проект", description: "Создать базовую структуру и README" },
    ],
  },
];

export default function AdminPanel() {
  useRequireAuth();
  const navigate = useNavigate();

  const [role, setRole] = useState<AdminRole>("user");
  const [loading, setLoading] = useState(true);

  const [admins, setAdmins] = useState<AdminUser[]>([]);
  const [newAdminId, setNewAdminId] = useState("");
  const [adminBusy, setAdminBusy] = useState(false);

  const [title, setTitle] = useState("");
  const [description, setDescription] = useState("");
  const [direction, setDirection] = useState("backend");
  const [level, setLevel] = useState("junior");
  const [sprintsJson, setSprintsJson] = useState(
    JSON.stringify(sampleSprints, null, 2),
  );
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
    if (!canManageAdmins) return;
    const data = await getAdmins();
    setAdmins(data);
  };

  useEffect(() => {
    (async () => {
      try {
        const meRole = await getMyAdminRole();
        setRole(meRole.role);
        if (meRole.role === "superadmin") {
          await loadAdmins();
        }
      } catch (e) {
        toast.error(e instanceof Error ? e.message : "Не удалось загрузить доступы");
      } finally {
        setLoading(false);
      }
    })();
  }, [canManageAdmins]);

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
      toast.success("Админ удален");
      await loadAdmins();
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Не удалось удалить админа");
    } finally {
      setAdminBusy(false);
    }
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

  if (loading) {
    return (
      <div className="min-h-screen flex items-center justify-center text-[#9E9E9E]">
        Загружаем админ-панель…
      </div>
    );
  }

  if (!canCreateTemplates) {
    return (
      <div className="min-h-screen p-6 md:p-12">
        <div className="max-w-3xl mx-auto">
          <Button
            type="button"
            variant="outline"
            onClick={() => navigate("/dashboard")}
            className="mb-6 rounded-[20px] border-2 border-[#FFE5EC] hover:bg-[#FFE5EC]"
          >
            <ArrowLeft className="w-4 h-4 mr-2" />
            Назад
          </Button>
          <div className="bg-white rounded-[20px] p-8 shadow-lg text-center">
            <Shield className="w-10 h-10 text-[#FF9BB5] mx-auto mb-3" />
            <h2 className="text-2xl mb-2">Нет доступа</h2>
            <p className="text-[#9E9E9E]">
              Админ-панель доступна только пользователям с ролью admin или superadmin.
            </p>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen p-6 md:p-12">
      <div className="max-w-4xl mx-auto">
        <div className="flex items-center justify-between mb-6 flex-wrap gap-3">
          <Button
            type="button"
            variant="outline"
            onClick={() => navigate("/dashboard")}
            className="rounded-[20px] border-2 border-[#FFE5EC] hover:bg-[#FFE5EC]"
          >
            <ArrowLeft className="w-4 h-4 mr-2" />
            Назад
          </Button>
          <div className="px-4 py-2 rounded-full bg-[#FFF5F8] text-[#FF9BB5] text-sm">
            Ваша роль: {role}
          </div>
        </div>

        <div className="bg-white rounded-[20px] p-8 shadow-lg mb-8">
          <div className="flex items-center gap-2 mb-6">
            <PlusSquare className="w-5 h-5 text-[#FF9BB5]" />
            <h2 className="text-2xl">Создание шаблона задач</h2>
          </div>

          <div className="space-y-4">
            <Input
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              placeholder="Название шаблона"
              className="h-12 rounded-[20px] border-2 border-[#FFE5EC] bg-white px-5"
            />
            <Input
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              placeholder="Описание проекта"
              className="h-12 rounded-[20px] border-2 border-[#FFE5EC] bg-white px-5"
            />

            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              <Input
                value={direction}
                onChange={(e) => setDirection(e.target.value)}
                placeholder="direction (например backend)"
                className="h-12 rounded-[20px] border-2 border-[#FFE5EC] bg-white px-5"
              />
              <Input
                value={level}
                onChange={(e) => setLevel(e.target.value)}
                placeholder="level (например junior)"
                className="h-12 rounded-[20px] border-2 border-[#FFE5EC] bg-white px-5"
              />
            </div>

            <textarea
              value={sprintsJson}
              onChange={(e) => setSprintsJson(e.target.value)}
              className="w-full min-h-[220px] rounded-[20px] border-2 border-[#FFE5EC] bg-white px-5 py-4 focus:outline-none focus:border-[#FF9BB5] transition-colors"
            />
            {sprintsPreviewError && (
              <p className="text-sm text-red-500">{sprintsPreviewError}</p>
            )}

            <Button
              type="button"
              disabled={templateBusy || Boolean(sprintsPreviewError)}
              onClick={() => void handleCreateTemplate()}
              className="h-12 px-6 rounded-[20px] bg-gradient-to-r from-[#FF9BB5] to-[#FFC2D4] text-white"
            >
              {templateBusy ? "Создаем…" : "Создать шаблон"}
            </Button>
          </div>
        </div>

        {canManageAdmins && (
          <div className="bg-white rounded-[20px] p-8 shadow-lg">
            <div className="flex items-center gap-2 mb-6">
              <UserPlus className="w-5 h-5 text-[#FF9BB5]" />
              <h2 className="text-2xl">Управление админами</h2>
            </div>

            <div className="flex gap-3 mb-6">
              <Input
                value={newAdminId}
                onChange={(e) => setNewAdminId(e.target.value)}
                placeholder="user_id пользователя"
                className="h-12 rounded-[20px] border-2 border-[#FFE5EC] bg-white px-5"
              />
              <Button
                type="button"
                disabled={adminBusy}
                onClick={() => void handleAddAdmin()}
                className="h-12 px-6 rounded-[20px] bg-gradient-to-r from-[#FF9BB5] to-[#FFC2D4] text-white"
              >
                Добавить
              </Button>
            </div>

            <div className="space-y-3">
              {admins.map((a) => (
                <div
                  key={a.user_id}
                  className="flex items-center justify-between bg-[#FFF5F8] rounded-[16px] px-4 py-3"
                >
                  <p className="text-sm">
                    user_id: <span className="font-medium">{a.user_id}</span> · роль:{" "}
                    <span className="font-medium">{a.role}</span>
                  </p>
                  {a.role === "admin" && (
                    <Button
                      type="button"
                      variant="outline"
                      disabled={adminBusy}
                      onClick={() => void handleRemoveAdmin(a.user_id)}
                      className="h-10 rounded-[16px] border-2 border-[#FFE5EC] hover:bg-[#FFE5EC]"
                    >
                      <Trash2 className="w-4 h-4 mr-1" />
                      Удалить
                    </Button>
                  )}
                </div>
              ))}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
