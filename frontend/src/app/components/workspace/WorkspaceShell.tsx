import { useEffect, useState, type ReactNode } from "react";
import { NavLink, useLocation, useNavigate } from "react-router";
import {
  LayoutGrid,
  Home,
  MessageCircle,
  BarChart3,
  UserRound,
  Shield,
  LogOut,
  Sparkles,
  Menu,
  X,
} from "lucide-react";
import { BrandMark } from "../brand/BrandMark";
import { cn } from "../ui/utils";
import { logoutRemote } from "@/lib/api";
import { touchStreak } from "@/lib/streak";
import type { AdminRole } from "@/lib/types";

const nav = [
  { to: "/dashboard", label: "Сегодня", icon: Home, hash: undefined as string | undefined },
  { to: "/dashboard#board", label: "Доска", icon: LayoutGrid, hash: "board" },
  { to: "/dashboard#path", label: "Путь", icon: Sparkles, hash: "path" },
  { to: "/chat", label: "Команда", icon: MessageCircle, hash: undefined },
  { to: "/statistics", label: "Прогресс", icon: BarChart3, hash: undefined },
];

const mobileNav = nav.filter((item) => item.hash !== "path");

function navActive(item: (typeof nav)[number], pathname: string, hash: string) {
  const onDashboard = pathname === "/dashboard";
  if (item.hash) return onDashboard && hash === item.hash;
  if (item.to === "/dashboard") return onDashboard && !hash;
  return pathname === item.to || pathname.startsWith(`${item.to}/`);
}

function NavItems({
  pathname,
  hash,
  compact,
  onNavigate,
  adminRole,
}: {
  pathname: string;
  hash: string;
  compact?: boolean;
  onNavigate?: () => void;
  adminRole: AdminRole;
}) {
  return (
    <>
      {nav.map((item) => {
        const active = navActive(item, pathname, hash);
        return (
          <NavLink
            key={item.label}
            to={item.to}
            title={item.label}
            onClick={onNavigate}
            className={cn(
              "flex items-center rounded-lg text-[13px] transition-colors",
              compact ? "justify-center px-0 py-2.5" : "gap-2.5 px-3 py-2",
              active
                ? "bg-primary/10 text-foreground"
                : "text-muted-foreground hover:bg-foreground/[0.04] hover:text-foreground",
            )}
          >
            <item.icon className="size-4 shrink-0" />
            {!compact && item.label}
          </NavLink>
        );
      })}
      {adminRole !== "user" && (
        <NavLink
          to="/admin"
          title="Админка"
          onClick={onNavigate}
          className={({ isActive }) =>
            cn(
              "flex items-center rounded-lg text-[13px] transition-colors",
              compact ? "justify-center px-0 py-2.5" : "gap-2.5 px-3 py-2",
              isActive
                ? "bg-primary/10 text-foreground"
                : "text-muted-foreground hover:bg-foreground/[0.04] hover:text-foreground",
            )
          }
        >
          <Shield className="size-4 shrink-0" />
          {!compact && "Админка"}
        </NavLink>
      )}
    </>
  );
}

function AccountLinks({
  userName,
  compact,
  onLogout,
  onNavigate,
  profileActive,
}: {
  userName?: string;
  compact?: boolean;
  onLogout: () => void;
  onNavigate?: () => void;
  profileActive: boolean;
}) {
  return (
    <>
      <NavLink
        to="/profile"
        title="Профиль"
        onClick={onNavigate}
        className={cn(
          "flex items-center rounded-lg text-[13px] transition-colors",
          compact ? "justify-center px-0 py-2.5" : "gap-2.5 px-3 py-2",
          profileActive
            ? "bg-primary/10 text-foreground"
            : "text-muted-foreground hover:bg-foreground/[0.04] hover:text-foreground",
        )}
      >
        <UserRound className="size-4" />
        {!compact && (userName ?? "Профиль")}
      </NavLink>
      <button
        type="button"
        title="Выйти"
        onClick={onLogout}
        className={cn(
          "flex w-full items-center rounded-lg text-[13px] text-muted-foreground hover:bg-foreground/[0.04] hover:text-foreground",
          compact ? "justify-center px-0 py-2.5" : "gap-2.5 px-3 py-2",
        )}
      >
        <LogOut className="size-4" />
        {!compact && "Выйти"}
      </button>
    </>
  );
}

