import { useNavigate } from "react-router";
import { TrendingUp, Zap } from "lucide-react";
import { Button } from "../components/ui/button";
import { useState } from "react";
import { toast } from "sonner";
import { updateProfile } from "@/lib/api";
import { useRequireAuth } from "../hooks/useRequireAuth";

const API_VALUES = ["junior", "junior-plus"] as const;

export default function LevelSelection() {
  useRequireAuth();
  const navigate = useNavigate();
  const [selected, setSelected] = useState<string>("");
  const [loading, setLoading] = useState(false);

  const levels = [
    {
      id: "junior" as const,
      icon: TrendingUp,
      title: "Джуниор",
      description: "Начните путь с базовых задач",
      gradient: "from-[#FFE5EC] to-[#FFC2D4]",
    },
    {
      id: "junior-plus" as const,
      icon: Zap,
      title: "Джуниор+",
      description: "Беритесь за более сложные проекты",
      gradient: "from-[#FFC2D4] to-[#FF9BB5]",
    },
  ];

  const handleStartSimulation = async () => {
    if (!selected || !API_VALUES.includes(selected as (typeof API_VALUES)[number])) {
      return;
    }
    setLoading(true);
    try {
      await updateProfile({ level: selected });
      toast.success("Уровень сохранен");
      navigate("/dashboard");
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Не удалось сохранить");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen flex items-center justify-center p-6">
      <div className="w-full max-w-2xl">
        <div className="text-center mb-8">
          <p className="text-sm text-[#9E9E9E]">Шаг 3 из 3</p>
        </div>

        <h1 className="text-center mb-12 text-3xl">Выберите уровень</h1>

        <div className="grid grid-cols-1 md:grid-cols-2 gap-6 mb-12">
          {levels.map((level) => {
            const Icon = level.icon;
            const isSelected = selected === level.id;

            return (
              <button
                key={level.id}
                type="button"
                onClick={() => setSelected(level.id)}
                className={`bg-gradient-to-br ${level.gradient} rounded-[20px] p-10 transition-all shadow-md hover:shadow-lg ${
                  isSelected ? "ring-4 ring-[#FF9BB5] ring-offset-2 scale-105" : ""
                }`}
              >
                <div className="w-16 h-16 bg-white rounded-full flex items-center justify-center mx-auto mb-4">
                  <Icon className="w-8 h-8 text-[#FF9BB5]" />
                </div>
                <h3 className="text-xl mb-2 text-white">{level.title}</h3>
                <p className="text-sm text-white/90">{level.description}</p>
              </button>
            );
          })}
        </div>

        <div className="flex justify-center">
          <Button
            onClick={handleStartSimulation}
            disabled={!selected || loading}
            className="h-14 px-12 rounded-[20px] bg-gradient-to-r from-[#FF9BB5] to-[#FFC2D4] hover:from-[#FF8AAA] hover:to-[#FFB1C9] text-white text-lg shadow-md disabled:opacity-50 disabled:cursor-not-allowed"
          >
            {loading ? "Сохраняем…" : "Начать симуляцию"}
          </Button>
        </div>
      </div>
    </div>
  );
}
