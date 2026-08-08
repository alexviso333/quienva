import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import api from "@/lib/api";
import { AppShell } from "@/components/AppShell";
import { AvatarCircle } from "@/components/AvatarCircle";
import { Users2, MessageSquare, Plus, Loader2, ChevronRight, X, Check } from "lucide-react";
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { toast } from "sonner";
import { useTranslation } from "react-i18next";
import i18n from "@/i18n";

const LOCALE_BY_LANG = { es: "es-ES", en: "en-GB", de: "de-DE" };
const dateLocale = () => LOCALE_BY_LANG[(i18n.language || "es").slice(0, 2)] || "es-ES";

function timeAgo(iso) {
  if (!iso) return "";
  const d = new Date(iso);
  const diff = (Date.now() - d.getTime()) / 1000;
  if (diff < 60) return i18n.t("stories.timeago_now");
  if (diff < 3600) return `${Math.floor(diff / 60)}min`;
  if (diff < 86400) return `${Math.floor(diff / 3600)}h`;
  if (diff < 7 * 86400) return `${Math.floor(diff / 86400)}d`;
  return d.toLocaleDateString(dateLocale(), { day: "numeric", month: "short" });
}

function CreateGroupDialog({ open, onClose }) {
  const qc = useQueryClient();
  const navigate = useNavigate();
  const { t } = useTranslation();
  const [name, setName] = useState("");
  const [selected, setSelected] = useState([]);
  const { data: friends = [] } = useQuery({
    queryKey: ["friends-for-group"],
    queryFn: async () => (await api.get("/friends")).data,
    enabled: open,
  });
  const createGroup = useMutation({
    mutationFn: async () => (await api.post("/groups", { name: name.trim(), member_ids: selected })).data,
    onSuccess: (data) => {
      toast.success(t("chats.toast_created"));
      qc.invalidateQueries({ queryKey: ["groups"] });
      onClose();
      setName(""); setSelected([]);
      navigate(`/chats/group/${data.id}`);
    },
    onError: (err) => toast.error(err.response?.data?.detail || t("chats.toast_create_error")),
  });

  const toggle = (uid) => setSelected((s) => s.includes(uid) ? s.filter((x) => x !== uid) : [...s, uid]);

  return (
    <Dialog open={open} onOpenChange={(o) => !o && onClose()}>
      <DialogContent className="bg-[#121215] border-white/10 text-white max-w-sm rounded-2xl" data-testid="create-group-dialog">
        <DialogHeader>
          <DialogTitle>{t("chats.new_group")}</DialogTitle>
        </DialogHeader>
        <Input
          data-testid="create-group-name"
          placeholder={t("chats.group_name_ph")}
          value={name}
          onChange={(e) => setName(e.target.value)}
          maxLength={60}
          className="bg-white/5 border-white/15 text-white placeholder:text-white/40"
        />
        <div className="max-h-64 overflow-y-auto hide-scrollbar">
          {friends.length === 0 ? (
            <p className="text-white/40 text-sm text-center py-6">{t("chats.add_friends_first")}</p>
          ) : (
            friends.map((f) => {
              const on = selected.includes(f.user_id);
              return (
                <button
                  key={f.user_id}
                  data-testid={`create-group-add-${f.username}`}
                  onClick={() => toggle(f.user_id)}
                  className="w-full flex items-center gap-3 py-2 px-1"
                >
                  <AvatarCircle name={f.name} picture={f.picture} size={36} ring={false} />
                  <span className="flex-1 text-left text-white text-sm">{f.name}</span>
                  <span className={`w-6 h-6 rounded-full flex items-center justify-center border ${on ? "bg-qv-primary border-qv-primary" : "border-white/30"}`}>
                    {on && <Check className="w-4 h-4 text-white" />}
                  </span>
                </button>
              );
            })
          )}
        </div>
        <button
          data-testid="create-group-submit"
          onClick={() => createGroup.mutate()}
          disabled={!name.trim() || selected.length === 0 || createGroup.isPending}
          className="h-11 rounded-2xl bg-qv-primary text-white font-bold disabled:opacity-40"
        >
          {createGroup.isPending ? t("chats.creating") : t(selected.length === 1 ? "chats.create_with_one" : "chats.create_with_other", { count: selected.length })}
        </button>
      </DialogContent>
    </Dialog>
  );
}

