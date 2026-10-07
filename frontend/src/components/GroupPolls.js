import { useMemo, useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import { BarChart3, Plus, Check, X, Loader2, CheckCircle2 } from "lucide-react";
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import api, { mediaThumb } from "@/lib/api";
import { toast } from "@/lib/notify";

function PollCard({ groupId, poll }) {
  const { t } = useTranslation();
  const qc = useQueryClient();
  const key = ["group-polls", groupId];

  const vote = useMutation({
    mutationFn: async (optionId) =>
      (await api.post(`/groups/${groupId}/polls/${poll.id}/vote`, { option_id: optionId })).data,
    onSuccess: () => qc.invalidateQueries({ queryKey: key }),
    onError: (e) => toast.error(e.response?.data?.detail || t("polls.err_vote", "No se pudo votar")),
  });
  const close = useMutation({
    mutationFn: async () => (await api.post(`/groups/${groupId}/polls/${poll.id}/close`)).data,
    onSuccess: () => qc.invalidateQueries({ queryKey: key }),
  });

  const open = poll.status === "open";
  const winner = useMemo(() => {
    if (open || !poll.options.length) return null;
    return poll.options.reduce((a, b) => (b.votes > a.votes ? b : a));
  }, [poll, open]);

  return (
    <div
      className="rounded-2xl border border-qv-primary/30 bg-gradient-to-br from-qv-primary/10 via-white/[0.03] to-transparent p-3.5"
      data-testid={`poll-card-${poll.id}`}
    >
      <div className="flex items-center gap-2 mb-3">
        <BarChart3 className="w-4 h-4 text-qv-primary shrink-0" />
        <p className="font-display font-black text-white text-sm leading-tight flex-1">{poll.title}</p>
        {!open && <span className="text-[10px] uppercase tracking-widest text-white/40 font-bold">{t("polls.closed", "Cerrada")}</span>}
      </div>

      <div className="flex flex-col gap-2">
        {poll.options.map((o) => {
          const mine = poll.my_vote === o.id;
          const isWinner = winner && winner.id === o.id;
          return (
            <button
              key={o.id}
              type="button"
              data-testid={`poll-option-${o.id}`}
              disabled={!open || vote.isPending}
              onClick={() => open && vote.mutate(o.id)}
              className={`relative w-full rounded-xl border overflow-hidden text-left active:scale-[0.99] transition-transform ${
                mine ? "border-qv-primary" : "border-white/12"
              } ${!open ? "opacity-90" : ""}`}
            >
              {/* vote bar fill */}
              <span
                className={`absolute inset-y-0 left-0 ${isWinner ? "bg-qv-secondary/25" : "bg-white/8"}`}
                style={{ width: `${o.pct}%`, transition: "width .4s ease" }}
              />
              <span className="relative flex items-center gap-2 px-3 py-2.5">
                {o.image_url ? (
                  <img src={mediaThumb(o.image_url, 80)} alt="" className="w-8 h-8 rounded-lg object-cover shrink-0" />
                ) : null}
                <span className="flex-1 min-w-0">
                  <span className="block text-sm font-semibold text-white truncate">{o.label}</span>
                  {(o.venue || o.date) && (
                    <span className="block text-[11px] text-white/45 truncate">{[o.venue, o.date].filter(Boolean).join(" · ")}</span>
                  )}
                </span>
                {mine && <Check className="w-4 h-4 text-qv-primary shrink-0" />}
                <span className="text-xs font-bold text-white/70 shrink-0 tabular-nums">{o.pct}%</span>
              </span>
            </button>
          );
        })}
      </div>

      <div className="flex items-center justify-between mt-2.5">
        <span className="text-[11px] text-white/40">{t("polls.total", { count: poll.total_votes, defaultValue: "{{count}} votos" })}</span>
        {open && poll.is_admin && (
          <button
            data-testid={`poll-close-${poll.id}`}
            onClick={() => close.mutate()}
            className="text-[11px] font-bold text-white/60 hover:text-white flex items-center gap-1"
          >
            <CheckCircle2 className="w-3.5 h-3.5" /> {t("polls.close_action", "Cerrar y decidir")}
          </button>
        )}
      </div>
    </div>
  );
}

function PollCreator({ groupId, onClose }) {
  const { t } = useTranslation();
  const qc = useQueryClient();
  const [title, setTitle] = useState("");
  const [selected, setSelected] = useState([]); // event ids
  const [customs, setCustoms] = useState([]); // free-text labels
  const [customText, setCustomText] = useState("");

  const { data: events = [], isLoading } = useQuery({
    queryKey: ["poll-events-all"],
    queryFn: async () =>
      (await api.get("/events", { params: { date_filter: "all", genre: "all", poll: 1 } })).data,
  });
  // The backend (poll=1) already returns the next parties ordered BY DATE — with
  // our affiliate clubs preferred only as a same-date tie-break — and limited to
  // the window today..Sunday-of-next-week. Keeping the ordering/window server-side
  // means future tweaks need no app update.
  const list = Array.isArray(events) ? events : events.items || events.events || [];

  const toggle = (eid) =>
    setSelected((prev) => (prev.includes(eid) ? prev.filter((x) => x !== eid) : prev.length + customs.length >= 4 ? prev : [...prev, eid]));

  const addCustom = () => {
    const v = customText.trim();
    if (!v) return;
    if (selected.length + customs.length >= 4) { toast(t("polls.max_options", "Máximo 4 opciones")); return; }
    setCustoms((p) => [...p, v]);
    setCustomText("");
  };

  const create = useMutation({
    mutationFn: async () => {
      const options = [
        ...selected.map((eid) => ({ event_id: eid })),
        ...customs.map((label) => ({ label })),
      ];
      return (await api.post(`/groups/${groupId}/polls`, { title: title.trim(), options })).data;
    },
    onSuccess: () => {
      toast.success(t("polls.created", "¡Encuesta creada!"));
      qc.invalidateQueries({ queryKey: ["group-polls", groupId] });
      qc.invalidateQueries({ queryKey: ["group-messages", groupId] });
      onClose();
    },
    onError: (e) => toast.error(e.response?.data?.detail || t("polls.err_create", "No se pudo crear")),
  });

  const totalOpts = selected.length + customs.length;

  return (
    <Dialog open onOpenChange={(o) => !o && onClose()}>
      <DialogContent className="bg-[#121215] border-white/10 text-white max-w-sm rounded-2xl max-h-[85vh] overflow-y-auto hide-scrollbar" data-testid="poll-creator">
        <DialogHeader><DialogTitle className="flex items-center gap-2"><BarChart3 className="w-5 h-5 text-qv-primary" /> {t("polls.new_title", "Encuesta del finde")}</DialogTitle></DialogHeader>
        <Input
          data-testid="poll-title-input"
          value={title}
          onChange={(e) => setTitle(e.target.value)}
          placeholder={t("polls.title_ph", "¿Dónde vamos el finde?")}
          className="h-11 bg-white/5 border-white/15 rounded-xl text-white placeholder:text-white/40"
        />
        <p className="text-white/50 text-xs mt-1">{t("polls.pick_hint", "Elige 2-4 planes candidatos de los próximos eventos")}</p>

        <div className="flex flex-col gap-2 mt-1">
          {isLoading ? (
            <div className="flex justify-center py-6"><Loader2 className="w-5 h-5 text-qv-primary animate-spin" /></div>
          ) : list.length === 0 ? (
            <p className="text-white/40 text-sm py-2">{t("polls.no_events", "No hay planes próximos — añade opciones a mano abajo.")}</p>
          ) : (
            list.slice(0, 60).map((ev) => {
              const on = selected.includes(ev.id);
              return (
                <button
                  key={ev.id}
                  type="button"
                  data-testid={`poll-event-option-${ev.id}`}
                  onClick={() => toggle(ev.id)}
                  className={`flex items-center gap-2.5 rounded-xl border p-2 text-left active:scale-[0.99] ${on ? "border-qv-primary bg-qv-primary/10" : "border-white/12"}`}
                >
                  {ev.image_url ? <img src={mediaThumb(ev.image_url, 80)} alt="" className="w-9 h-9 rounded-lg object-cover shrink-0" /> : <div className="w-9 h-9 rounded-lg bg-white/10 shrink-0" />}
                  <span className="flex-1 min-w-0">
                    <span className="block text-sm font-semibold text-white truncate">{ev.name}</span>
                    <span className="block text-[11px] text-white/45 truncate">{[ev.venue, ev.date].filter(Boolean).join(" · ")}</span>
                  </span>
                  <span className={`w-5 h-5 rounded-full border flex items-center justify-center shrink-0 ${on ? "bg-qv-primary border-qv-primary" : "border-white/30"}`}>
                    {on && <Check className="w-3 h-3 text-white" />}
                  </span>
                </button>
              );
            })
          )}
        </div>

        {/* custom options */}
        {customs.length > 0 && (
          <div className="flex flex-wrap gap-2 mt-1">
            {customs.map((c, i) => (
              <span key={i} className="flex items-center gap-1 rounded-full bg-white/8 border border-white/15 pl-3 pr-1.5 py-1 text-xs text-white">
                {c}
                <button onClick={() => setCustoms((p) => p.filter((_, idx) => idx !== i))} className="w-4 h-4 rounded-full bg-white/10 flex items-center justify-center"><X className="w-3 h-3" /></button>
              </span>
            ))}
          </div>
        )}
        <div className="flex gap-2 mt-1">
          <Input
            data-testid="poll-custom-input"
            value={customText}
            onChange={(e) => setCustomText(e.target.value)}
            onKeyDown={(e) => { if (e.key === "Enter") { e.preventDefault(); addCustom(); } }}
            placeholder={t("polls.custom_ph", "Otra opción (ej. Casa de Marta)")}
            className="h-10 bg-white/5 border-white/15 rounded-xl text-white placeholder:text-white/40 text-sm"
          />
          <button data-testid="poll-add-custom" onClick={addCustom} className="w-10 h-10 rounded-xl bg-white/10 border border-white/15 flex items-center justify-center shrink-0 active:scale-90">
            <Plus className="w-4 h-4 text-white" />
          </button>
        </div>

        <button
          data-testid="poll-submit"
          onClick={() => create.mutate()}
          disabled={totalOpts < 2 || create.isPending}
          className="h-12 mt-2 rounded-2xl bg-qv-primary text-white font-bold flex items-center justify-center gap-2 active:scale-95 disabled:opacity-50"
        >
          {create.isPending ? <Loader2 className="w-5 h-5 animate-spin" /> : <BarChart3 className="w-5 h-5" />}
          {t("polls.create_btn", "Lanzar encuesta")} {totalOpts > 0 ? `(${totalOpts})` : ""}
        </button>
      </DialogContent>
    </Dialog>
  );
}

// Group weekend poll block, shown at the top of a group chat. Members vote on
// where to go; the creator can close it to lock the plan.
export default function GroupPolls({ groupId }) {
  const { t } = useTranslation();
  const [creating, setCreating] = useState(false);

  const { data: polls = [] } = useQuery({
    queryKey: ["group-polls", groupId],
    queryFn: async () => (await api.get(`/groups/${groupId}/polls`)).data,
    refetchInterval: 8000,
  });

  const openPolls = polls.filter((p) => p.status === "open");
  const lastClosed = polls.find((p) => p.status === "closed");
  const visible = openPolls.length ? openPolls : lastClosed ? [lastClosed] : [];

  return (
    <div className="flex flex-col gap-2 mb-1" data-testid="group-polls">
      {visible.map((p) => (
        <PollCard key={p.id} groupId={groupId} poll={p} />
      ))}
      {!openPolls.length && (
        <button
          data-testid="create-poll-btn"
          onClick={() => setCreating(true)}
          className="h-12 rounded-2xl bg-gradient-to-r from-qv-primary/25 to-qv-secondary/15 border border-qv-primary/50 text-white font-bold text-sm flex items-center justify-center gap-2 active:scale-95 shadow-[0_0_16px_-4px_rgba(255,0,85,0.55)]"
        >
          <BarChart3 className="w-4 h-4 text-qv-primary" /> {t("polls.launch", "Montar encuesta: ¿a dónde vamos?")}
        </button>
      )}
      {creating && <PollCreator groupId={groupId} onClose={() => setCreating(false)} />}
    </div>
  );
}
