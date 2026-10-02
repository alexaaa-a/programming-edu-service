import { useLayoutEffect } from "react";
import { Outlet, useNavigate } from "react-router";
import { setAppNavigate } from "@/lib/app-navigate";
import { BadgeUnlocks } from "./components/BadgeUnlocks";

export default function AppShell() {
  const navigate = useNavigate();
  useLayoutEffect(() => {
    setAppNavigate(navigate);
  }, [navigate]);
  return (
    <>
      <Outlet />
      <BadgeUnlocks />
    </>
  );
}
