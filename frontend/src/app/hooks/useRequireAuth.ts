import { useEffect } from "react";
import { useNavigate } from "react-router";
import { isAuthenticated } from "@/lib/auth-storage";

export function useRequireAuth(): void {
  const navigate = useNavigate();
  useEffect(() => {
    if (!isAuthenticated()) {
      navigate("/login", { replace: true });
    }
  }, [navigate]);
}
