import { NavLink, useNavigate } from "react-router-dom";
import { Home, Users, MessageCircle, Bell, User } from "lucide-react";
import { useQuery } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import api from "@/lib/api";
import { useAuth } from "@/context/AuthContext";
import { useGuestGate } from "@/context/GuestGate";

const items = [
  { to: "/feed", icon: Home, labelKey: "nav.planes", testid: "nav-feed", public: true },
  { to: "/friends", icon: Users, labelKey: "nav.amigos", testid: "nav-friends", reasonKey: "nav.reason_friends" },
  { to: "/chats", icon: MessageCircle, labelKey: "nav.chats", testid: "nav-chats", reasonKey: "nav.reason_chats" },
  { to: "/notifications", icon: Bell, labelKey: "nav.avisos", testid: "nav-notifications", reasonKey: "nav.reason_notifications" },
  { to: "/profile", icon: User, labelKey: "nav.perfil", testid: "nav-profile", reasonKey: "nav.reason_profile" },
];

// Shared unread counters (react-query dedupes by queryKey, so the bottom nav
// and the desktop sidebar reuse the same cached values — no double fetching).
function useUnreadCounts() {
  const { user } = useAuth();
  const { data: unread } = useQuery({
    queryKey: ["unread-count"],
    queryFn: async () => (await api.get("/notifications/unread-count")).data.count,
    refetchInterval: 30000,
    refetchOnWindowFocus: true,
    staleTime: 15000,
    enabled: !!user,
  });
  const { data: dmUnread } = useQuery({
    queryKey: ["dm-unread-count"],
    queryFn: async () => (await api.get("/dm/unread-count")).data.count,
    refetchInterval: 30000,
    refetchOnWindowFocus: true,
    staleTime: 15000,
    enabled: !!user,
  });
  return { unread: unread || 0, dmUnread: dmUnread || 0 };
}

function badgeFor(to, unread, dmUnread) {
  if (to === "/notifications") return unread;
  if (to === "/chats") return dmUnread;
  return 0;
}

export function BottomNav() {
  const { t } = useTranslation();
  const { user } = useAuth();
  const { requireAuth } = useGuestGate();
  const { unread, dmUnread } = useUnreadCounts();

  const navClass = (isActive) =>
    `relative flex flex-col items-center gap-1 py-1.5 rounded-2xl transition-colors duration-300 ${
      isActive ? "text-white" : "text-white/40"
    }`;

  const renderInner = (Icon, label, testid, badgeCount, isActive) => (
    <>
      <div className="relative">
        <Icon
          className={`w-6 h-6 transition-transform duration-300 ${isActive ? "scale-110" : ""}`}
          strokeWidth={isActive ? 2.4 : 2}
          style={isActive ? { filter: "drop-shadow(0 0 8px rgba(255,0,85,0.7))" } : {}}
        />
        {badgeCount > 0 && (
          <span
            data-testid={`${testid}-badge`}
            className="absolute -top-1.5 -right-2 min-w-[18px] h-[18px] px-1 rounded-full bg-qv-primary text-white text-[10px] font-bold flex items-center justify-center"
          >
            {badgeCount > 9 ? "9+" : badgeCount}
          </span>
        )}
      </div>
      <span className="text-[10px] font-semibold tracking-wide uppercase">{label}</span>
    </>
  );

  return (
    <nav
      className="qv-glass fixed bottom-0 left-1/2 -translate-x-1/2 w-full max-w-md z-50 border-t border-white/10 lg:hidden"
      data-testid="bottom-nav"
    >
      <div className="grid grid-cols-5 px-2 pt-2 pb-[max(0.5rem,env(safe-area-inset-bottom))]">
        {items.map(({ to, icon: Icon, labelKey, testid, reasonKey, public: isPublic }) => {
          const label = t(labelKey);
          const reason = reasonKey ? t(reasonKey) : "";
          const badgeCount = badgeFor(to, unread, dmUnread);
          // Guests can only open public tabs; everything else pops the gate.
          if (!user && !isPublic) {
            return (
              <button
                key={to}
                type="button"
                data-testid={testid}
                onClick={() => requireAuth(reason)}
                className={navClass(false)}
              >
                {renderInner(Icon, label, testid, 0, false)}
              </button>
            );
          }
          return (
            <NavLink key={to} to={to} data-testid={testid} className={({ isActive }) => navClass(isActive)}>
              {({ isActive }) => renderInner(Icon, label, testid, badgeCount, isActive)}
            </NavLink>
          );
        })}
      </div>
    </nav>
  );
}

