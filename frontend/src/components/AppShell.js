import { NavLink, useNavigate } from "react-router-dom";
import { Home, Users, MessageCircle, Bell, User } from "lucide-react";
import { useQuery } from "@tanstack/react-query";
import api from "@/lib/api";

const items = [
  { to: "/feed", icon: Home, label: "Planes", testid: "nav-feed" },
  { to: "/friends", icon: Users, label: "Amigos", testid: "nav-friends" },
  { to: "/chats", icon: MessageCircle, label: "Chats", testid: "nav-chats" },
  { to: "/notifications", icon: Bell, label: "Avisos", testid: "nav-notifications" },
  { to: "/profile", icon: User, label: "Perfil", testid: "nav-profile" },
];

export function BottomNav() {
  const { data: unread } = useQuery({
    queryKey: ["unread-count"],
    queryFn: async () => (await api.get("/notifications/unread-count")).data.count,
    refetchInterval: 30000,
    refetchOnWindowFocus: true,
    staleTime: 15000,
  });
  const { data: dmUnread } = useQuery({
    queryKey: ["dm-unread-count"],
    queryFn: async () => (await api.get("/dm/unread-count")).data.count,
    refetchInterval: 30000,
    refetchOnWindowFocus: true,
    staleTime: 15000,
  });

  return (
    <nav
      className="qv-glass fixed bottom-0 left-1/2 -translate-x-1/2 w-full max-w-md z-50 border-t border-white/10"
      data-testid="bottom-nav"
    >
      <div className="grid grid-cols-6 px-2 pt-2 pb-[max(0.5rem,env(safe-area-inset-bottom))]">
        {items.map(({ to, icon: Icon, label, testid }) => {
          const badgeCount = to === "/notifications" ? unread : to === "/chats" ? dmUnread : 0;
          return (
            <NavLink
              key={to}
              to={to}
              data-testid={testid}
              className={({ isActive }) =>
                `relative flex flex-col items-center gap-1 py-1.5 rounded-2xl transition-colors duration-300 ${
                  isActive ? "text-white" : "text-white/40"
                }`
              }
            >
              {({ isActive }) => (
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
              )}
            </NavLink>
          );
        })}
      </div>
    </nav>
  );
}

export function AppShell({ children, showNav = true }) {
  useNavigate();
  return (
    <div className="min-h-screen qv-app-bg">
      <div className="relative max-w-md mx-auto min-h-screen bg-transparent">
        <div className={showNav ? "pb-28" : ""}>{children}</div>
        {showNav && <BottomNav />}
      </div>
    </div>
  );
}
