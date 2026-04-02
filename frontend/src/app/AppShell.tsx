import { useLayoutEffect } from "react";
import { Outlet, useNavigate } from "react-router";
import { setAppNavigate } from "@/lib/app-navigate";

export default function AppShell() {
  const navigate = useNavigate();
  useLayoutEffect(() => {
    setAppNavigate(navigate);
  }, [navigate]);
  return <Outlet />;
}