// Desktop-only left sidebar (≥ lg). Mirrors the bottom nav but laid out vertically
// so quienva.me feels like a real desktop app instead of a phone column.
export function DesktopSidebar() {
  const { t } = useTranslation();
  const { user } = useAuth();
  const { requireAuth } = useGuestGate();
  const navigate = useNavigate();
  const { unread, dmUnread } = useUnreadCounts();

  const rowClass = (isActive) =>
    `relative flex items-center gap-4 px-4 py-3 rounded-2xl font-semibold text-sm transition-colors duration-200 ${
      isActive ? "bg-white/10 text-white" : "text-white/55 hover:bg-white/5 hover:text-white"
    }`;

  const rowInner = (Icon, label, badgeCount, isActive) => (
    <>
      <span className="relative">
        <Icon
          className="w-6 h-6"
          strokeWidth={isActive ? 2.4 : 2}
          style={isActive ? { filter: "drop-shadow(0 0 8px rgba(255,0,85,0.7))" } : {}}
        />
        {badgeCount > 0 && (
          <span className="absolute -top-1.5 -right-2 min-w-[18px] h-[18px] px-1 rounded-full bg-qv-primary text-white text-[10px] font-bold flex items-center justify-center">
            {badgeCount > 9 ? "9+" : badgeCount}
          </span>
        )}
      </span>
      <span className="truncate">{label}</span>
    </>
  );

  return (
    <aside
      className="hidden lg:flex sticky top-0 h-screen w-64 shrink-0 flex-col qv-glass border-r border-white/10 z-40 px-4 py-6"
      data-testid="desktop-sidebar"
    >
      <button
        onClick={() => navigate("/feed")}
        className="px-3 mb-8 text-left"
        data-testid="desktop-brand"
      >
        <span className="font-display text-2xl font-black tracking-tighter text-white">
          {t("feed.title")}<span className="text-qv-primary">.</span>
        </span>
      </button>

      <nav className="flex flex-col gap-1.5">
        {items.map(({ to, icon: Icon, labelKey, testid, reasonKey, public: isPublic }) => {
          const label = t(labelKey);
          const reason = reasonKey ? t(reasonKey) : "";
          const badgeCount = badgeFor(to, unread, dmUnread);
          if (!user && !isPublic) {
            return (
              <button
                key={to}
                type="button"
                data-testid={`sidebar-${testid}`}
                onClick={() => requireAuth(reason)}
                className={rowClass(false)}
              >
                {rowInner(Icon, label, 0, false)}
              </button>
            );
          }
          return (
            <NavLink key={to} to={to} data-testid={`sidebar-${testid}`} className={({ isActive }) => rowClass(isActive)}>
              {({ isActive }) => rowInner(Icon, label, badgeCount, isActive)}
            </NavLink>
          );
        })}
      </nav>

      <div className="mt-auto px-3 text-[10px] text-white/25 font-semibold uppercase tracking-widest">
        quienva.me
      </div>
    </aside>
  );
}

export function AppShell({ children, showNav = true, wide = false }) {
  useNavigate();
  return (
    <div className="min-h-screen qv-app-bg">
      {/* Desktop (≥lg): sidebar + content form ONE frame that is capped and
          centered (mx-auto), so on wide monitors the app sits centered with even
          margins instead of hugging the left edge. `main` is flex-1 so it fills
          the frame next to the sidebar. On mobile the flex collapses to a normal
          block and the phone column + bottom nav are untouched. */}
      <div className={`lg:flex lg:mx-auto ${showNav && wide ? "lg:max-w-[1480px]" : "lg:max-w-4xl"}`}>
        {showNav && <DesktopSidebar />}
        <main className="flex-1 min-w-0">
          <div className={`relative mx-auto qv-screen bg-transparent max-w-md ${wide ? "lg:max-w-none" : ""}`}>
            <div className={showNav ? "pb-28 lg:pb-12" : ""}>{children}</div>
          </div>
        </main>
      </div>
      {showNav && <BottomNav />}
    </div>
  );
}