export function WorkspaceShell({
  children,
  adminRole = "user",
  userName,
  fullBleed = false,
}: {
  children: ReactNode;
  adminRole?: AdminRole;
  userName?: string;
  fullBleed?: boolean;
}) {
  const navigate = useNavigate();
  const location = useLocation();
  const hash = location.hash.replace("#", "");
  const [menuOpen, setMenuOpen] = useState(false);
  const profileActive = location.pathname.startsWith("/profile");

  useEffect(() => {
    touchStreak();
  }, []);

  useEffect(() => {
    setMenuOpen(false);
  }, [location.pathname, location.hash]);

  const handleLogout = async () => {
    setMenuOpen(false);
    await logoutRemote();
    navigate("/login", { replace: true });
  };

  return (
    <div className="theme-night min-h-screen bg-background text-foreground">
      <header className="fixed inset-x-0 top-0 z-30 flex h-14 items-center justify-between border-b border-border bg-background/90 px-4 backdrop-blur-md md:hidden">
        <BrandMark to="/dashboard" />
        <button
          type="button"
          aria-label={menuOpen ? "Закрыть меню" : "Меню"}
          onClick={() => setMenuOpen((v) => !v)}
          className="flex size-9 items-center justify-center rounded-[10px] text-muted-foreground hover:bg-foreground/5 hover:text-foreground"
        >
          {menuOpen ? <X className="size-4" /> : <Menu className="size-4" />}
        </button>
      </header>

      {menuOpen && (
        <div className="fixed inset-0 z-40 md:hidden">
          <button
            type="button"
            className="absolute inset-0 bg-black/50"
            aria-label="Закрыть"
            onClick={() => setMenuOpen(false)}
          />
          <aside className="relative flex h-full w-[220px] flex-col border-r border-border bg-card">
            <div className="px-5 py-5">
              <BrandMark to="/dashboard" />
            </div>
            <nav className="flex flex-1 flex-col gap-0.5 px-3">
              <NavItems
                pathname={location.pathname}
                hash={hash}
                adminRole={adminRole}
                onNavigate={() => setMenuOpen(false)}
              />
            </nav>
            <div className="border-t border-border p-3">
              <AccountLinks
                userName={userName}
                profileActive={profileActive}
                onLogout={() => void handleLogout()}
                onNavigate={() => setMenuOpen(false)}
              />
            </div>
          </aside>
        </div>
      )}

      <aside className="fixed inset-y-0 left-0 z-20 hidden w-[72px] flex-col border-r border-border bg-background md:flex lg:w-[232px]">
        <div className="flex justify-center px-3 py-5 lg:justify-start lg:px-5">
          <BrandMark to="/dashboard" compact className="lg:hidden" />
          <BrandMark to="/dashboard" className="hidden lg:inline-flex" />
        </div>
        <nav className="flex flex-1 flex-col gap-0.5 px-2 lg:px-3">
          <div className="flex flex-col gap-0.5 lg:hidden">
            <NavItems
              pathname={location.pathname}
              hash={hash}
              adminRole={adminRole}
              compact
            />
          </div>
          <div className="hidden flex-col gap-0.5 lg:flex">
            <NavItems pathname={location.pathname} hash={hash} adminRole={adminRole} />
          </div>
        </nav>
        <div className="border-t border-border p-2 lg:p-3">
          <div className="lg:hidden">
            <AccountLinks
              userName={userName}
              compact
              profileActive={profileActive}
              onLogout={() => void handleLogout()}
            />
          </div>
          <div className="hidden lg:block">
            <AccountLinks
              userName={userName}
              profileActive={profileActive}
              onLogout={() => void handleLogout()}
            />
          </div>
        </div>
      </aside>

      <div className="md:pl-[72px] lg:pl-[232px]">
        <div
          className={
            fullBleed
              ? "relative h-[100dvh] overflow-hidden pt-14 md:h-screen md:pt-0"
              : "relative min-h-screen pt-14 pb-20 md:pt-0 md:pb-0"
          }
        >
          <div className={fullBleed ? "relative h-full" : "page-rise relative h-full"}>{children}</div>
        </div>
      </div>

      {!fullBleed && (
        <nav className="fixed inset-x-0 bottom-0 z-20 flex border-t border-border bg-card/95 backdrop-blur md:hidden">
          {mobileNav.map((item) => {
            const active = navActive(item, location.pathname, hash);
            return (
              <NavLink
                key={item.label}
                to={item.to}
                className={cn(
                  "flex flex-1 flex-col items-center gap-1 py-2.5 text-[10px]",
                  active ? "text-primary" : "text-muted-foreground",
                )}
              >
                <item.icon className="size-4" />
                {item.label}
              </NavLink>
            );
          })}
        </nav>
      )}
    </div>
  );
}
