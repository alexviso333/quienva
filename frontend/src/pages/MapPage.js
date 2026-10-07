import { useMemo, useState, useEffect } from "react";
import { useQuery } from "@tanstack/react-query";
import { useNavigate } from "react-router-dom";
import { MapContainer, TileLayer, Marker, Popup, Circle, useMap } from "react-leaflet";
import L from "leaflet";
import "leaflet/dist/leaflet.css";
import api from "@/lib/api";
import { useAuth } from "@/context/AuthContext";
import { AppShell } from "@/components/AppShell";
import { Loader2, LocateFixed } from "lucide-react";
import { toast } from "@/lib/notify";
import { useTranslation } from "react-i18next";

const TYPE_COLOR = {
  discoteca: "#e879f9",
  pub: "#34d399",
  beach_club: "#22d3ee",
  promotor: "#fbbf24",
};
const TYPE_KEYS = ["discoteca", "pub", "beach_club", "promotor"];

// Sensible default map centers per city (fallback when we can't geolocate).
const CITY_CENTER = {
  "Palma de Mallorca": [39.62, 2.95],
  Ibiza: [38.95, 1.43],
  Madrid: [40.4168, -3.7038],
  Barcelona: [41.3874, 2.1686],
  Marbella: [36.5099, -4.8858],
};

const DISTANCE_KMS = [0, 2, 5, 10, 20];

// Haversine distance in km between two [lat, lng] points.
function distanceKm(a, b) {
  if (!a || !b) return Infinity;
  const R = 6371;
  const dLat = ((b[0] - a[0]) * Math.PI) / 180;
  const dLng = ((b[1] - a[1]) * Math.PI) / 180;
  const lat1 = (a[0] * Math.PI) / 180;
  const lat2 = (b[0] * Math.PI) / 180;
  const h =
    Math.sin(dLat / 2) ** 2 + Math.sin(dLng / 2) ** 2 * Math.cos(lat1) * Math.cos(lat2);
  return 2 * R * Math.asin(Math.sqrt(h));
}

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

// Pulsing blue "you are here" marker.
const meIcon = L.divIcon({
  className: "qv-me-pin",
  html: `<div style="position:relative;width:20px;height:20px">
    <div style="position:absolute;inset:0;border-radius:50%;background:rgba(56,132,255,.35);animation:qvpulse 1.8s ease-out infinite"></div>
    <div style="position:absolute;top:4px;left:4px;width:12px;height:12px;border-radius:50%;background:#3884ff;border:2px solid #fff;box-shadow:0 0 6px rgba(56,132,255,.9)"></div>
  </div>
  <style>@keyframes qvpulse{0%{transform:scale(.6);opacity:.9}100%{transform:scale(2.4);opacity:0}}</style>`,
  iconSize: [20, 20],
  iconAnchor: [10, 10],
});

// Imperatively recenter the map when the target changes (e.g. after geolocation).
function Recenter({ center, zoom }) {
  const map = useMap();
  useEffect(() => {
    if (center) map.setView(center, zoom ?? map.getZoom(), { animate: true });
  }, [center, zoom, map]);
  return null;
}

