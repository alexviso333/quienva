import { useState, useMemo } from "react";
import { useQuery, useMutation } from "@tanstack/react-query";
import api from "@/lib/api";
import { Input } from "@/components/ui/input";
import { Bell, Search, Send, Loader2, Users, Globe, Check, Megaphone } from "lucide-react";
import { toast } from "sonner";

export default function AdminNotifyComposer() {
  const [presetId, setPresetId] = useState("");
  const [audience, setAudience] = useState("event"); // event | all
  const [eventId, setEventId] = useState("");
  const [eventName, setEventName] = useState("");
  const [body, setBody] = useState("");
  const [search, setSearch] = useState("");
  const [showList, setShowList] = useState(false);

  const { data: presetsData } = useQuery({
    queryKey: ["notify-presets"],
    queryFn: async () => (await api.get("/admin/notify/presets")).data,
    staleTime: 5 * 60_000,
  });
  const { data: eventsData } = useQuery({
    queryKey: ["events-min"],
    queryFn: async () => (await api.get("/admin/events-min")).data,
    staleTime: 60_000,
  });

  const presets = presetsData?.presets || [];
  const events = eventsData?.events || [];
  const filteredEvents = useMemo(() => {
    if (!search) return events.slice(0, 40);
    const s = search.toLowerCase();
    return events.filter((e) => e.name.toLowerCase().includes(s) || (e.venue || "").toLowerCase().includes(s)).slice(0, 40);
  }, [events, search]);

  // Live preview with {name} filled
  const preview = useMemo(() => body.replace(/\{name\}/g, eventName || "…"), [body, eventName]);
  const needsEvent = /\{name\}/.test(body) || audience === "event";

  const pickPreset = (p) => {
    setPresetId(p.id);
    setBody(p.body);
    if (!p.needs_event) setAudience("all");
    else setAudience("event");
  };

  const send = useMutation({
    mutationFn: async () => (await api.post("/admin/notify/send", {
      event_id: eventId,
      preset_id: presetId,
      body,
      audience,
    })).data,
    onSuccess: (d) => {
      toast.success(d.audience === "all" ? `Aviso enviado a ${d.notified} usuarios 📣` : `Aviso enviado a ${d.notified} interesados 📣`);
    },
    onError: (e) => toast.error(e.response?.data?.detail || "No se pudo enviar"),
  });

  const canSend = body.trim() && (!needsEvent || eventId);

  return (
    <div data-testid="admin-notify-composer">
      <h2 className="font-display text-base font-bold text-white mb-1 flex items-center gap-2">
        <Megaphone className="w-4 h-4 text-qv-primary" /> Enviar aviso
      </h2>
      <p className="text-white/40 text-xs mb-3">Elige un aviso predeterminado o escribe el tuyo y envíalo cuando quieras.</p>

      {/* Presets */}
      <div className="flex flex-wrap gap-1.5 mb-4">
        {presets.map((p) => (
          <button
            key={p.id}
            data-testid={`preset-${p.id}`}
            onClick={() => pickPreset(p)}
            className={`text-xs font-bold px-2.5 py-1.5 rounded-full border transition-colors ${presetId === p.id ? "bg-qv-primary text-white border-qv-primary" : "bg-white/5 text-white/70 border-white/10"}`}
          >
            {p.emoji} {p.label}
          </button>
        ))}
      </div>

      {/* Audience */}
      <p className="text-[11px] uppercase tracking-widest text-white/40 font-bold mb-2">¿A quién?</p>
      <div className="grid grid-cols-2 gap-2 mb-4">
        <button
          data-testid="audience-event"
          onClick={() => setAudience("event")}
          className={`p-3 rounded-2xl border flex items-center gap-2 ${audience === "event" ? "bg-qv-primary/15 border-qv-primary/50" : "bg-white/5 border-white/10"}`}
        >
          <Users className="w-4 h-4 text-qv-primary" />
          <span className="text-xs font-bold text-white text-left">Interesados en la fiesta</span>
          {audience === "event" && <Check className="w-4 h-4 text-qv-primary ml-auto" />}
        </button>
        <button
          data-testid="audience-all"
          onClick={() => setAudience("all")}
          className={`p-3 rounded-2xl border flex items-center gap-2 ${audience === "all" ? "bg-qv-secondary/15 border-qv-secondary/50" : "bg-white/5 border-white/10"}`}
        >
          <Globe className="w-4 h-4 text-qv-secondary" />
          <span className="text-xs font-bold text-white text-left">Todos los usuarios</span>
          {audience === "all" && <Check className="w-4 h-4 text-qv-secondary ml-auto" />}
        </button>
      </div>

      {/* Event dropdown */}
      {needsEvent && (
        <div className="mb-4">
          <p className="text-[11px] uppercase tracking-widest text-white/40 font-bold mb-2">Fiesta {eventName && <span className="text-qv-primary normal-case">· {eventName}</span>}</p>
          <div className="relative">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-white/40" />
            <Input
              data-testid="notify-event-search"
              value={search}
              onFocus={() => setShowList(true)}
              onChange={(e) => { setSearch(e.target.value); setShowList(true); }}
              placeholder={eventName || "Buscar y elegir fiesta..."}
              className="h-11 pl-9 bg-white/5 border-white/15 rounded-xl text-white placeholder:text-white/40"
            />
          </div>
          {showList && (
            <div className="mt-1.5 max-h-56 overflow-y-auto hide-scrollbar rounded-xl border border-white/10 bg-[#121215]">
              {filteredEvents.length === 0 ? (
                <p className="text-white/40 text-xs p-3">Sin resultados</p>
              ) : filteredEvents.map((e) => (
                <button
                  key={e.id}
                  data-testid={`notify-event-${e.id}`}
                  onClick={() => { setEventId(e.id); setEventName(e.name); setSearch(""); setShowList(false); }}
                  className={`w-full text-left px-3 py-2 flex items-center justify-between hover:bg-white/5 ${eventId === e.id ? "bg-qv-primary/10" : ""}`}
                >
                  <div className="min-w-0">
                    <p className="text-white text-sm font-semibold truncate">{e.name}</p>
                    <p className="text-white/40 text-[11px] truncate">{e.venue} · {e.date}</p>
                  </div>
                  {eventId === e.id && <Check className="w-4 h-4 text-qv-primary shrink-0" />}
                </button>
              ))}
            </div>
          )}
        </div>
      )}

      {/* Message */}
      <p className="text-[11px] uppercase tracking-widest text-white/40 font-bold mb-2">Mensaje</p>
      <textarea
        data-testid="notify-body"
        value={body}
        onChange={(e) => setBody(e.target.value)}
        rows={3}
        placeholder="Escribe el mensaje... usa {name} para incluir el nombre de la fiesta."
        className="w-full rounded-xl bg-white/5 border border-white/15 text-white p-3 text-sm placeholder:text-white/40 resize-none"
      />
      {body.includes("{name}") && (
        <p className="text-qv-secondary text-[11px] mt-1">Se sustituirá <span className="font-mono">{"{name}"}</span> por el nombre de la fiesta.</p>
      )}

      {/* Preview */}
      <div className="mt-3 rounded-2xl border border-white/10 bg-white/[0.03] p-3 flex items-start gap-2.5">
        <div className="w-9 h-9 rounded-xl bg-qv-primary/20 flex items-center justify-center shrink-0"><Bell className="w-4 h-4 text-qv-primary" /></div>
        <div className="min-w-0">
          <p className="text-white text-xs font-bold">¿Quién va?</p>
          <p className="text-white/70 text-xs mt-0.5 break-words">{preview || "Vista previa del aviso…"}</p>
        </div>
      </div>

      <button
        data-testid="notify-send"
        onClick={() => send.mutate()}
        disabled={!canSend || send.isPending}
        className="w-full mt-4 h-12 rounded-2xl bg-gradient-to-r from-qv-primary to-qv-secondary text-black font-display font-black flex items-center justify-center gap-2 active:scale-95 disabled:opacity-40"
      >
        {send.isPending ? <Loader2 className="w-5 h-5 animate-spin" /> : <><Send className="w-4 h-4" /> Enviar aviso</>}
      </button>
      {!canSend && needsEvent && !eventId && (
        <p className="text-white/40 text-[11px] text-center mt-2">Elige una fiesta para poder enviar.</p>
      )}
    </div>
  );
}
