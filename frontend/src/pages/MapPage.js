import { useMemo } from "react";
import { useQuery } from "@tanstack/react-query";
import { useNavigate } from "react-router-dom";
import { MapContainer, TileLayer, Marker, Popup } from "react-leaflet";
import L from "leaflet";
import "leaflet/dist/leaflet.css";
import api from "@/lib/api";
import { AppShell } from "@/components/AppShell";
import { Loader2 } from "lucide-react";

const TYPE_COLOR = {
  discoteca: "#e879f9",
  pub: "#34d399",
  beach_club: "#22d3ee",
  promotor: "#fbbf24",
};
const TYPE_LABEL = { discoteca: "Discotecas", pub: "Pubs", beach_club: "Beach clubs", promotor: "Promotores" };

function makeIcon(color, count) {
  const badge = count > 0
    ? `<span style="position:absolute;top:-6px;right:-6px;background:#ff0055;color:#fff;font-size:9px;font-weight:800;border-radius:9px;padding:0 4px;line-height:14px;border:1.5px solid #12040a">${count}</span>`
    : "";
  return L.divIcon({
    className: "qv-pin",
    html: `<div style="position:relative;width:22px;height:22px">
      <div style="width:22px;height:22px;border-radius:50% 50% 50% 0;transform:rotate(-45deg);background:${color};border:2px solid #12040a;box-shadow:0 2px 6px rgba(0,0,0,.5)"></div>
      ${badge}
    </div>`,
    iconSize: [22, 22],
    iconAnchor: [11, 22],
    popupAnchor: [0, -22],
  });
}

export default function MapPage() {
  const navigate = useNavigate();
  const { data: venues = [], isLoading } = useQuery({
    queryKey: ["venues"],
    queryFn: async () => (await api.get("/venues")).data,
    staleTime: 60_000,
  });

  const pins = useMemo(() => venues.filter((v) => v.lat != null && v.lng != null), [venues]);

  return (
    <AppShell>
      <header className="px-5 pt-8 pb-2">
        <p className="text-xs tracking-[0.25em] uppercase text-qv-secondary font-bold">Mallorca</p>
        <h1 className="font-display text-4xl font-black tracking-tighter mt-1">
          Mapa<span className="text-qv-primary">.</span>
        </h1>
        <p className="text-white/50 text-sm mt-1">Discotecas y pubs de la isla en el mapa.</p>
      </header>

      {/* Legend */}
      <div className="px-4 pb-2 flex flex-wrap gap-3">
        {Object.entries(TYPE_LABEL).map(([k, label]) => (
          <span key={k} className="flex items-center gap-1.5 text-[11px] text-white/60">
            <span className="w-3 h-3 rounded-full" style={{ background: TYPE_COLOR[k] }} /> {label}
          </span>
        ))}
      </div>

      <div className="px-3">
        {isLoading ? (
          <div className="h-[62vh] flex items-center justify-center"><Loader2 className="w-6 h-6 animate-spin text-white/50" /></div>
        ) : (
          <div className="rounded-2xl overflow-hidden border border-white/10" style={{ height: "62vh" }} data-testid="mallorca-map">
            <MapContainer center={[39.62, 2.95]} zoom={9} scrollWheelZoom={true} style={{ height: "100%", width: "100%", background: "#0b0710" }}>
              <TileLayer
                attribution='&copy; OpenStreetMap'
                url="https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png"
              />
              {pins.map((v) => (
                <Marker key={v.id} position={[v.lat, v.lng]} icon={makeIcon(TYPE_COLOR[v.type] || "#e879f9", v.upcoming_events || 0)}>
                  <Popup>
                    <div style={{ minWidth: 160 }}>
                      <div style={{ fontWeight: 800, fontSize: 14 }}>{v.name}</div>
                      <div style={{ color: "#666", fontSize: 12 }}>{v.zone} · {v.type}</div>
                      {v.free_entry && <div style={{ color: "#059669", fontSize: 11, fontWeight: 700 }}>Entrada libre</div>}
                      <div style={{ fontSize: 12, marginTop: 4 }}>
                        {v.upcoming_events > 0 ? `🎉 ${v.upcoming_events} fiestas próximas` : "Sin fiestas anunciadas"}
                      </div>
                      <button
                        onClick={() => navigate("/locales")}
                        style={{ marginTop: 6, background: "#ff0055", color: "#fff", border: "none", borderRadius: 8, padding: "5px 10px", fontWeight: 700, fontSize: 12, cursor: "pointer" }}
                      >
                        Ver ficha
                      </button>
                    </div>
                  </Popup>
                </Marker>
              ))}
            </MapContainer>
          </div>
        )}
        <p className="text-white/30 text-[10px] text-center mt-2 pb-2">Mapas © OpenStreetMap · CARTO</p>
      </div>
    </AppShell>
  );
}
