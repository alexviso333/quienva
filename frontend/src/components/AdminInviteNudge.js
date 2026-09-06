import { useEffect, useMemo, useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import api, { formatApiErrorDetail } from "@/lib/api";
import { AvatarCircle } from "@/components/AvatarCircle";
import { Input } from "@/components/ui/input";
import { Megaphone, ChevronDown, ChevronRight, Search, Loader2, Check, Users2, Gift, Send, UserPlus, Clock } from "lucide-react";
import { toast } from "sonner";

const ACTIONS = [
  { id: "group", label: "Montar grupo", icon: Users2 },
  { id: "friends", label: "Añadir amigos", icon: UserPlus },
  { id: "both", label: "Ambas", icon: Megaphone },
];
const TARGETS = [
  { id: "group", label: "Sin grupo" },
  { id: "friends", label: "Sin amigos" },
  { id: "both", label: "Sin grupo o sin amigos" },
];

function StatPill({ value, label, color }) {
  return (
    <div className="flex-1 rounded-xl bg-black/25 border border-white/10 p-2 text-center">
      <p className={`font-display text-lg font-black ${color}`}>{value ?? 0}</p>
      <p className="text-white/50 text-[10px] leading-tight">{label}</p>
    </div>
  );
}

// Admin "Empujón para invitar": pick users (manual) or turn on automatic mode,
// plus a campaign follow-up showing how many nudged users converted.
export default function AdminInviteNudge() {
  const qc = useQueryClient();
  const [open, setOpen] = useState(false);
  const [search, setSearch] = useState("");
  const [selected, setSelected] = useState({});
  const [presetId, setPresetId] = useState("both");
  const [body, setBody] = useState("");
  const [action, setAction] = useState("both");
  // auto config local state
  const [autoMode, setAutoMode] = useState(false);
  const [intervalDays, setIntervalDays] = useState(7);
  const [target, setTarget] = useState("both");

  const { data: presets = [] } = useQuery({
    queryKey: ["invite-nudge-presets"],
    queryFn: async () => (await api.get("/admin/invite-nudge/presets")).data.presets,
    enabled: open, staleTime: 60 * 60_000,
  });
  const { data: stats } = useQuery({
    queryKey: ["invite-nudge-stats"],
    queryFn: async () => (await api.get("/admin/invite-nudge/stats")).data,
    enabled: open, staleTime: 15_000,
  });
  const { data: config } = useQuery({
    queryKey: ["invite-nudge-config"],
    queryFn: async () => (await api.get("/admin/invite-nudge/config")).data,
    enabled: open, staleTime: 60_000,
  });
  const { data: users = [], isLoading } = useQuery({
    queryKey: ["admin-users-nudge", search],
    queryFn: async () => (await api.get("/admin/users", { params: { search } })).data,
    enabled: open, staleTime: 15_000,
  });

  useEffect(() => {
    if (config) {
      setAutoMode(config.mode === "auto");
      setIntervalDays(config.interval_days || 7);
      setTarget(config.target || "both");
    }
  }, [config]);

  const selectedIds = useMemo(() => Object.keys(selected).filter((k) => selected[k]), [selected]);
  const applyPreset = (p) => { setPresetId(p.id); setBody(p.body); setAction(p.action || "both"); };
  const toggle = (uid) => setSelected((s) => ({ ...s, [uid]: !s[uid] }));

  const send = useMutation({
    mutationFn: async () => (await api.post("/admin/invite-nudge", {
      user_ids: selectedIds, preset_id: body ? "" : presetId, body: body.trim(), action,
    })).data,
    onSuccess: (d) => {
      toast.success(`Empujón enviado a ${d.sent} usuario${d.sent === 1 ? "" : "s"} 📣`);
      setSelected({});
      qc.invalidateQueries({ queryKey: ["invite-nudge-stats"] });
    },
    onError: (e) => toast.error(formatApiErrorDetail(e.response?.data?.detail) || "No se pudo enviar"),
  });

  const saveConfig = useMutation({
    mutationFn: async () => (await api.put("/admin/invite-nudge/config", {
      mode: autoMode ? "auto" : "manual",
      interval_days: Number(intervalDays) || 7,
      target,
      preset_id: body ? "" : presetId,
      body: body.trim(),
      action,
    })).data,
    onSuccess: () => {
      toast.success(autoMode ? "Auto-empujón activado ✅" : "Guardado en modo manual");
      qc.invalidateQueries({ queryKey: ["invite-nudge-config"] });
    },
    onError: (e) => toast.error(formatApiErrorDetail(e.response?.data?.detail) || "No se pudo guardar"),
  });

  return (
    <div className="mb-6 rounded-2xl border border-qv-primary/30 bg-gradient-to-br from-qv-primary/10 via-white/[0.02] to-transparent overflow-hidden" data-testid="admin-invite-nudge">
      <button onClick={() => setOpen((o) => !o)} data-testid="invite-nudge-toggle" className="w-full flex items-center gap-2.5 p-3.5 text-left active:scale-[0.99]">
        <div className="w-9 h-9 rounded-full bg-qv-primary/20 flex items-center justify-center shrink-0"><Megaphone className="w-4.5 h-4.5 text-qv-primary" /></div>
        <div className="flex-1 min-w-0">
          <p className="font-display font-bold text-white text-sm">Empujón para invitar</p>
          <p className="text-white/50 text-xs">Elige usuarios o actívalo en automático</p>
        </div>
        {selectedIds.length > 0 && <span className="text-[11px] font-bold text-black bg-qv-primary rounded-full px-2 py-0.5" data-testid="invite-nudge-selcount">{selectedIds.length}</span>}
        {open ? <ChevronDown className="w-5 h-5 text-white/40" /> : <ChevronRight className="w-5 h-5 text-white/40" />}
      </button>

      {open && (
        <div className="px-3.5 pb-3.5">
          {/* Campaign follow-up */}
          <div className="mb-3" data-testid="nudge-stats">
            <p className="text-[11px] uppercase tracking-widest text-white/40 font-bold mb-1.5">Seguimiento de campaña</p>
            <div className="flex gap-1.5">
              <StatPill value={stats?.total_nudged} label="empujados" color="text-white" />
              <StatPill value={stats?.converted} label="convirtieron" color="text-emerald-300" />
              <StatPill value={stats?.created_group} label="crearon grupo" color="text-qv-primary" />
              <StatPill value={stats?.invited} label="invitaron" color="text-qv-secondary" />
            </div>
          </div>

          {/* Message (shared by manual + auto) */}
          <div className="rounded-xl bg-black/30 border border-white/10 p-3 mb-3">
            <p className="text-[11px] uppercase tracking-widest text-white/40 font-bold mb-2">Mensaje</p>
            <div className="flex flex-wrap gap-1.5 mb-2">
              {presets.map((p) => (
                <button key={p.id} data-testid={`nudge-preset-${p.id}`} onClick={() => applyPreset(p)} className={`text-xs font-semibold rounded-full px-2.5 py-1 border ${presetId === p.id && !body ? "bg-qv-primary/20 border-qv-primary text-white" : "bg-white/5 border-white/12 text-white/70"}`}>{p.emoji} {p.label}</button>
              ))}
            </div>
            <textarea data-testid="nudge-body" value={body} onChange={(e) => setBody(e.target.value)} rows={2} placeholder="Mensaje personalizado (o elige un preset)…" className="w-full rounded-xl bg-white/5 border border-white/15 p-2.5 text-sm text-white placeholder:text-white/35 focus:outline-none focus:border-qv-primary/50 resize-none" />
            <p className="text-[11px] uppercase tracking-widest text-white/40 font-bold mt-3 mb-1.5">Al abrir la app, llévales a…</p>
            <div className="grid grid-cols-3 gap-1.5">
              {ACTIONS.map((a) => (
                <button key={a.id} data-testid={`nudge-action-${a.id}`} onClick={() => setAction(a.id)} className={`h-10 rounded-xl border text-xs font-bold flex items-center justify-center gap-1 ${action === a.id ? "bg-qv-secondary/15 border-qv-secondary text-white" : "bg-white/5 border-white/12 text-white/60"}`}><a.icon className="w-3.5 h-3.5" /> {a.label}</button>
              ))}
            </div>
          </div>

          {/* Automatic mode */}
          <div className="rounded-xl bg-black/30 border border-white/10 p-3 mb-3" data-testid="nudge-auto">
            <div className="flex items-center gap-2.5">
              <Clock className="w-4 h-4 text-qv-primary shrink-0" />
              <div className="flex-1 min-w-0">
                <p className="text-white text-sm font-semibold">Modo automático</p>
                <p className="text-white/45 text-[11px] leading-tight">Empuja solo a quien cumpla el criterio, cada X días</p>
              </div>
              <button
                data-testid="nudge-auto-toggle"
                onClick={() => setAutoMode((v) => !v)}
                className={`w-12 h-7 rounded-full relative transition-colors shrink-0 ${autoMode ? "bg-qv-primary" : "bg-white/15"}`}
              >
                <span className={`absolute top-0.5 w-6 h-6 rounded-full bg-white transition-all ${autoMode ? "left-[22px]" : "left-0.5"}`} />
              </button>
            </div>

            {autoMode && (
              <div className="mt-3 flex flex-col gap-2.5" data-testid="nudge-auto-config">
                <div className="flex items-center gap-2">
                  <span className="text-white/60 text-xs">Cada</span>
                  <Input data-testid="nudge-interval" type="number" min={1} max={90} value={intervalDays} onChange={(e) => setIntervalDays(e.target.value)} className="h-9 w-20 bg-white/5 border-white/15 rounded-xl text-white text-center" />
                  <span className="text-white/60 text-xs">días</span>
                </div>
                <div>
                  <p className="text-[11px] uppercase tracking-widest text-white/40 font-bold mb-1.5">Avisar a usuarios…</p>
                  <div className="grid grid-cols-3 gap-1.5">
                    {TARGETS.map((tg) => (
                      <button key={tg.id} data-testid={`nudge-target-${tg.id}`} onClick={() => setTarget(tg.id)} className={`h-11 rounded-xl border text-[11px] font-bold flex items-center justify-center text-center leading-tight px-1 ${target === tg.id ? "bg-qv-primary/15 border-qv-primary text-white" : "bg-white/5 border-white/12 text-white/60"}`}>{tg.label}</button>
                    ))}
                  </div>
                </div>
              </div>
            )}

            <button data-testid="nudge-save-config" onClick={() => saveConfig.mutate()} disabled={saveConfig.isPending} className="w-full h-10 mt-3 rounded-xl bg-white/10 border border-white/15 text-white font-bold text-sm flex items-center justify-center gap-2 active:scale-95 disabled:opacity-50">
              {saveConfig.isPending ? <Loader2 className="w-4 h-4 animate-spin" /> : null}
              {autoMode ? "Activar auto-empujón" : "Guardar (modo manual)"}
            </button>
          </div>

          {/* Manual picker */}
          <p className="text-[11px] uppercase tracking-widest text-white/40 font-bold mb-1.5">Envío manual</p>
          <div className="relative mb-2">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-white/40" />
            <Input data-testid="nudge-search" value={search} onChange={(e) => setSearch(e.target.value)} placeholder="Buscar usuarios…" className="h-10 pl-9 bg-white/5 border-white/15 rounded-xl text-white placeholder:text-white/40" />
          </div>
          {isLoading ? (
            <div className="flex justify-center py-6"><Loader2 className="w-5 h-5 text-qv-primary animate-spin" /></div>
          ) : (
            <div className="flex flex-col gap-1.5 max-h-[340px] overflow-y-auto hide-scrollbar">
              {users.map((u) => {
                const on = !!selected[u.user_id];
                const st = u._stats || {};
                return (
                  <button key={u.user_id} data-testid={`nudge-user-${u.user_id}`} onClick={() => toggle(u.user_id)} className={`rounded-xl border p-2.5 flex items-center gap-3 text-left active:scale-[0.99] ${on ? "bg-qv-primary/10 border-qv-primary" : "bg-white/[0.03] border-white/10"}`}>
                    <AvatarCircle name={u.name} picture={u.picture} size={36} />
                    <div className="flex-1 min-w-0">
                      <p className="font-semibold text-sm text-white truncate">{u.name}</p>
                      <div className="flex flex-wrap items-center gap-x-2.5 gap-y-0.5 mt-0.5 text-[11px]">
                        <span className="text-white/55 flex items-center gap-1"><UserPlus className="w-3 h-3" /> {st.friends || 0} amigos</span>
                        <span className="text-white/55 flex items-center gap-1"><Users2 className="w-3 h-3" /> {st.groups || 0} grupos</span>
                        <span className="text-emerald-300/80 flex items-center gap-1"><Gift className="w-3 h-3" /> {st.referred || 0} registrados</span>
                        <span className="text-white/45 flex items-center gap-1"><Send className="w-3 h-3" /> {st.invites_sent || 0} enviados</span>
                      </div>
                    </div>
                    <span className={`w-6 h-6 rounded-full border flex items-center justify-center shrink-0 ${on ? "bg-qv-primary border-qv-primary" : "border-white/30"}`}>{on && <Check className="w-3.5 h-3.5 text-white" />}</span>
                  </button>
                );
              })}
              {users.length === 0 && <p className="text-center text-white/40 text-sm py-6">Ningún usuario coincide</p>}
            </div>
          )}

          <button data-testid="nudge-send" onClick={() => send.mutate()} disabled={selectedIds.length === 0 || send.isPending} className="w-full h-12 mt-3 rounded-2xl bg-qv-primary text-white font-bold flex items-center justify-center gap-2 active:scale-95 disabled:opacity-50">
            {send.isPending ? <Loader2 className="w-5 h-5 animate-spin" /> : <Send className="w-5 h-5" />}
            Enviar empujón {selectedIds.length > 0 ? `(${selectedIds.length})` : ""}
          </button>
        </div>
      )}
    </div>
  );
}
