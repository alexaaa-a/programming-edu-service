import { useState } from "react";
import { useNavigate, Link } from "react-router";
import { Code2 } from "lucide-react";
import { toast } from "sonner";
import { Input } from "../components/ui/input";
import { Button } from "../components/ui/button";
import { getMe, loginUser } from "@/lib/api";
import { setTokens } from "@/lib/auth-storage";

export default function Login() {
  const navigate = useNavigate();
  const [email, setПочта] = useState("");
  const [password, setПароль] = useState("");
  const [loading, setLoading] = useState(false);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true);
    try {
      const tokens = await loginUser({ email, password });
      setTokens(tokens.access_token, tokens.refresh_token);
      const me = await getMe();
      toast.success("С возвращением");
      if (me.direction && me.level) {
        navigate("/dashboard", { replace: true });
      } else {
        navigate("/direction", { replace: true });
      }
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Не удалось войти");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen flex items-center justify-center p-6">
      <div className="w-full max-w-md">
        <div className="bg-white rounded-[20px] p-8 shadow-lg">
          <div className="flex justify-center mb-6">
            <div className="w-16 h-16 bg-gradient-to-br from-[#FF9BB5] to-[#FFC2D4] rounded-full flex items-center justify-center">
              <Code2 className="w-8 h-8 text-white" />
            </div>
          </div>

          <h1 className="text-center mb-8 text-2xl">Вход 💻</h1>

          <form onSubmit={handleSubmit} className="space-y-5">
            <div>
              <Input
                type="email"
                placeholder="Почта"
                value={email}
                onChange={(e) => setПочта(e.target.value)}
                className="h-14 rounded-[20px] border-2 border-[#FFE5EC] bg-white px-5 focus:border-[#FF9BB5] transition-colors"
                required
              />
            </div>
            <div>
              <Input
                type="password"
                placeholder="Пароль"
                value={password}
                onChange={(e) => setПароль(e.target.value)}
                className="h-14 rounded-[20px] border-2 border-[#FFE5EC] bg-white px-5 focus:border-[#FF9BB5] transition-colors"
                required
              />
            </div>

            <Button
              type="submit"
              disabled={loading}
              className="w-full h-14 rounded-[20px] bg-gradient-to-r from-[#FF9BB5] to-[#FFC2D4] hover:from-[#FF8AAA] hover:to-[#FFB1C9] text-white text-lg shadow-md transition-all"
            >
              {loading ? "Подождите…" : "Войти"}
            </Button>
          </form>

          <div className="text-center mt-6">
            <Link
              to="/"
              className="text-sm text-[#9E9E9E] hover:text-[#FF9BB5] transition-colors"
            >
              Создать аккаунт
            </Link>
          </div>
        </div>
      </div>
    </div>
  );
}
