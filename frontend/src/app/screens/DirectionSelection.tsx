import { useState } from "react";
import { useNavigate } from "react-router";
import { Server, Monitor, Layers } from "lucide-react";
import { toast } from "sonner";
import { OnboardingShell } from "../components/onboarding/OnboardingShell";
import { ChoiceCard } from "../components/onboarding/ChoiceCard";
import { PrimaryButton } from "../components/onboarding/Field";
import { updateProfile } from "@/lib/api";
import { useRequireAuth } from "../hooks/useRequireAuth";

const API_VALUES = ["backend", "frontend", "fullstack"] as const;

const directions = [
  {
    id: "backend" as const,
    icon: Server,
    title: "Backend",
    description: "API, данные, ошибки и то, что держит продукт.",
  },
  {
    id: "frontend" as const,
    icon: Monitor,
    title: "Frontend",
    description: "Интерфейс, состояние и аккуратная работа с API.",
  },
  {
    id: "fullstack" as const,
    icon: Layers,
    title: "Fullstack",
    description: "Весь контур: от хендлера до кнопки.",
  },
];

export default function DirectionSelection() {
  useRequireAuth();
  const navigate = useNavigate();
  const [selected, setSelected] = useState<string>("");
  const [loading, setLoading] = useState(false);

  const handleContinue = async () => {
    if (!selected || !API_VALUES.includes(selected as (typeof API_VALUES)[number])) {
      return;
    }
    setLoading(true);
    try {
      await updateProfile({ direction: selected });
      toast.success("Направление сохранено");
      navigate("/level");
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Не удалось сохранить");
    } finally {
      setLoading(false);
    }
  };

  return (
    <OnboardingShell step={2} stepLabel="Шаг 2 из 3 · роль">
      <p className="font-mono text-[11px] text-primary">
        Куда ты идёшь
      </p>
      <h1 className="mt-3 max-w-2xl text-4xl leading-[1.12] sm:text-5xl">
        Выбери направление
      </h1>
      <p className="mt-4 max-w-lg text-[15px] leading-relaxed text-muted-foreground">
        От этого зависят проекты и то, как команда будет тебя вести. Поменять можно позже в профиле.
      </p>

      <div className="mt-12 grid grid-cols-1 gap-4 md:grid-cols-3">
        {directions.map((direction) => (
          <ChoiceCard
            key={direction.id}
            title={direction.title}
            description={direction.description}
            icon={direction.icon}
            selected={selected === direction.id}
            onSelect={() => setSelected(direction.id)}
          />
        ))}
      </div>

      <div className="mt-10 max-w-xs">
        <PrimaryButton onClick={() => void handleContinue()} disabled={!selected || loading}>
          {loading ? "Сохраняем…" : "Продолжить"}
        </PrimaryButton>
      </div>
    </OnboardingShell>
  );
}
