import { useState, useMemo } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import api from "@/lib/api";
import { Input } from "@/components/ui/input";
import { Bell, Search, Send, Loader2, Users, Globe, Check, Megaphone, MapPin, Music, Clock, Calendar, Trash2 } from "lucide-react";
import { toast } from "sonner";

const AUDIENCES = [
  { id: "event", label: "Interesados en la fiesta", icon: Users, color: "text-qv-primary" },
  { id: "all", label: "Todos los usuarios", icon: Globe, color: "text-qv-secondary" },
  { id: "city", label: "Por ciudad", icon: MapPin, color: "text-emerald-300" },
  { id: "genre", label: "Por género", icon: Music, color: "text-fuchsia-300" },
];

export default function AdminNotifyComposer() {
  const qc = useQueryClient();
  const [presetId, setPresetId] = useState("");
  const [audience, setAudience] = useState("event");
  const [eventId, setEventId] = useState("");
  const [eventName, setEventName] = useState("");
  const [body, setBody] = useState("");
  const [search, setSearch] = useState("");
  const [showList, setShowList] = useState(false);
  const [city, setCity] = useState("Palma de Mallorca");
  const [genre, setGenre] = useState("");
  const [sendAt, setSendAt] = useState("");
  const [schedule, setSchedule] = useState(false);

  const { data: presetsData } = useQuery({ queryKey: ["notify-presets"], queryFn: async () => (await api.get("/admin/notify/presets")).data, staleTime: 5 * 60_000 });
  const { data: eventsData } = useQuery({ queryKey: ["events-min"], queryFn: async () => (await api.get("/admin/events-min")).data, staleTime: 60_000 });
  const { data: genresData } = useQuery({ queryKey: ["event-genres-admin"], queryFn: async () => (await api.get("/events/genres")).data, staleTime: 5 * 60_000 });
  const { data: scheduledData } = useQuery({ queryKey: ["notify-scheduled"], queryFn: async () => (await api.get("/admin/notify/scheduled")).data, staleTime: 20_000 });

  const presets = presetsData?.presets || [];
  const events = eventsData?.events || [];
  const genres = genresData || [];
  const scheduled = scheduledData?.scheduled || [];

  const cities = useMemo(() => {
    const s = new Set(["Palma de Mallorca"]);
    return Array.from(s);
  }, []);

  const filteredEvents = useMemo(() => {
    if (!search) return events.slice(0, 40);
    const s = search.toLowerCase();
    return events.filter((e) => e.name.toLowerCase().includes(s) || (e.venue || "").toLowerCase().includes(s)).slice(0, 40);
  }, [events, search]);

  const preview = useMemo(() => body.replace(/\{name\}/g, eventName || "…"), [body, eventName]);
  const needsEvent = /\{name\}/.test(body) || audience === "event";

  const pickPreset = (p) => {
    setPresetId(p.id);
    setBody(p.body);
    if (!p.needs_event && audience === "event") setAudience("all");
    else if (p.needs_event) setAudience("event");
  };

  const send = useMutation({
    mutationFn: async () => (await api.post("/admin/notify/send", {
      event_id: eventId, preset_id: presetId, body, audience,
      city: audience === "city" ? city : "",
      genre: audience === "genre" ? genre : "",
      send_at: schedule && sendAt ? new Date(sendAt).toISOString() : "",
    })).data,
    onSuccess: (d) => {
      if (d.scheduled) toast.success("Aviso programado ⏰");
      else toast.success(`Aviso enviado a ${d.notified} ${d.audience === "event" ? "interesados" : "usuarios"} 📣`);
      qc.invalidateQueries({ queryKey: ["notify-scheduled"] });
    },
    onError: (e) => toast.error(e.response?.data?.detail || "No se pudo enviar"),
  });

  const cancelSched = useMutation({
    mutationFn: async (id) => (await api.delete(`/admin/notify/scheduled/${id}`)).data,
    onSuccess: () => { toast.success("Programación cancelada"); qc.invalidateQueries({ queryKey: ["notify-scheduled"] }); },
    onError: () => toast.error("Error"),
  });

  const canSend = body.trim() && (!needsEvent || eventId) && (audience !== "genre" || genre) && (!schedule || sendAt);

  return (
    <div data-testid="admin-notify-composer">
      <h2 className="font-display text-base font-bold text-white mb-1 flex items-center gap-2">
        <Megaphone className="w-4 h-4 text-qv-primary" /> Enviar aviso
      </h2>
      <p className="text-white/40 text-xs mb-3">Elige un aviso predeterminado o escribe el tuyo. Envíalo ahora o prográmalo.</p>

      {/* Presets */}
      <div className="flex flex-wrap gap-1.5 mb-4">
        {presets.map((p) => (
          <button key={p.id} data-testid={`preset-${p.id}`} onClick={() => pickPreset(p)}
            className={`text-xs font-bold px-2.5 py-1.5 rounded-full border transition-colors ${presetId === p.id ? "bg-qv-primary text-white border-qv-primary" : "bg-white/5 text-white/70 border-white/10"}`}>
            {p.emoji} {p.label}
          </button>
        ))}
      </div>

      {/* Audience */}
      <p className="text-[11px] uppercase tracking-widest text-white/40 font-bold mb-2">¿A quién?</p>
      <div className="grid grid-cols-2 gap-2 mb-3">
        {AUDIENCES.map((a) => {
          const Icon = a.icon;
          const on = audience === a.id;
          return (
            <button key={a.id} data-testid={`audience-${a.id}`} onClick={() => setAudience(a.id)}
              className={`p-3 rounded-2xl border flex items-center gap-2 ${on ? "bg-white/10 border-white/40" : "bg-white/5 border-white/10"}`}>
              <Icon className={`w-4 h-4 ${a.color}`} />
              <span className="text-xs font-bold text-white text-left flex-1">{a.label}</span>
              {on && <Check className="w-4 h-4 text-white ml-auto" />}
            </button>
          );
        })}
      </div>

      {/* City selector */}
      {audience === "city" && (
        <div className="mb-3">
          <select data-testid="notify-city" value={city} onChange={(e) => setCity(e.target.value)}
            className="w-full h-11 rounded-xl bg-white/5 border border-white/15 text-white px-3 text-sm">
            {cities.map((c) => <option key={c} value={c}>{c}</option>)}
          </select>
        </div>
      )}

      {/* Genre selector */}
      {audience === "genre" && (
        <div className="mb-3">
          <select data-testid="notify-genre" value={genre} onChange={(e) => setGenre(e.target.value)}
            className="w-full h-11 rounded-xl bg-white/5 border border-white/15 text-white px-3 text-sm">
            <option value="">Elige un género…</option>
            {genres.map((g) => <option key={g} value={g}>{g}</option>)}
          </select>
        </div>
      )}

      {/* Event dropdown */}
      {needsEvent && (
        <div className="mb-3">
          <p className="text-[11px] uppercase tracking-widest text-white/40 font-bold mb-2">Fiesta {eventName && <span className="text-qv-primary normal-case">· {eventName}</span>}</p>
          <div className="relative">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-white/40" />
            <Input data-testid="notify-event-search" value={search} onFocus={() => setShowList(true)}
              onChange={(e) => { setSearch(e.target.value); setShowList(true); }}
              placeholder={eventName || "Buscar y elegir fiesta..."}
              className="h-11 pl-9 bg-white/5 border-white/15 rounded-xl text-white placeholder:text-white/40" />
          </div>
          {showList && (
            <div className="mt-1.5 max-h-56 overflow-y-auto hide-scrollbar rounded-xl border border-white/10 bg-[#121215]">
              {filteredEvents.length === 0 ? <p className="text-white/40 text-xs p-3">Sin resultados</p> :
                filteredEvents.map((e) => (
                  <button key={e.id} data-testid={`notify-event-${e.id}`}
                    onClick={() => { setEventId(e.id); setEventName(e.name); setSearch(""); setShowList(false); }}
                    className={`w-full text-left px-3 py-2 flex items-center justify-between hover:bg-white/5 ${eventId === e.id ? "bg-qv-primary/10" : ""}`}>
                    <div className="min-w-0"><p className="text-white text-sm font-semibold truncate">{e.name}</p><p className="text-white/40 text-[11px] truncate">{e.venue} · {e.date}</p></div>
                    {eventId === e.id && <Check className="w-4 h-4 text-qv-primary shrink-0" />}
                  </button>
                ))}
            </div>
          )}
        </div>
      )}

      {/* Message */}
      <p className="text-[11px] uppercase tracking-widest text-white/40 font-bold mb-2">Mensaje</p>
      <textarea data-testid="notify-body" value={body} onChange={(e) => setBody(e.target.value)} rows={3}
        placeholder="Escribe el mensaje... usa {name} para incluir el nombre de la fiesta."
        className="w-full rounded-xl bg-white/5 border border-white/15 text-white p-3 text-sm placeholder:text-white/40 resize-none" />
      {body.includes("{name}") && (
        <p className="text-qv-secondary text-[11px] mt-1">Se sustituirá <span className="font-mono">{"{name}"}</span> por el nombre de la fiesta.</p>
      )}

      {/* Preview */}
      <div className="mt-3 rounded-2xl border border-white/10 bg-white/[0.03] p-3 flex items-start gap-2.5">
        <div className="w-9 h-9 rounded-xl bg-qv-primary/20 flex items-center justify-center shrink-0"><Bell className="w-4 h-4 text-qv-primary" /></div>
        <div className="min-w-0"><p className="text-white text-xs font-bold">¿Quién va?</p><p className="text-white/70 text-xs mt-0.5 break-words">{preview || "Vista previa del aviso…"}</p></div>
      </div>

      {/* Schedule */}
      <button data-testid="notify-schedule-toggle" onClick={() => setSchedule((v) => !v)}
        className={`w-full mt-3 h-11 rounded-xl border flex items-center justify-center gap-2 text-sm font-bold active:scale-95 ${schedule ? "bg-qv-secondary/15 border-qv-secondary/40 text-qv-secondary" : "bg-white/5 border-white/15 text-white/70"}`}>
        <Clock className="w-4 h-4" /> {schedule ? "Programado para más tarde" : "Programar para más tarde"}
      </button>
      {schedule && (
        <input data-testid="notify-sendat" type="datetime-local" value={sendAt} onChange={(e) => setSendAt(e.target.value)}
          className="w-full mt-2 h-11 rounded-xl bg-white/5 border border-white/15 text-white px-3 text-sm" />
      )}

      <button data-testid="notify-send" onClick={() => send.mutate()} disabled={!canSend || send.isPending}
        className="w-full mt-4 h-12 rounded-2xl bg-gradient-to-r from-qv-primary to-qv-secondary text-black font-display font-black flex items-center justify-center gap-2 active:scale-95 disabled:opacity-40">
        {send.isPending ? <Loader2 className="w-5 h-5 animate-spin" /> : schedule ? <><Clock className="w-4 h-4" /> Programar aviso</> : <><Send className="w-4 h-4" /> Enviar aviso</>}
      </button>

      {/* Scheduled list */}
      {scheduled.length > 0 && (
        <div className="mt-6">
          <p className="text-[11px] uppercase tracking-widest text-white/40 font-bold mb-2 flex items-center gap-1.5"><Calendar className="w-3.5 h-3.5" /> Programados ({scheduled.length})</p>
          <div className="space-y-1.5">
            {scheduled.map((s) => (
              <div key={s.id} className="rounded-xl bg-white/[0.04] border border-white/10 p-2.5 flex items-center gap-3" data-testid={`sched-${s.id}`}>
                <div className="flex-1 min-w-0">
                  <p className="text-white text-xs font-semibold truncate">{s.body}</p>
                  <p className="text-white/40 text-[10px]">{new Date(s.send_at).toLocaleString("es-ES")} · {s.audience}{s.event_name ? ` · ${s.event_name}` : ""}</p>
                </div>
                <button onClick={() => cancelSched.mutate(s.id)} className="w-8 h-8 rounded-full bg-white/5 flex items-center justify-center active:scale-90" data-testid={`sched-cancel-${s.id}`}>
                  <Trash2 className="w-4 h-4 text-red-400" />
                </button>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
