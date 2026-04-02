import { useNavigate } from "react-router";
import { Server, Monitor, Layers } from "lucide-react";
import { Button } from "../components/ui/button";
import { useState } from "react";
import { toast } from "sonner";
import { updateProfile } from "@/lib/api";
import { useRequireAuth } from "../hooks/useRequireAuth";

const API_VALUES = ["backend", "frontend", "fullstack"] as const;

export default function DirectionSelection() {
  useRequireAuth();
  const navigate = useNavigate();
  const [selected, setSelected] = useState<string>("");
  const [loading, setLoading] = useState(false);

  const directions = [
    {
      id: "backend" as const,
      icon: Server,
      title: "Бэкенд",
      description: "Работа с серверами, базами данных и API",
    },
    {
      id: "frontend" as const,
      icon: Monitor,
      title: "Фронтенд",
      description: "Создание интерфейсов и пользовательского опыта",
    },
    {
      id: "fullstack" as const,
      icon: Layers,
      title: "Фулстек",
      description: "Развитие во фронтенде и бэкенде",
    },
  ];

  const handleПродолжить = async () => {
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
    <div className="min-h-screen flex items-center justify-center p-6">
      <div className="w-full max-w-3xl">
        <div className="text-center mb-8">
          <p className="text-sm text-[#9E9E9E]">Шаг 2 из 3</p>
        </div>

        <h1 className="text-center mb-12 text-3xl">Выберите направление</h1>

        <div className="grid grid-cols-1 md:grid-cols-3 gap-6 mb-8">
          {directions.map((direction) => {
            const Icon = direction.icon;
            const isSelected = selected === direction.id;

            return (
              <button
                key={direction.id}
                type="button"
                onClick={() => setSelected(direction.id)}
                className={`bg-white rounded-[20px] p-8 transition-all shadow-md hover:shadow-lg ${
                  isSelected ? "ring-4 ring-[#FF9BB5] ring-offset-2" : ""
                }`}
              >
                <div
                  className={`w-16 h-16 rounded-full flex items-center justify-center mx-auto mb-4 ${
                    isSelected
                      ? "bg-gradient-to-br from-[#FF9BB5] to-[#FFC2D4]"
                      : "bg-[#FFE5EC]"
                  }`}
                >
                  <Icon
                    className={`w-8 h-8 ${isSelected ? "text-white" : "text-[#FF9BB5]"}`}
                  />
                </div>
                <h3 className="text-xl mb-2">{direction.title}</h3>
                <p className="text-sm text-[#9E9E9E]">{direction.description}</p>
              </button>
            );
          })}
        </div>

        <div className="flex justify-center">
          <Button
            onClick={handleПродолжить}
            disabled={!selected || loading}
            className="h-14 px-12 rounded-[20px] bg-gradient-to-r from-[#FF9BB5] to-[#FFC2D4] hover:from-[#FF8AAA] hover:to-[#FFB1C9] text-white text-lg shadow-md disabled:opacity-50 disabled:cursor-not-allowed"
          >
            {loading ? "Сохраняем…" : "Продолжить"}
          </Button>
        </div>
      </div>
    </div>
  );
}
