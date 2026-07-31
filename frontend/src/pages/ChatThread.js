import { useEffect, useRef, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import api from "@/lib/api";
import { AvatarCircle } from "@/components/AvatarCircle";
import { Input } from "@/components/ui/input";
import { ArrowLeft, Send, Loader2, MoreVertical, LogOut, UserPlus } from "lucide-react";
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { toast } from "sonner";
import { useAuth } from "@/context/AuthContext";

function msgTime(iso) {
  try { return new Date(iso).toLocaleTimeString("es-ES", { hour: "2-digit", minute: "2-digit" }); }
  catch { return ""; }
}

/**
 * Universal chat thread — used for both DMs and Group chats.
 * kind: 'dm' | 'group'
 */
export default function ChatThread({ kind }) {
  const { id } = useParams();
  const navigate = useNavigate();
  const qc = useQueryClient();
  const scrollRef = useRef(null);
  const [text, setText] = useState("");
  const [showMenu, setShowMenu] = useState(false);
  const { user: me } = useAuth();

  const messagesKey = kind === "dm" ? ["dm-messages", id] : ["group-messages", id];
  const listEndpoint = kind === "dm" ? `/dm/${id}/messages` : `/groups/${id}/messages`;

  const { data: messages = [], isLoading } = useQuery({
    queryKey: messagesKey,
    queryFn: async () => (await api.get(listEndpoint)).data,
    refetchInterval: 5000,
  });

  const { data: groupInfo } = useQuery({
    queryKey: ["group-info", id],
    queryFn: async () => (await api.get(`/groups/${id}`)).data,
    enabled: kind === "group",
  });

  const { data: friend } = useQuery({
    queryKey: ["user-basic", id],
    queryFn: async () => {
      const friends = (await api.get("/friends")).data;
      return friends.find((f) => f.user_id === id) || null;
    },
    enabled: kind === "dm",
  });

  const send = useMutation({
    mutationFn: async () => {
      const body = text.trim();
      if (kind === "dm") return (await api.post("/dm/send", { to_user_id: id, text: body })).data;
      return (await api.post(`/groups/${id}/messages`, { text: body })).data;
    },
    onSuccess: () => {
      setText("");
      qc.invalidateQueries({ queryKey: messagesKey });
      qc.invalidateQueries({ queryKey: kind === "dm" ? ["dm-threads"] : ["groups"] });
    },
    onError: (err) => toast.error(err.response?.data?.detail || "No se pudo enviar"),
  });

  const leaveGroup = useMutation({
    mutationFn: async () => (await api.post(`/groups/${id}/leave`)).data,
    onSuccess: () => {
      toast.success("Saliste del grupo");
      qc.invalidateQueries({ queryKey: ["groups"] });
      navigate("/chats");
    },
  });

  useEffect(() => {
    if (scrollRef.current) scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
  }, [messages.length]);

  const title = kind === "dm" ? (friend?.name || "Chat") : (groupInfo?.name || "Grupo");
  const subtitle = kind === "dm"
    ? (friend?.username ? `@${friend.username}` : "")
    : (groupInfo ? `${groupInfo.member_ids.length} miembros` : "");

  return (
    <div className="min-h-screen qv-app-bg flex flex-col">
      <div className="max-w-md mx-auto w-full flex-1 flex flex-col">
        {/* Header */}
        <header className="flex items-center gap-3 px-4 py-3 border-b border-white/10 qv-glass sticky top-0 z-20">
          <button
            data-testid="chat-back"
            onClick={() => navigate("/chats")}
            className="w-10 h-10 rounded-full border border-white/15 flex items-center justify-center active:scale-90"
          >
            <ArrowLeft className="w-5 h-5 text-white" />
          </button>
          <button
            onClick={() => kind === "dm" && navigate(`/users/${id}`)}
            className="flex items-center gap-3 flex-1 text-left"
          >
            {kind === "dm" ? (
              <AvatarCircle name={friend?.name || ""} picture={friend?.picture || ""} size={38} ring={false} />
            ) : (
              <div className="w-10 h-10 rounded-2xl bg-gradient-to-br from-qv-primary to-qv-secondary flex items-center justify-center text-white font-black text-sm">
                {title.slice(0, 2).toUpperCase()}
              </div>
            )}
            <div className="min-w-0">
              <p className="font-bold text-white truncate">{title}</p>
              <p className="text-xs text-white/50 truncate">{subtitle}</p>
            </div>
          </button>
          {kind === "group" && (
            <button
              data-testid="chat-menu"
              onClick={() => setShowMenu(true)}
              className="w-10 h-10 rounded-full border border-white/15 flex items-center justify-center active:scale-90"
            >
              <MoreVertical className="w-5 h-5 text-white" />
            </button>
          )}
        </header>

        {/* Messages */}
        <div ref={scrollRef} className="flex-1 overflow-y-auto hide-scrollbar px-4 py-4 flex flex-col gap-3" data-testid="chat-messages">
          {isLoading ? (
            <div className="flex justify-center py-10"><Loader2 className="w-6 h-6 text-qv-primary animate-spin" /></div>
          ) : messages.length === 0 ? (
            <p className="text-center text-white/40 text-sm py-10">Sé el primero en escribir 👋</p>
          ) : (
            messages.map((m) => (
              <div key={m.id} className={`flex gap-2 ${m.is_mine ? "flex-row-reverse" : ""}`} data-testid={`msg-${m.id}`}>
                {!m.is_mine && kind === "group" && (
                  <AvatarCircle name={m.author?.name || ""} picture={m.author?.picture || ""} size={28} ring={false} />
                )}
                <div className={`max-w-[75%] ${m.is_mine ? "items-end" : "items-start"} flex flex-col`}>
                  <div className={`rounded-2xl px-3 py-2 text-sm ${m.is_mine ? "bg-qv-primary text-white" : "bg-white/10 text-white"}`}>
                    {!m.is_mine && kind === "group" && (
                      <span className="block text-[11px] text-qv-secondary font-semibold">{m.author?.name?.split(" ")[0]}</span>
                    )}
                    {m.text}
                  </div>
                  <span className="text-[10px] text-white/40 mt-0.5 px-1">{msgTime(m.created_at)}</span>
                </div>
              </div>
            ))
          )}
        </div>

        {/* Input */}
        <div className="px-4 pt-2 pb-[max(0.75rem,env(safe-area-inset-bottom))] border-t border-white/10 qv-glass sticky bottom-0 flex items-center gap-2">
          <Input
            data-testid="chat-input"
            value={text}
            onChange={(e) => setText(e.target.value)}
            onKeyDown={(e) => { if (e.key === "Enter" && text.trim()) send.mutate(); }}
            placeholder="Escribe un mensaje…"
            className="flex-1 h-11 bg-white/5 border-white/15 rounded-full text-white placeholder:text-white/40"
          />
          <button
            data-testid="chat-send"
            onClick={() => text.trim() && send.mutate()}
            disabled={send.isPending || !text.trim()}
            className="w-11 h-11 rounded-full bg-qv-primary flex items-center justify-center shrink-0 active:scale-90 disabled:opacity-40"
          >
            <Send className="w-4 h-4 text-white" />
          </button>
        </div>
      </div>

      <Dialog open={showMenu} onOpenChange={setShowMenu}>
        <DialogContent className="bg-[#121215] border-white/10 text-white max-w-sm rounded-2xl">
          <DialogHeader><DialogTitle>{title}</DialogTitle></DialogHeader>
          <div className="space-y-3">
            {groupInfo?.members?.map((m) => (
              <div key={m.user_id} className="flex items-center gap-3">
                <AvatarCircle name={m.name} picture={m.picture} size={34} ring={false} />
                <span className="flex-1 text-white text-sm">{m.name}</span>
                {groupInfo?.created_by === m.user_id && <span className="text-[10px] uppercase text-qv-secondary font-bold">creador</span>}
                {m.user_id === me?.user_id && <span className="text-[10px] uppercase text-white/40 font-bold">tú</span>}
              </div>
            ))}
          </div>
          <button
            data-testid="leave-group"
            onClick={() => leaveGroup.mutate()}
            className="h-11 rounded-2xl bg-red-500/20 text-red-300 font-bold flex items-center justify-center gap-2"
          >
            <LogOut className="w-4 h-4" /> Salir del grupo
          </button>
        </DialogContent>
      </Dialog>
    </div>
  );
}
