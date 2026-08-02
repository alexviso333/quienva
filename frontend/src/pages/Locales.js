import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { useNavigate } from "react-router-dom";
import api from "@/lib/api";
import { AppShell } from "@/components/AppShell";
import { Loader2, MapPin, Instagram, Ticket, PartyPopper, ChevronDown, ChevronUp, DoorOpen, Map } from "lucide-react";

const DAYS = ["L", "M", "X", "J", "V", "S", "D"];
const TYPE_LABEL = { discoteca: "Discoteca", pub: "Pub", beach_club: "Beach club", promotor: "Promotor" };
const TYPE_COLOR = {
  discoteca: "bg-fuchsia-500/20 text-fuchsia-200",
  pub: "bg-emerald-500/20 text-emerald-200",
  beach_club: "bg-cyan-500/20 text-cyan-200",
  promotor: "bg-amber-500/20 text-amber-200",
};

function VenueCard({ v }) {
  const navigate = useNavigate();
  const [open, setOpen] = useState(false);
  const { data: detail, isLoading } = useQuery({
    queryKey: ["venue", v.id],
    queryFn: async () => (await api.get(`/venues/${v.id}`)).data,
    enabled: open && v.upcoming_events > 0,
    staleTime: 60_000,
  });
  const maps = `https://www.google.com/maps/search/?api=1&query=${encodeURIComponent(v.name + " " + (v.address || v.city))}`;

  return (
    <div className="rounded-2xl border border-white/10 bg-white/[0.04] overflow-hidden" data-testid={`venue-${v.id}`}>
      {v.image_url && (
        <div className="h-24 w-full bg-cover bg-center" style={{ backgroundImage: `url(${v.image_url})` }}>
          <div className="h-full w-full bg-gradient-to-t from-[#12040a] via-transparent to-transparent" />
        </div>
      )}
      <div className="p-3">
      <div className="flex items-start gap-3">
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 flex-wrap">
            <p className="font-bold text-[15px] text-white truncate">{v.name}</p>
            <span className={`text-[9px] px-1.5 py-0.5 rounded-full uppercase font-bold ${TYPE_COLOR[v.type] || "bg-white/10 text-white/60"}`}>
              {TYPE_LABEL[v.type] || v.type}
            </span>
            {v.free_entry && (
              <span className="text-[9px] px-1.5 py-0.5 rounded-full bg-emerald-400/20 text-emerald-200 uppercase font-bold flex items-center gap-0.5">
                <DoorOpen className="w-3 h-3" /> Libre
              </span>
            )}
          </div>
          <p className="text-white/45 text-[11px] mt-0.5 flex items-center gap-1">
            <MapPin className="w-3 h-3" /> {v.zone}
          </p>
          {/* Open days */}
          <div className="flex items-center gap-1 mt-2">
            {DAYS.map((d, i) => {
              const on = (v.open_days || []).includes(i);
              return (
                <span
                  key={i}
                  className={`w-5 h-5 rounded-md text-[10px] font-bold flex items-center justify-center ${
                    on ? "bg-qv-primary text-black" : "bg-white/5 text-white/30"
                  }`}
                >
                  {d}
                </span>
              );
            })}
            {(!v.open_days || v.open_days.length === 0) && (
              <span className="text-white/30 text-[10px] ml-1">horario por confirmar</span>
            )}
          </div>
        </div>
      </div>

      {/* Actions */}
      <div className="mt-3 flex flex-wrap gap-1.5">
        {v.upcoming_events > 0 && (
          <button
            onClick={() => setOpen((o) => !o)}
            className="text-[11px] font-bold text-black bg-qv-primary rounded-lg px-2.5 py-1.5 flex items-center gap-1 active:scale-95"
            data-testid={`venue-events-${v.id}`}
          >
            <PartyPopper className="w-3.5 h-3.5" /> {v.upcoming_events} fiestas
            {open ? <ChevronUp className="w-3.5 h-3.5" /> : <ChevronDown className="w-3.5 h-3.5" />}
          </button>
        )}
        {v.upcoming_events === 0 && (
          <span className="text-[11px] text-white/35 px-1 py-1.5">Sin fiestas anunciadas</span>
        )}
        <a
          href={maps}
          target="_blank"
          rel="noreferrer"
          className="text-[11px] font-bold text-white bg-white/10 rounded-lg px-2.5 py-1.5 flex items-center gap-1 active:scale-95"
        >
          <MapPin className="w-3.5 h-3.5" /> Cómo llegar
        </a>
        {v.instagram && (
          <a
            href={`https://instagram.com/${v.instagram}`}
            target="_blank"
            rel="noreferrer"
            className="text-[11px] font-bold text-white bg-white/10 rounded-lg px-2.5 py-1.5 flex items-center gap-1 active:scale-95"
          >
            <Instagram className="w-3.5 h-3.5" /> Instagram
          </a>
        )}
      </div>

      {/* Expanded events */}
      {open && (
        <div className="mt-3 flex flex-col gap-2 border-t border-white/10 pt-3">
          {isLoading && <div className="flex justify-center py-3"><Loader2 className="w-4 h-4 animate-spin text-white/40" /></div>}
          {detail?.events?.map((e) => (
            <button
              key={e.id}
              onClick={() => navigate(`/event/${e.id}`)}
              className="flex items-center gap-3 text-left active:scale-[0.99]"
            >
              <div className="w-12 h-12 rounded-lg bg-white/5 bg-cover bg-center flex-shrink-0"
                   style={{ backgroundImage: e.image_url ? `url(${e.image_url})` : "none" }} />
              <div className="flex-1 min-w-0">
                <p className="text-white text-[13px] font-semibold truncate">{e.name}</p>
                <p className="text-white/45 text-[11px]">
                  {new Date(e.date).toLocaleDateString("es-ES", { weekday: "short", day: "numeric", month: "short" })}
                  {e.time ? ` · ${e.time}` : ""}
                </p>
              </div>
              {e.current_price != null && (
                <span className="text-[11px] font-bold text-qv-secondary flex items-center gap-0.5">
                  <Ticket className="w-3 h-3" />{Math.round(e.current_price)}€
                </span>
              )}
            </button>
          ))}
        </div>
      )}
      </div>
    </div>
  );
}

