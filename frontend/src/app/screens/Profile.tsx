import { useEffect, useState } from "react";
import { useNavigate } from "react-router";
import { ArrowLeft, KeyRound, Save, UserRound } from "lucide-react";
import { toast } from "sonner";
import { Button } from "../components/ui/button";
import { Input } from "../components/ui/input";
import { useRequireAuth } from "../hooks/useRequireAuth";
import { getMe, updateProfile } from "@/lib/api";
import type { UserShow } from "@/lib/types";

const DIRECTION_OPTIONS = [
  { value: "backend", label: "Бэкенд" },
  { value: "frontend", label: "Фронтенд" },
  { value: "fullstack", label: "Фулстек" },
] as const;

const LEVEL_OPTIONS = [
  { value: "junior", label: "Джуниор" },
  { value: "junior-plus", label: "Джуниор+" },
] as const;

const selectClass =
  "h-12 w-full rounded-[20px] border-2 border-[#FFE5EC] bg-white px-5 text-sm focus:border-[#FF9BB5] focus:outline-none transition-colors";

export default function Profile() {
  useRequireAuth();
  const navigate = useNavigate();

  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [form, setForm] = useState<UserShow>({
    username: "",
    name: "",
    surname: "",
    email: "",
    direction: null,
    level: null,
  });

  useEffect(() => {
    (async () => {
      try {
        const me = await getMe();
        setForm(me);
      } catch (e) {
        toast.error(e instanceof Error ? e.message : "Не удалось загрузить профиль");
      } finally {
        setLoading(false);
      }
    })();
  }, []);

  const onChange = (key: keyof UserShow, value: string) => {
    setForm((prev) => ({ ...prev, [key]: value }));
  };

  const handleSave = async (e: React.FormEvent) => {
    e.preventDefault();
    setSaving(true);
    try {
      await updateProfile({
        name: form.name.trim(),
        surname: form.surname.trim(),
        direction: form.direction || undefined,
        level: form.level || undefined,
      });
      toast.success("Профиль сохранен");
      navigate("/dashboard");
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Не удалось сохранить профиль");
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="min-h-screen p-6 md:p-12">
      <div className="max-w-3xl mx-auto">
        <div className="mb-6">
          <Button
            type="button"
            variant="outline"
            onClick={() => navigate("/dashboard")}
            className="rounded-[20px] border-2 border-[#FFE5EC] hover:bg-[#FFE5EC]"
          >
            <ArrowLeft className="w-4 h-4 mr-2" />
            Назад
          </Button>
        </div>

        <div className="bg-white rounded-[20px] p-8 md:p-10 shadow-lg">
          <div className="flex items-center gap-3 mb-6">
            <div className="w-12 h-12 rounded-full bg-gradient-to-r from-[#FF9BB5] to-[#FFC2D4] flex items-center justify-center">
              <UserRound className="w-6 h-6 text-white" />
            </div>
            <h1 className="text-2xl">Профиль пользователя</h1>
          </div>

          {loading ? (
            <p className="text-[#9E9E9E] py-8">Загружаем профиль…</p>
          ) : (
            <form onSubmit={handleSave} className="space-y-4">
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                <Input
                  value={form.name}
                  onChange={(e) => onChange("name", e.target.value)}
                  placeholder="Имя"
                  className="h-12 rounded-[20px] border-2 border-[#FFE5EC] bg-white px-5"
                  required
                />
                <Input
                  value={form.surname}
                  onChange={(e) => onChange("surname", e.target.value)}
                  placeholder="Фамилия"
                  className="h-12 rounded-[20px] border-2 border-[#FFE5EC] bg-white px-5"
                  required
                />
              </div>

              <Input
                value={form.username}
                placeholder="Никнейм"
                className="h-12 rounded-[20px] border-2 border-[#FFE5EC] bg-[#FAFAFA] px-5 text-[#9E9E9E]"
                disabled
              />

              <Input
                type="email"
                value={form.email}
                placeholder="Почта"
                className="h-12 rounded-[20px] border-2 border-[#FFE5EC] bg-[#FAFAFA] px-5 text-[#9E9E9E]"
                disabled
              />

              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                <select
                  value={form.direction ?? ""}
                  onChange={(e) => onChange("direction", e.target.value)}
                  className={selectClass}
                >
                  <option value="">Выберите направление</option>
                  {DIRECTION_OPTIONS.map((option) => (
                    <option key={option.value} value={option.value}>
                      {option.label}
                    </option>
                  ))}
                </select>
                <select
                  value={form.level ?? ""}
                  onChange={(e) => onChange("level", e.target.value)}
                  className={selectClass}
                >
                  <option value="">Выберите уровень</option>
                  {LEVEL_OPTIONS.map((option) => (
                    <option key={option.value} value={option.value}>
                      {option.label}
                    </option>
                  ))}
                </select>
              </div>

              <Button
                type="submit"
                disabled={saving}
                className="h-12 px-6 rounded-[20px] bg-gradient-to-r from-[#FF9BB5] to-[#FFC2D4] text-white"
              >
                <Save className="w-4 h-4 mr-2" />
                {saving ? "Сохраняем…" : "Сохранить изменения"}
              </Button>
              <Button
                type="button"
                variant="outline"
                onClick={() => navigate("/profile/password")}
                className="h-12 px-6 rounded-[20px] border-2 border-[#FFE5EC] hover:bg-[#FFE5EC] ml-3"
              >
                <KeyRound className="w-4 h-4 mr-2" />
                Сменить пароль
              </Button>
            </form>
          )}
        </div>
      </div>
    </div>
  );
}