export default function Chats() {
  const navigate = useNavigate();
  const { t } = useTranslation();
  const [tab, setTab] = useState("friends");
  const [creating, setCreating] = useState(false);

  const { data: dms = [], isLoading: loadingDMs } = useQuery({
    queryKey: ["dm-threads"],
    queryFn: async () => (await api.get("/dm/threads")).data,
    refetchInterval: 15000,
  });
  const { data: groups = [], isLoading: loadingGroups } = useQuery({
    queryKey: ["groups"],
    queryFn: async () => (await api.get("/groups")).data,
    refetchInterval: 15000,
  });

  return (
    <AppShell>
      <header className="px-5 pt-8 pb-3 flex items-center justify-between">
        <div>
          <p className="text-xs tracking-[0.25em] uppercase text-qv-secondary font-bold">{t("chats.eyebrow")}</p>
          <h1 className="font-display text-4xl font-black tracking-tighter">{t("chats.title")}<span className="text-qv-primary">.</span></h1>
        </div>
        <button
          data-testid="create-group-btn"
          onClick={() => setCreating(true)}
          className="w-11 h-11 rounded-full bg-qv-primary flex items-center justify-center active:scale-90 transition-transform"
        >
          <Plus className="w-5 h-5 text-white" />
        </button>
      </header>

      <div className="flex gap-2 px-5 pb-3">
        <button
          data-testid="chats-tab-friends"
          onClick={() => setTab("friends")}
          className={`flex-1 flex items-center justify-center gap-1.5 rounded-full px-3 py-2 text-xs font-bold ${
            tab === "friends" ? "bg-white text-black" : "bg-white/5 border border-white/10 text-white/70"
          }`}
        >
          <MessageSquare className="w-3.5 h-3.5" /> {t("chats.tab_friends")}
        </button>
        <button
          data-testid="chats-tab-groups"
          onClick={() => setTab("groups")}
          className={`flex-1 flex items-center justify-center gap-1.5 rounded-full px-3 py-2 text-xs font-bold ${
            tab === "groups" ? "bg-white text-black" : "bg-white/5 border border-white/10 text-white/70"
          }`}
        >
          <Users2 className="w-3.5 h-3.5" /> {t("chats.tab_groups")}
        </button>
      </div>

      {tab === "friends" ? (
        loadingDMs ? (
          <div className="flex justify-center py-16"><Loader2 className="w-7 h-7 text-qv-primary animate-spin" /></div>
        ) : dms.length === 0 ? (
          <p className="text-center text-white/40 py-16 px-6">{t("chats.empty_dms")}</p>
        ) : (
          <div className="flex flex-col" data-testid="dm-list">
            {dms.map((thread) => (
              <button
                key={thread.user.user_id}
                data-testid={`dm-row-${thread.user.username}`}
                onClick={() => navigate(`/chats/dm/${thread.user.user_id}`)}
                className="flex items-center gap-3 px-5 py-3 border-b border-white/5 hover:bg-white/[0.03] active:bg-white/5"
              >
                <AvatarCircle name={thread.user.name} picture={thread.user.picture} size={48} ring={thread.unread > 0} />
                <div className="flex-1 min-w-0 text-left">
                  <div className="flex justify-between items-baseline gap-2">
                    <p className="font-bold text-white truncate">{thread.user.name}</p>
                    <span className="text-[10px] text-white/40">{timeAgo(thread.last_at)}</span>
                  </div>
                  <p className={`text-sm truncate ${thread.unread > 0 ? "text-white" : "text-white/50"}`}>
                    {thread.last_message || t("chats.start_conversation")}
                  </p>
                </div>
                {thread.unread > 0 && (
                  <span className="min-w-[20px] h-5 px-1.5 rounded-full bg-qv-primary text-white text-[10px] font-bold flex items-center justify-center">
                    {thread.unread > 9 ? "9+" : thread.unread}
                  </span>
                )}
              </button>
            ))}
          </div>
        )
      ) : loadingGroups ? (
        <div className="flex justify-center py-16"><Loader2 className="w-7 h-7 text-qv-primary animate-spin" /></div>
      ) : groups.length === 0 ? (
        <div className="text-center py-16 px-6">
          <Users2 className="w-12 h-12 text-white/30 mx-auto mb-3" />
          <p className="text-white/60">{t("chats.empty_groups")}</p>
          <button
            data-testid="empty-create-group"
            onClick={() => setCreating(true)}
            className="mt-4 h-11 px-5 rounded-2xl bg-qv-primary text-white font-bold"
          >
            {t("chats.create_first")}
          </button>
        </div>
      ) : (
        <div className="flex flex-col" data-testid="group-list">
          {groups.map((g) => (
            <button
              key={g.id}
              data-testid={`group-row-${g.id}`}
              onClick={() => navigate(`/chats/group/${g.id}`)}
              className="flex items-center gap-3 px-5 py-3 border-b border-white/5"
            >
              <div className="w-12 h-12 rounded-2xl bg-gradient-to-br from-qv-primary to-qv-secondary flex items-center justify-center text-white font-black text-lg">
                {g.name.slice(0, 2).toUpperCase()}
              </div>
              <div className="flex-1 min-w-0 text-left">
                <div className="flex justify-between items-baseline gap-2">
                  <p className="font-bold text-white truncate">{g.name}</p>
                  <span className="text-[10px] text-white/40">{timeAgo(g.last_at || g.created_at)}</span>
                </div>
                <p className={`text-sm truncate ${g.unread > 0 ? "text-white" : "text-white/50"}`}>
                  {g.last_message || t(g.member_ids.length === 1 ? "chats.members_one" : "chats.members_other", { count: g.member_ids.length })}
                </p>
              </div>
              {g.unread > 0 && (
                <span className="min-w-[20px] h-5 px-1.5 rounded-full bg-qv-primary text-white text-[10px] font-bold flex items-center justify-center">
                  {g.unread > 9 ? "9+" : g.unread}
                </span>
              )}
            </button>
          ))}
        </div>
      )}

      <CreateGroupDialog open={creating} onClose={() => setCreating(false)} />
    </AppShell>
  );
}
