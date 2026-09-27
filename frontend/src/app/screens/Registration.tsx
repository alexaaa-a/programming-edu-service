import { useState, type FormEvent } from "react";
import { useNavigate, Link } from "react-router";
import { toast } from "sonner";
import { OnboardingShell } from "../components/onboarding/OnboardingShell";
import { Field, PrimaryButton } from "../components/onboarding/Field";
import { registerUser } from "@/lib/api";
import { setTokens } from "@/lib/auth-storage";

export default function Registration() {
  const navigate = useNavigate();
  const [name, setName] = useState("");
  const [surname, setSurname] = useState("");
  const [username, setUsername] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [loading, setLoading] = useState(false);

  const handleSubmit = async (e: FormEvent) => {
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
    <OnboardingShell
      aside={
        <>
          <p className="font-mono text-[11px] text-primary">
            Шаг 1 · аккаунт
          </p>
          <h1 className="text-[2.75rem] leading-[1.12] xl:text-5xl">
            Начни как в настоящей команде.
          </h1>
          <p className="text-[15px] leading-relaxed text-muted-foreground">
            Спринт, доска задач и ревью от команды — всё как на первой работе. Для начала расскажи, кто ты.
          </p>
        </>
      }
    >
      <h2 className="mb-1 text-2xl font-medium tracking-tight">Регистрация</h2>
      <p className="mb-8 text-sm text-muted-foreground">Минута, и ты в команде</p>

      <form onSubmit={handleSubmit} className="space-y-4">
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
          <Field
            label="Имя"
            type="text"
            name="name"
            autoComplete="given-name"
            value={name}
            onChange={(e) => setName(e.target.value)}
            required
            minLength={2}
          />
          <Field
            label="Фамилия"
            type="text"
            name="surname"
            autoComplete="family-name"
            value={surname}
            onChange={(e) => setSurname(e.target.value)}
            required
            minLength={2}
          />
        </div>
        <Field
          label="Никнейм"
          type="text"
          name="username"
          autoComplete="username"
          value={username}
          onChange={(e) => setUsername(e.target.value)}
          required
          minLength={2}
          maxLength={30}
        />
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
          autoComplete="new-password"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          required
          minLength={8}
          maxLength={64}
        />
        <PrimaryButton type="submit" disabled={loading} className="mt-2">
          {loading ? "Создаём…" : "Продолжить"}
        </PrimaryButton>
      </form>

      <p className="mt-8 text-sm text-muted-foreground">
        Уже есть аккаунт?{" "}
        <Link to="/login" className="text-foreground underline-offset-4 hover:text-primary hover:underline">
          Войти
        </Link>
      </p>
    </OnboardingShell>
  );
}