export default function Locales() {
  const [zone, setZone] = useState("");
  const navigate = useNavigate();
  const { data: venues = [], isLoading } = useQuery({
    queryKey: ["venues"],
    queryFn: async () => (await api.get("/venues")).data,
    staleTime: 60_000,
  });

  const zones = Array.from(new Set(venues.map((v) => v.zone)));
  const filtered = zone ? venues.filter((v) => v.zone === zone) : venues;

  return (
    <AppShell>
      <header className="px-5 pt-8 pb-2 flex items-start justify-between gap-3">
        <div>
          <p className="text-xs tracking-[0.25em] uppercase text-qv-secondary font-bold">Mallorca</p>
          <h1 className="font-display text-4xl font-black tracking-tighter mt-1">
            Locales<span className="text-qv-primary">.</span>
          </h1>
          <p className="text-white/50 text-sm mt-1">Discotecas y pubs de la isla, con días de apertura y sus fiestas.</p>
        </div>
        <button
          data-testid="locales-map-btn"
          onClick={() => navigate("/mapa")}
          className="mt-1 shrink-0 flex items-center gap-1.5 text-xs font-bold text-black bg-qv-secondary rounded-full px-3 py-2 active:scale-95"
        >
          <Map className="w-4 h-4" /> Mapa
        </button>
      </header>

      {/* Zone filter */}
      <div className="px-4 pb-3 flex gap-2 overflow-x-auto no-scrollbar">
        <button
          onClick={() => setZone("")}
          className={`whitespace-nowrap text-xs font-bold rounded-full px-3 py-1.5 ${zone === "" ? "bg-qv-primary text-black" : "bg-white/10 text-white/70"}`}
        >
          Todas
        </button>
        {zones.map((z) => (
          <button
            key={z}
            onClick={() => setZone(z)}
            className={`whitespace-nowrap text-xs font-bold rounded-full px-3 py-1.5 ${zone === z ? "bg-qv-primary text-black" : "bg-white/10 text-white/70"}`}
          >
            {z}
          </button>
        ))}
      </div>

      {isLoading ? (
        <div className="py-16 flex justify-center"><Loader2 className="w-6 h-6 animate-spin text-white/50" /></div>
      ) : (
        <div className="px-4 pb-28 flex flex-col gap-2.5">
          {filtered.map((v) => <VenueCard key={v.id} v={v} />)}
          {filtered.length === 0 && (
            <p className="text-white/40 text-sm text-center py-10">No hay locales en esta zona.</p>
          )}
        </div>
      )}
    </AppShell>
  );
}
