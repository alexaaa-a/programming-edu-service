import { useState, type FormEvent } from "react";
import { useNavigate, Link } from "react-router";
import { toast } from "sonner";
import { OnboardingShell } from "../components/onboarding/OnboardingShell";
import { Field, PrimaryButton } from "../components/onboarding/Field";
import { getMe, loginUser } from "@/lib/api";
import { setTokens } from "@/lib/auth-storage";

export default function Login() {
  const navigate = useNavigate();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [loading, setLoading] = useState(false);

  const handleSubmit = async (e: FormEvent) => {
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
    <OnboardingShell
      aside={
        <>
          <p className="font-mono text-[11px] text-primary">
            Рабочий стол джуна
          </p>
          <h1 className="text-[2.75rem] leading-[1.12] xl:text-5xl">
            Команда, которая не прощает сырой код.
          </h1>
          <p className="text-[15px] leading-relaxed text-muted-foreground">
            Спринты, ревью и живой чат с агентами. Как стажировка — только с ментором,
            который не уходит в 18:00.
          </p>
        </>
      }
    >
      <h2 className="mb-1 text-2xl font-medium tracking-tight">Вход</h2>
      <p className="mb-8 text-sm text-muted-foreground">Продолжить симуляцию</p>

      <form onSubmit={handleSubmit} className="space-y-4">
        <Field
          label="Почта"
          type="email"
          name="email"
          autoComplete="email"
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          required
        />
        <Field
          label="Пароль"
          type="password"
          name="password"
          autoComplete="current-password"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          required
        />
        <PrimaryButton type="submit" disabled={loading} className="mt-2">
          {loading ? "Входим…" : "Войти"}
        </PrimaryButton>
      </form>

      <p className="mt-8 text-sm text-muted-foreground">
        Нет аккаунта?{" "}
        <Link to="/" className="text-foreground underline-offset-4 hover:text-primary hover:underline">
          Создать
        </Link>
      </p>
    </OnboardingShell>
  );
}
