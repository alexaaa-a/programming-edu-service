import { useEffect, useState } from "react";
import { useNavigate } from "react-router";
import { toast } from "sonner";
import { useRequireAuth } from "../hooks/useRequireAuth";
import { changePassword, getMe, getMyAdminRole } from "@/lib/api";
import type { AdminRole } from "@/lib/types";
import { WorkspaceShell } from "../components/workspace/WorkspaceShell";
import { Field, PrimaryButton } from "../components/onboarding/Field";

export default function ChangePassword() {
  useRequireAuth();
  const navigate = useNavigate();
  const [saving, setSaving] = useState(false);
  const [userName, setUserName] = useState<string | undefined>();
  const [adminRole, setAdminRole] = useState<AdminRole>("user");
  const [currentPassword, setCurrentPassword] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");

  useEffect(() => {
    void (async () => {
      try {
        const [me, role] = await Promise.all([getMe(), getMyAdminRole()]);
        setUserName(me.name);
        setAdminRole(role.role);
      } catch {
        /* rail still works */
      }
    })();
  }, []);

  const handleSave = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!currentPassword.trim()) {
      toast.error("Введите текущий пароль");
      return;
    }
    if (newPassword.length < 8) {
      toast.error("Новый пароль должен быть не короче 8 символов");
      return;
    }
    if (newPassword !== confirmPassword) {
      toast.error("Новый пароль и подтверждение не совпадают");
      return;
    }

    setSaving(true);
    try {
      await changePassword({
        current_password: currentPassword,
        new_password: newPassword,
      });
      toast.success("Пароль изменён");
      navigate("/profile");
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Не удалось изменить пароль");
    } finally {
      setSaving(false);
    }
  };

  return (
    <WorkspaceShell adminRole={adminRole} userName={userName}>
      <div className="mx-auto max-w-xl px-5 py-8 sm:px-8 lg:py-10">
        <p className="font-mono text-[11px] text-primary">Аккаунт</p>
        <h1 className="mt-3 text-4xl leading-[1.1]">Смена пароля</h1>
        <p className="mt-2 text-sm text-muted-foreground">Минимум 8 символов. Сессии не сбрасываем.</p>

        <form onSubmit={handleSave} className="mt-10 space-y-4">
          <Field
            label="Текущий пароль"
            type="password"
            value={currentPassword}
            onChange={(e) => setCurrentPassword(e.target.value)}
            required
          />
          <Field
            label="Новый пароль"
            type="password"
            value={newPassword}
            onChange={(e) => setNewPassword(e.target.value)}
            required
          />
          <Field
            label="Ещё раз"
            type="password"
            value={confirmPassword}
            onChange={(e) => setConfirmPassword(e.target.value)}
            required
          />
          <div className="flex flex-wrap gap-3 pt-4">
            <PrimaryButton type="submit" disabled={saving} className="w-auto min-w-[180px]">
              {saving ? "Сохраняем…" : "Изменить пароль"}
            </PrimaryButton>
            <button
              type="button"
              onClick={() => navigate("/profile")}
              className="h-12 px-4 text-sm text-muted-foreground hover:text-foreground"
            >
              Назад к профилю
            </button>
          </div>
        </form>
      </div>
    </WorkspaceShell>
  );
}
