import { useState } from "react";
import { useNavigate } from "react-router";
import { ArrowLeft, KeyRound, Save } from "lucide-react";
import { toast } from "sonner";
import { Button } from "../components/ui/button";
import { Input } from "../components/ui/input";
import { useRequireAuth } from "../hooks/useRequireAuth";
import { changePassword } from "@/lib/api";

export default function ChangePassword() {
  useRequireAuth();
  const navigate = useNavigate();
  const [saving, setSaving] = useState(false);
  const [currentPassword, setCurrentPassword] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");

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
      toast.success("Пароль успешно изменен");
      navigate("/profile");
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Не удалось изменить пароль");
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="min-h-screen p-6 md:p-12">
      <div className="max-w-2xl mx-auto">
        <div className="mb-6">
          <Button
            type="button"
            variant="outline"
            onClick={() => navigate("/profile")}
            className="rounded-[20px] border-2 border-[#FFE5EC] hover:bg-[#FFE5EC]"
          >
            <ArrowLeft className="w-4 h-4 mr-2" />
            Назад к профилю
          </Button>
        </div>

        <div className="bg-white rounded-[20px] p-8 md:p-10 shadow-lg">
          <div className="flex items-center gap-3 mb-6">
            <div className="w-12 h-12 rounded-full bg-gradient-to-r from-[#FF9BB5] to-[#FFC2D4] flex items-center justify-center">
              <KeyRound className="w-6 h-6 text-white" />
            </div>
            <h1 className="text-2xl">Смена пароля</h1>
          </div>

          <form onSubmit={handleSave} className="space-y-4">
            <Input
              type="password"
              value={currentPassword}
              onChange={(e) => setCurrentPassword(e.target.value)}
              placeholder="Текущий пароль"
              className="h-12 rounded-[20px] border-2 border-[#FFE5EC] bg-white px-5"
              required
            />
            <Input
              type="password"
              value={newPassword}
              onChange={(e) => setNewPassword(e.target.value)}
              placeholder="Новый пароль"
              className="h-12 rounded-[20px] border-2 border-[#FFE5EC] bg-white px-5"
              required
            />
            <Input
              type="password"
              value={confirmPassword}
              onChange={(e) => setConfirmPassword(e.target.value)}
              placeholder="Подтвердите новый пароль"
              className="h-12 rounded-[20px] border-2 border-[#FFE5EC] bg-white px-5"
              required
            />
            <p className="text-xs text-[#9E9E9E]">Минимальная длина нового пароля: 8 символов.</p>

            <Button
              type="submit"
              disabled={saving}
              className="h-12 px-6 rounded-[20px] bg-gradient-to-r from-[#FF9BB5] to-[#FFC2D4] text-white"
            >
              <Save className="w-4 h-4 mr-2" />
              {saving ? "Сохраняем…" : "Изменить пароль"}
            </Button>
          </form>
        </div>
      </div>
    </div>
  );
}
