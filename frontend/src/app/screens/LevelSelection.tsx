import { useState } from "react";
import { useNavigate } from "react-router";
import { TrendingUp, Zap } from "lucide-react";
import { toast } from "sonner";
import { OnboardingShell } from "../components/onboarding/OnboardingShell";
import { ChoiceCard } from "../components/onboarding/ChoiceCard";
import { PrimaryButton } from "../components/onboarding/Field";
import { updateProfile } from "@/lib/api";
import { useRequireAuth } from "../hooks/useRequireAuth";

const API_VALUES = ["junior", "junior-plus"] as const;

const levels = [
  {
    id: "junior" as const,
    icon: TrendingUp,
    title: "Junior",
    description: "База, ясный бриф и ревью без гонки. Начни отсюда, если командная разработка ещё новая.",
  },
  {
    id: "junior-plus" as const,
    icon: Zap,
    title: "Junior+",
    description: "Жёстче критерии, больше дыр в требованиях. Как будто тебя уже не ведут за руку.",
  },
];

export default function LevelSelection() {
  useRequireAuth();
  const navigate = useNavigate();
  const [selected, setSelected] = useState<string>("");
  const [loading, setLoading] = useState(false);

  const handleStart = async () => {
    if (!selected || !API_VALUES.includes(selected as (typeof API_VALUES)[number])) {
      return;
    }
    setLoading(true);
    try {
      await updateProfile({ level: selected });
      toast.success("Уровень сохранён");
      navigate("/dashboard");
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Не удалось сохранить");
    } finally {
      setLoading(false);
    }
  };

  return (
    <OnboardingShell step={3} stepLabel="Шаг 3 из 3 · уровень">
      <p className="font-mono text-[11px] text-primary">
        Насколько жёстко
      </p>
      <h1 className="mt-3 max-w-2xl text-4xl leading-[1.12] sm:text-5xl">
        Выбери уровень
      </h1>
      <p className="mt-4 max-w-lg text-[15px] leading-relaxed text-muted-foreground">
        Уровень задаёт сложность симуляции — команда подстроится под выбор.
      </p>

      <div className="mt-12 grid grid-cols-1 gap-4 md:grid-cols-2">
        {levels.map((level) => (
          <ChoiceCard
            key={level.id}
            title={level.title}
            description={level.description}
            icon={level.icon}
            selected={selected === level.id}
            onSelect={() => setSelected(level.id)}
          />
        ))}
      </div>

      <div className="mt-10 max-w-xs">
        <PrimaryButton onClick={() => void handleStart()} disabled={!selected || loading}>
          {loading ? "Сохраняем…" : "Начать симуляцию"}
        </PrimaryButton>
      </div>
    </OnboardingShell>
  );
}
