import { useEffect, useState } from "react";
import { useNavigate } from "react-router";
import { toast } from "sonner";
import { useRequireAuth } from "../hooks/useRequireAuth";
import { getCareer, getMe, getMyAdminRole, updateProfile } from "@/lib/api";
import type { AdminRole, Career, UserShow } from "@/lib/types";
import { GRADE_LABEL, careerRights, formatRub } from "@/lib/career-rights";
import { BadgeGlyph } from "../components/BadgeGlyph";
import { WorkspaceShell } from "../components/workspace/WorkspaceShell";
import { Field, PrimaryButton, selectClass } from "../components/onboarding/Field";
import { LoadingState } from "../components/LoadingState";

const DIRECTION_OPTIONS = [
  { value: "backend", label: "Backend" },
  { value: "frontend", label: "Frontend" },
  { value: "fullstack", label: "Fullstack" },
] as const;

const LEVEL_OPTIONS = [
  { value: "junior", label: "Junior" },
  { value: "junior-plus", label: "Junior+" },
] as const;

export default function Profile() {
  useRequireAuth();
  const navigate = useNavigate();
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [adminRole, setAdminRole] = useState<AdminRole>("user");
  const [career, setCareer] = useState<Career | null>(null);
  const [openLetter, setOpenLetter] = useState(0);
  const [form, setForm] = useState<UserShow>({
    username: "",
    name: "",
    surname: "",
    email: "",
    direction: null,
    level: null,
  });

  useEffect(() => {
    void (async () => {
      try {
        const [me, role, careerState] = await Promise.all([
          getMe(),
          getMyAdminRole(),
          getCareer(),
        ]);
        setForm(me);
        setAdminRole(role.role);
        setCareer(careerState);
        setOpenLetter(Math.max(0, (careerState?.letters.length ?? 1) - 1));
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
      toast.success("Профиль сохранён");
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Не удалось сохранить профиль");
    } finally {
      setSaving(false);
    }
  };

  return (
    <WorkspaceShell adminRole={adminRole} userName={form.name || undefined}>
      <div className="mx-auto max-w-xl px-5 py-8 sm:px-8 lg:py-10">
        <p className="font-mono text-[11px] text-primary">Аккаунт</p>
        <h1 className="mt-3 text-4xl leading-[1.1]">Профиль</h1>
        <p className="mt-2 text-sm text-muted-foreground">
          Ник и почта фиксированы. Направление можно сменить — спринт останется текущий.
        </p>

        {loading ? (
          <LoadingState label="Загружаем профиль…" />
        ) : (
          <form onSubmit={handleSave} className="mt-10 space-y-4">
            <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
              <Field
                label="Имя"
                value={form.name}
                onChange={(e) => onChange("name", e.target.value)}
                required
              />
              <Field
                label="Фамилия"
                value={form.surname}
                onChange={(e) => onChange("surname", e.target.value)}
                required
              />
            </div>
            <Field label="Никнейм" value={form.username} disabled />
            <Field label="Почта" type="email" value={form.email} disabled />
            <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
              <label className="block space-y-2">
                <span className="text-xs font-medium tracking-wide text-muted-foreground">
                  Направление
                </span>
                <select
                  value={form.direction ?? ""}
                  onChange={(e) => onChange("direction", e.target.value)}
                  className={selectClass}
                >
                  <option value="">Не выбрано</option>
                  {DIRECTION_OPTIONS.map((option) => (
                    <option key={option.value} value={option.value}>
                      {option.label}
                    </option>
                  ))}
                </select>
              </label>
              <label className="block space-y-2">
                <span className="text-xs font-medium tracking-wide text-muted-foreground">
                  Уровень
                </span>
                <select
                  value={form.level ?? ""}
                  onChange={(e) => onChange("level", e.target.value)}
                  className={selectClass}
                >
                  <option value="">Не выбран</option>
                  {LEVEL_OPTIONS.map((option) => (
                    <option key={option.value} value={option.value}>
                      {option.label}
                    </option>
                  ))}
                </select>
              </label>
            </div>
            <div className="flex flex-wrap gap-3 pt-4">
              <PrimaryButton type="submit" disabled={saving} className="w-auto min-w-[180px]">
                {saving ? "Сохраняем…" : "Сохранить"}
              </PrimaryButton>
              <button
                type="button"
                onClick={() => navigate("/profile/password")}
                className="h-12 px-4 text-sm text-muted-foreground hover:text-foreground"
              >
                Сменить пароль
              </button>
            </div>
          </form>
        )}

        {!loading && career && (career.badges?.length ?? 0) > 0 && (
          <section className="mt-14 border-t border-border pt-10">
            <p className="font-mono text-[11px] text-primary">Полка</p>
            <h2 className="mt-3 text-3xl">Бейджи</h2>
            <p className="mt-2 max-w-xl text-sm text-muted-foreground">
              Выдаются за закрытые задачи и события спринта. Собрано{" "}
              {career.badges!.length} из {career.badge_total ?? career.badges!.length}.
            </p>
            <ul className="mt-6 grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-4">
              {career.badges!.map((badge) => (
                <li
                  key={badge.id}
                  className="rounded-[10px] border border-primary/30 bg-primary/5 p-4"
                >
                  <BadgeGlyph id={badge.id} className="size-4 text-primary" />
                  <p className="mt-2 text-sm leading-snug">{badge.title}</p>
                  <p className="mt-1 text-xs leading-relaxed text-muted-foreground">
                    {badge.hint}
                  </p>
                  <p className="mt-2 font-mono text-[10px] text-muted-foreground">
                    {new Date(badge.at).toLocaleDateString("ru-RU")}
                  </p>
                </li>
              ))}
            </ul>
          </section>
        )}

        {!loading && careerRights(career?.grade).reopenLetter && (career?.letters.length ?? 0) > 0 && (
          <section className="mt-14 border-t border-border pt-10">
            <p className="font-mono text-[11px] text-primary">Performance review</p>
            <h2 className="mt-3 text-3xl">Письма Джона</h2>
            <div className="mt-4 flex flex-wrap gap-2">
              {career!.letters.map((letter, index) => (
                <button
                  key={`${letter.at}-${index}`}
                  type="button"
                  onClick={() => setOpenLetter(index)}
                  className={
                    openLetter === index
                      ? "rounded-full border border-primary/40 px-3 py-1 text-xs text-primary"
                      : "rounded-full border border-border px-3 py-1 text-xs text-muted-foreground"
                  }
                >
                  {new Date(letter.at).toLocaleDateString("ru-RU")}
                </button>
              ))}
            </div>
            {career!.letters[openLetter] && (
              <div className="mt-6">
                <p className="font-display text-3xl leading-none">
                  {formatRub(career!.letters[openLetter].old_salary)}
                  <span className="mx-3 text-muted-foreground">→</span>
                  {formatRub(career!.letters[openLetter].new_salary)}
                </p>
                <p className="mt-2 text-sm text-muted-foreground">
                  {GRADE_LABEL[career!.letters[openLetter].old_grade] ?? career!.letters[openLetter].old_grade}
                  {" → "}
                  {GRADE_LABEL[career!.letters[openLetter].new_grade] ?? career!.letters[openLetter].new_grade}
                </p>
                <ul className="mt-6 space-y-2">
                  {career!.letters[openLetter].facts.map((fact) => (
                    <li key={fact} className="text-sm leading-relaxed">
                      {fact}
                    </li>
                  ))}
                </ul>
                <p className="mt-6 text-sm leading-relaxed text-muted-foreground">
                  {career!.letters[openLetter].text}
                </p>
              </div>
            )}
          </section>
        )}
      </div>
    </WorkspaceShell>
  );
}
