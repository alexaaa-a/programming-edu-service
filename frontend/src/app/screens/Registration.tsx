import { useState } from "react";
import { useNavigate, Link } from "react-router";
import { Code2 } from "lucide-react";
import { toast } from "sonner";
import { Input } from "../components/ui/input";
import { Button } from "../components/ui/button";
import { registerUser } from "@/lib/api";
import { setTokens } from "@/lib/auth-storage";

export default function Registration() {
  const navigate = useNavigate();
  const [name, setName] = useState("");
  const [surname, setSurname] = useState("");
  const [username, setНикнейм] = useState("");
  const [email, setПочта] = useState("");
  const [password, setPassword] = useState("");
  const [loading, setLoading] = useState(false);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true);
    try {
      const tokens = await registerUser({
        name,
        surname,
        username,
        email,
        password,
      });
      setTokens(tokens.access_token, tokens.refresh_token);
      toast.success("Аккаунт создан");
      navigate("/direction");
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Не удалось зарегистрироваться");
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

          <h1 className="text-center mb-8 text-2xl">
            Добро пожаловать в ваше dev-путешествие 💻
          </h1>

          <form onSubmit={handleSubmit} className="space-y-5">
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
              <Input
                type="text"
                placeholder="Имя"
                value={name}
                onChange={(e) => setName(e.target.value)}
                className="h-14 rounded-[20px] border-2 border-[#FFE5EC] bg-white px-5 focus:border-[#FF9BB5] transition-colors"
                required
                minLength={2}
              />
              <Input
                type="text"
                placeholder="Фамилия"
                value={surname}
                onChange={(e) => setSurname(e.target.value)}
                className="h-14 rounded-[20px] border-2 border-[#FFE5EC] bg-white px-5 focus:border-[#FF9BB5] transition-colors"
                required
                minLength={2}
              />
            </div>
            <div>
              <Input
                type="text"
                placeholder="Никнейм"
                value={username}
                onChange={(e) => setНикнейм(e.target.value)}
                className="h-14 rounded-[20px] border-2 border-[#FFE5EC] bg-white px-5 focus:border-[#FF9BB5] transition-colors"
                required
                minLength={2}
                maxLength={30}
              />
            </div>
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
                placeholder="Пароль (минимум 8 символов)"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                className="h-14 rounded-[20px] border-2 border-[#FFE5EC] bg-white px-5 focus:border-[#FF9BB5] transition-colors"
                required
                minLength={8}
                maxLength={64}
              />
            </div>

            <Button
              type="submit"
              disabled={loading}
              className="w-full h-14 rounded-[20px] bg-gradient-to-r from-[#FF9BB5] to-[#FFC2D4] hover:from-[#FF8AAA] hover:to-[#FFB1C9] text-white text-lg shadow-md transition-all"
            >
              {loading ? "Подождите…" : "Начать"}
            </Button>
          </form>

          <div className="text-center mt-6">
            <Link
              to="/login"
              className="text-sm text-[#9E9E9E] hover:text-[#FF9BB5] transition-colors"
            >
              Уже есть аккаунт?
            </Link>
          </div>
        </div>
      </div>
    </div>
  );
}
