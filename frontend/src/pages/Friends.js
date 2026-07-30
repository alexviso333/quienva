import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import api from "@/lib/api";
import { AppShell } from "@/components/AppShell";
import { AvatarCircle } from "@/components/AvatarCircle";
import { Input } from "@/components/ui/input";
import { UserPlus, Check, Clock, Search, X, Loader2 } from "lucide-react";
import { toast } from "sonner";

export default function Friends() {
  const qc = useQueryClient();
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

  const invalidate = () => {
    qc.invalidateQueries({ queryKey: ["user-search"] });
    qc.invalidateQueries({ queryKey: ["friend-requests"] });
    qc.invalidateQueries({ queryKey: ["friends"] });
    qc.invalidateQueries({ queryKey: ["unread-count"] });
  };

  const sendReq = useMutation({
    mutationFn: async (userId) => (await api.post("/friends/request", { user_id: userId })).data,
    onSuccess: (d) => {
      toast.success(d.status === "accepted" ? "¡Ya sois amigos!" : "Solicitud enviada");
      invalidate();
    },
    onError: (e) => toast.error(e.response?.data?.detail || "Error"),
  });

  const respond = useMutation({
    mutationFn: async ({ requestId, accept }) =>
      (await api.post("/friends/respond", { request_id: requestId, accept })).data,
    onSuccess: () => {
      toast.success("Hecho");
      invalidate();
    },
  });

  const relBadge = (rel) => {
    if (!rel || rel.status === "none")
      return { label: "Añadir", icon: UserPlus, action: "add", cls: "bg-qv-primary text-white" };
    if (rel.status === "accepted") return { label: "Amigos", icon: Check, action: "none", cls: "bg-white/10 text-white/60" };
    if (rel.status === "pending" && rel.direction === "out")
      return { label: "Pendiente", icon: Clock, action: "none", cls: "bg-white/10 text-white/60" };
    if (rel.status === "pending" && rel.direction === "in")
      return { label: "Aceptar", icon: Check, action: "accept", rel, cls: "bg-qv-secondary text-black" };
    return { label: "Añadir", icon: UserPlus, action: "add", cls: "bg-qv-primary text-white" };
  };

  return (
    <AppShell>
      <header className="px-5 pt-8 pb-4">
        <h1 className="font-display text-4xl font-black tracking-tighter">
          Amigos<span className="text-qv-primary">.</span>
        </h1>
        <p className="text-white/50 text-sm mt-1">Cuantos más amigos, más planes verás.</p>
      </header>

      <div className="px-5">
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
          <p className="text-xs uppercase tracking-widest text-white/40 font-bold mb-2">Resultados</p>
          {isFetching ? (
            <div className="py-6 flex justify-center"><Loader2 className="w-5 h-5 animate-spin text-white/40" /></div>
          ) : results.length === 0 ? (
            <p className="text-white/40 text-sm py-4">Sin resultados para “{debounced}”.</p>
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
                      <p className="text-white/40 text-sm truncate">@{u.username}</p>
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
            Solicitudes ({requests.length})
          </p>
          <div className="flex flex-col gap-2">
            {requests.map((r) => (
              <div key={r.request_id} className="flex items-center gap-3 bg-white/5 border border-white/10 rounded-2xl p-3" data-testid={`request-${r.user.username}`}>
                <AvatarCircle name={r.user.name} picture={r.user.picture} size={44} ring={false} />
                <div className="flex-1 min-w-0">
                  <p className="font-semibold truncate">{r.user.name}</p>
                  <p className="text-white/40 text-sm truncate">@{r.user.username}</p>
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
          Tus amigos ({friends.length})
        </p>
        {friends.length === 0 ? (
          <p className="text-white/40 text-sm py-4">
            Aún no tienes amigos añadidos. Búscalos arriba por su nombre de usuario.
          </p>
        ) : (
          <div className="flex flex-col gap-2">
            {friends.map((f) => (
              <div key={f.user_id} className="flex items-center gap-3 bg-white/5 border border-white/10 rounded-2xl p-3" data-testid={`friend-${f.username}`}>
                <AvatarCircle name={f.name} picture={f.picture} size={44} ring={false} />
                <div className="flex-1 min-w-0">
                  <p className="font-semibold truncate">{f.name}</p>
                  <p className="text-white/40 text-sm truncate">@{f.username}</p>
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
