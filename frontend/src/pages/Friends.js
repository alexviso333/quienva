import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import api from "@/lib/api";
import { AppShell } from "@/components/AppShell";
import { AvatarCircle } from "@/components/AvatarCircle";
import FindFriends from "@/components/FindFriends";
import { Input } from "@/components/ui/input";
import { UserPlus, Check, Clock, Search, X, Loader2, Compass, MessageCircle } from "lucide-react";
import { toast } from "@/lib/notify";
import { useNavigate } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { captureEvent } from "@/analytics/posthog";

export default function Friends() {
  const { t } = useTranslation();
  const qc = useQueryClient();
  const navigate = useNavigate();
  const [q, setQ] = useState("");
  const [debounced, setDebounced] = useState("");

  const onSearch = (e) => {
    const v = e.target.value;
    setQ(v);
    clearTimeout(window.__qvSearch);
    window.__qvSearch = setTimeout(() => setDebounced(v.trim()), 350);
  };

  const { data: results = [], isFetching } = useQuery({
    queryKey: ["user-search", debounced],
    queryFn: async () => (await api.get("/users/search", { params: { q: debounced } })).data,
    enabled: debounced.length >= 1,
  });

  const { data: requests = [] } = useQuery({
    queryKey: ["friend-requests"],
    queryFn: async () => (await api.get("/friends/requests")).data,
  });

  const { data: friends = [] } = useQuery({
    queryKey: ["friends"],
    queryFn: async () => (await api.get("/friends")).data,
  });

  // DM unread badge — chats now live here (bottom-nav tab was removed).
  const { data: dmUnread = 0 } = useQuery({
    queryKey: ["dm-unread-count"],
    queryFn: async () => (await api.get("/dm/unread-count")).data.count,
    refetchInterval: 30000,
    staleTime: 15000,
  });

  const invalidate = () => {
    qc.invalidateQueries({ queryKey: ["user-search"] });
    qc.invalidateQueries({ queryKey: ["friend-requests"] });
    qc.invalidateQueries({ queryKey: ["friends"] });
    qc.invalidateQueries({ queryKey: ["unread-count"] });
  };

  const sendReq = useMutation({
    mutationFn: async (userId) => (await api.post("/friends/request", { user_id: userId })).data,
    onSuccess: (d) => {
      captureEvent("friend_request_sent", { auto_accepted: d.status === "accepted" });
      toast.success(d.status === "accepted" ? t("friends.toast_now_friends") : t("friends.toast_request_sent"));
      invalidate();
    },
    onError: (e) => toast.error(e.response?.data?.detail || t("friends.toast_error")),
  });

  const respond = useMutation({
    mutationFn: async ({ requestId, accept }) =>
      (await api.post("/friends/respond", { request_id: requestId, accept })).data,
    onSuccess: (_d, vars) => {
      if (vars?.accept) captureEvent("friend_added", { via: "request_accepted" });
      toast.success(t("friends.toast_done"));
      invalidate();
    },
  });

  const relBadge = (rel) => {
    if (!rel || rel.status === "none")
      return { label: t("friends.add"), icon: UserPlus, action: "add", cls: "bg-qv-primary text-white" };
    if (rel.status === "accepted") return { label: t("friends.friends_label"), icon: Check, action: "none", cls: "bg-white/10 text-white/60" };
    if (rel.status === "pending" && rel.direction === "out")
      return { label: t("friends.pending"), icon: Clock, action: "none", cls: "bg-white/10 text-white/60" };
    if (rel.status === "pending" && rel.direction === "in")
      return { label: t("friends.accept"), icon: Check, action: "accept", rel, cls: "bg-qv-secondary text-black" };
    return { label: t("friends.add"), icon: UserPlus, action: "add", cls: "bg-qv-primary text-white" };
  };

  return (
    <AppShell>
      <header className="px-5 pt-8 pb-4 flex items-start justify-between gap-3">
        <div className="min-w-0">
          <h1 className="font-display text-4xl font-black tracking-tighter">
            {t("friends.title")}<span className="text-qv-primary">.</span>
          </h1>
          <p className="text-white/50 text-sm mt-1">{t("friends.subtitle")}</p>
        </div>
        <button
          data-testid="friends-messages-btn"
          onClick={() => navigate("/chats")}
          aria-label={t("friends.messages", "Mensajes")}
          className="relative mt-1 shrink-0 flex items-center justify-center w-11 h-11 rounded-full bg-white/[0.08] border border-white/10 text-qv-secondary active:scale-95"
        >
          <MessageCircle className="w-5 h-5" />
          {dmUnread > 0 && (
            <span
              data-testid="friends-messages-badge"
              className="absolute -top-1 -right-1 min-w-[18px] h-[18px] px-1 rounded-full bg-qv-primary text-white text-[10px] font-bold flex items-center justify-center"
            >
              {dmUnread > 9 ? "9+" : dmUnread}
            </span>
          )}
        </button>
      </header>

      <div className="px-5 pb-1">
        <button
          data-testid="descubrir-btn"
          onClick={() => navigate("/descubrir")}
          className="w-full h-12 rounded-2xl bg-gradient-to-r from-qv-primary/20 to-qv-secondary/20 border border-qv-secondary/40 text-white font-bold flex items-center justify-center gap-2 active:scale-95"
        >
          <Compass className="w-4 h-4 text-qv-secondary" /> {t("friends.discover_cta")}
        </button>
      </div>

      <FindFriends />

      <div className="px-5 mt-2">
        <div className="relative">
          <Search className="absolute left-4 top-1/2 -translate-y-1/2 w-4 h-4 text-white/40" />
          <Input
            data-testid="friend-search-input"
            placeholder="Buscar por usuario o nombre"
            value={q}
            onChange={onSearch}
            className="h-12 pl-11 bg-white/5 border-white/15 rounded-2xl text-white placeholder:text-white/40"
          />
        </div>
      </div>

      {debounced.length >= 1 && (
        <section className="px-5 mt-4" data-testid="search-results">
          <p className="text-xs uppercase tracking-widest text-white/40 font-bold mb-2">{t("friends.results")}</p>
          {isFetching ? (
            <div className="py-6 flex justify-center"><Loader2 className="w-5 h-5 animate-spin text-white/40" /></div>
          ) : results.length === 0 ? (
            <p className="text-white/40 text-sm py-4">{t("friends.no_results", { q: debounced })}</p>
          ) : (
            <div className="flex flex-col gap-2">
              {results.map((u) => {
                const b = relBadge(u.relationship);
                const Icon = b.icon;
                return (
                  <div key={u.user_id} className="flex items-center gap-3 bg-white/5 border border-white/10 rounded-2xl p-3" data-testid={`search-user-${u.username}`}>
                    <AvatarCircle name={u.name} picture={u.picture} size={44} ring={false} />
                    <div className="flex-1 min-w-0">
                      <p className="font-semibold truncate">{u.name}</p>
                      {u.mutual_count > 0 && (
                        <p className="text-white/40 text-sm truncate">
                          <span className="text-qv-secondary">{u.mutual_count} en común</span>
                        </p>
                      )}
                    </div>
                    <button
                      data-testid={`friend-action-${u.username}`}
                      disabled={b.action === "none"}
                      onClick={() => {
                        if (b.action === "add") sendReq.mutate(u.user_id);
                        else if (b.action === "accept") respond.mutate({ requestId: b.rel.request_id, accept: true });
                      }}
                      className={`h-9 px-4 rounded-full text-sm font-semibold flex items-center gap-1.5 transition-transform duration-300 active:scale-95 ${b.cls}`}
                    >
                      <Icon className="w-4 h-4" /> {b.label}
                    </button>
                  </div>
                );
              })}
            </div>
          )}
        </section>
      )}

      {requests.length > 0 && (
        <section className="px-5 mt-6" data-testid="incoming-requests">
          <p className="text-xs uppercase tracking-widest text-qv-primary font-bold mb-2">
            {t("friends.requests", { count: requests.length })}
          </p>
          <div className="flex flex-col gap-2">
            {requests.map((r) => (
              <div key={r.request_id} className="flex items-center gap-3 bg-white/5 border border-white/10 rounded-2xl p-3" data-testid={`request-${r.user.username}`}>
                <AvatarCircle name={r.user.name} picture={r.user.picture} size={44} ring={false} />
                <div className="flex-1 min-w-0">
                  <p className="font-semibold truncate">{r.user.name}</p>
                  {r.user.mutual_count > 0 && (
                    <p className="text-white/40 text-sm truncate">
                      <span className="text-qv-secondary">{t("friends.mutual", { count: r.user.mutual_count })}</span>
                    </p>
                  )}
                </div>
                <button
                  data-testid={`accept-${r.user.username}`}
                  onClick={() => respond.mutate({ requestId: r.request_id, accept: true })}
                  className="h-9 w-9 rounded-full bg-qv-secondary text-black flex items-center justify-center active:scale-95 transition-transform"
                >
                  <Check className="w-4 h-4" />
                </button>
                <button
                  data-testid={`reject-${r.user.username}`}
                  onClick={() => respond.mutate({ requestId: r.request_id, accept: false })}
                  className="h-9 w-9 rounded-full bg-white/10 text-white/70 flex items-center justify-center active:scale-95 transition-transform"
                >
                  <X className="w-4 h-4" />
                </button>
              </div>
            ))}
          </div>
        </section>
      )}

      <section className="px-5 mt-6" data-testid="friends-list">
        <p className="text-xs uppercase tracking-widest text-white/40 font-bold mb-2">
          {t("friends.your_friends", { count: friends.length })}
        </p>
        {friends.length === 0 ? (
          <p className="text-white/40 text-sm py-4">
            {t("friends.empty")}
          </p>
        ) : (
          <div className="flex flex-col gap-2">
            {friends.map((f) => (
              <div key={f.user_id} className="flex items-center gap-3 bg-white/5 border border-white/10 rounded-2xl p-3" data-testid={`friend-${f.username}`}>
                <AvatarCircle name={f.name} picture={f.picture} size={44} ring={false} />
                <div className="flex-1 min-w-0">
                  <p className="font-semibold truncate">{f.name}</p>
                </div>
                <Check className="w-5 h-5 text-qv-secondary" />
              </div>
            ))}
          </div>
        )}
      </section>
    </AppShell>
  );
}