export default function MapPage() {
  const navigate = useNavigate();
  const { user } = useAuth();
  const { t } = useTranslation();
  const cityLabel = user?.city || t("map.your_city");

  // City map centre comes from the backend (/api/cities → lat/lng) so a city
  // added from the admin centres correctly WITHOUT an app update. Falls back to
  // the built-in table, then Palma.
  const { data: citiesData } = useQuery({
    queryKey: ["cities"],
    queryFn: async () => (await api.get("/cities")).data,
    staleTime: 60 * 60_000,
  });
  const cityCenter = useMemo(() => {
    const c = (citiesData?.cities || []).find((x) => x.id === user?.city);
    if (c && typeof c.lat === "number" && typeof c.lng === "number") return [c.lat, c.lng];
    return CITY_CENTER[user?.city] || CITY_CENTER["Palma de Mallorca"];
  }, [citiesData, user?.city]);

  const [myPos, setMyPos] = useState(null);     // [lat, lng] of the viewer
  const [geoState, setGeoState] = useState("idle"); // idle | locating | ok | denied
  const [radius, setRadius] = useState(0);       // km, 0 = show all

  const { data: venues = [], isLoading } = useQuery({
    queryKey: ["venues", user?.city],
    queryFn: async () => (await api.get("/venues")).data,
    staleTime: 60_000,
  });

  const locate = () => {
    if (!("geolocation" in navigator)) {
      toast.error(t("map.geo_unsupported"));
      return;
    }
    setGeoState("locating");
    navigator.geolocation.getCurrentPosition(
      (p) => {
        setMyPos([p.coords.latitude, p.coords.longitude]);
        setGeoState("ok");
      },
      () => {
        setGeoState("denied");
        toast.error(t("map.geo_denied"));
      },
      { enableHighAccuracy: true, timeout: 10000, maximumAge: 60000 },
    );
  };

  // Ask for location once on mount (silent — the browser shows its own prompt).
  useEffect(() => {
    if (geoState === "idle") locate();
  }, []); // run once on mount

  const allPins = useMemo(
    () => venues.filter((v) => v.lat != null && v.lng != null),
    [venues],
  );

  // Attach distance to each pin (when we know where the user is) and filter.
  const pins = useMemo(() => {
    let list = allPins;
    if (myPos) {
      list = list.map((v) => ({ ...v, _dist: distanceKm(myPos, [v.lat, v.lng]) }));
      if (radius > 0) list = list.filter((v) => v._dist <= radius);
      list = [...list].sort((a, b) => (a._dist ?? 0) - (b._dist ?? 0));
    }
    return list;
  }, [allPins, myPos, radius]);

  const center = myPos || cityCenter;
  const zoom = myPos ? (radius && radius <= 5 ? 13 : 11) : 9;

  return (
    <AppShell>
      <header className="px-5 pt-8 pb-2">
        <p className="text-xs tracking-[0.25em] uppercase text-qv-secondary font-bold">{cityLabel}</p>
        <h1 className="font-display text-4xl font-black tracking-tighter mt-1">
          {t("map.title")}<span className="text-qv-primary">.</span>
        </h1>
        <p className="text-white/50 text-sm mt-1">{t("map.subtitle")}</p>
      </header>

      {/* Distance filter (only meaningful once we have the viewer's position) */}
      <div className="px-4 pb-1 flex items-center gap-2 overflow-x-auto no-scrollbar">
        {DISTANCE_KMS.map((km) => (
          <button
            key={km}
            data-testid={`map-radius-${km}`}
            onClick={() => {
              if (!myPos && km > 0) { locate(); }
              setRadius(km);
            }}
            className={`shrink-0 px-3 h-8 rounded-full text-xs font-bold border transition-colors ${
              radius === km
                ? "bg-qv-primary text-white border-qv-primary"
                : "bg-white/5 text-white/70 border-white/15"
            }`}
          >
            {km === 0 ? t("map.all") : `${km} km`}
          </button>
        ))}
        <button
          data-testid="map-locate-btn"
          onClick={locate}
          className="shrink-0 ml-auto px-3 h-8 rounded-full text-xs font-bold border border-qv-secondary/40 bg-qv-secondary/15 text-qv-secondary flex items-center gap-1.5"
        >
          {geoState === "locating" ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <LocateFixed className="w-3.5 h-3.5" />}
          {t("map.my_location")}
        </button>
      </div>

      {/* Legend */}
      <div className="px-4 py-2 flex flex-wrap gap-3">
        {TYPE_KEYS.map((k) => (
          <span key={k} className="flex items-center gap-1.5 text-[11px] text-white/60">
            <span className="w-3 h-3 rounded-full" style={{ background: TYPE_COLOR[k] }} /> {t(`map.type.${k}`)}
          </span>
        ))}
        {myPos && radius > 0 && (
          <span className="text-[11px] text-white/50 ml-auto">{t("map.within_radius", { count: pins.length, km: radius })}</span>
        )}
      </div>

      <div className="px-3">
        {isLoading ? (
          <div className="h-[58vh] flex items-center justify-center"><Loader2 className="w-6 h-6 animate-spin text-white/50" /></div>
        ) : (
          <div className="rounded-2xl overflow-hidden border border-white/10" style={{ height: "58vh" }} data-testid="mallorca-map">
            <MapContainer center={center} zoom={zoom} scrollWheelZoom={true} style={{ height: "100%", width: "100%", background: "#0b0710" }}>
              <Recenter center={center} zoom={zoom} />
              <TileLayer
                attribution='&copy; OpenStreetMap'
                url="https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png"
              />
              {myPos && (
                <>
                  <Marker position={myPos} icon={meIcon}>
                    <Popup><div style={{ fontWeight: 800 }}>{t("map.you_here")}</div></Popup>
                  </Marker>
                  {radius > 0 && (
                    <Circle
                      center={myPos}
                      radius={radius * 1000}
                      pathOptions={{ color: "#3884ff", fillColor: "#3884ff", fillOpacity: 0.06, weight: 1 }}
                    />
                  )}
                </>
              )}
              {pins.map((v) => (
                <Marker key={v.id} position={[v.lat, v.lng]} icon={makeIcon(TYPE_COLOR[v.type] || "#e879f9", v.upcoming_events || 0)}>
                  <Popup>
                    <div style={{ minWidth: 160 }}>
                      <div style={{ fontWeight: 800, fontSize: 14 }}>{v.name}</div>
                      <div style={{ color: "#666", fontSize: 12 }}>{v.zone} · {v.type}</div>
                      {v._dist != null && Number.isFinite(v._dist) && (
                        <div style={{ color: "#3884ff", fontSize: 12, fontWeight: 700 }}>
                          {t("map.dist_from_you", { dist: v._dist < 1 ? `${Math.round(v._dist * 1000)} m` : `${v._dist.toFixed(1)} km` })}
                        </div>
                      )}
                      {v.free_entry && <div style={{ color: "#059669", fontSize: 11, fontWeight: 700 }}>{t("map.free_entry")}</div>}
                      <div style={{ fontSize: 12, marginTop: 4 }}>
                        {v.upcoming_events > 0 ? t(v.upcoming_events === 1 ? "map.upcoming_one" : "map.upcoming_other", { count: v.upcoming_events }) : t("map.no_parties")}
                      </div>
                      <button
                        onClick={() => navigate("/locales")}
                        style={{ marginTop: 6, background: "#ff0055", color: "#fff", border: "none", borderRadius: 8, padding: "5px 10px", fontWeight: 700, fontSize: 12, cursor: "pointer" }}
                      >
                        {t("map.view_venue")}
                      </button>
                    </div>
                  </Popup>
                </Marker>
              ))}
            </MapContainer>
          </div>
        )}
        {geoState === "denied" && (
          <p className="text-white/40 text-[11px] text-center mt-2">
            {t("map.geo_hint")}
          </p>
        )}
        <p className="text-white/30 text-[10px] text-center mt-2 pb-2">{t("map.attribution")}</p>
      </div>
    </AppShell>
  );
}
