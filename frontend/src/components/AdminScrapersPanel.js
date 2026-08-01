import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import api, { formatApiErrorDetail } from "@/lib/api";
import { Bot, Play, Loader2, Plus, Trash2, CheckCircle2, XCircle, RefreshCw, Globe, KeyRound, ShieldCheck, ShieldAlert } from "lucide-react";
import { toast } from "sonner";

const ADAPTER_LABELS = {
  fourvenues_api: "FourVenues API (universal · precios reales)",
  fourvenues_public_api: "API pública (/api/fourvenues)",
  nextjs_html: "HTML Next.js (extrae del home)",
};

/**
 * Admin panel to manage automatic event scrapers.
 * Each venue defines its FourVenues slug + adapter type. Runs auto every 30 min.
 */
export default function AdminScrapersPanel() {
  const qc = useQueryClient();
  const [adding, setAdding] = useState(false);
  const [newVenue, setNewVenue] = useState({
    name: "", city: "Palma de Mallorca", adapter_type: "fourvenues_api", url: "", slug: "",
  });
  const [tokenInput, setTokenInput] = useState("");
  const [editingToken, setEditingToken] = useState(false);

  const { data: venues = [], isLoading } = useQuery({
    queryKey: ["admin-scrapers"],
    queryFn: async () => (await api.get("/admin/scrapers")).data,
    staleTime: 20_000,
    refetchInterval: 60_000,
  });

  const { data: tokenStatus } = useQuery({
    queryKey: ["admin-fv-token"],
    queryFn: async () => (await api.get("/admin/scrapers/fourvenues-token")).data,
    staleTime: 30_000,
  });

  const inv = () => qc.invalidateQueries({ queryKey: ["admin-scrapers"] });

  const saveToken = useMutation({
    mutationFn: async () => (await api.put("/admin/scrapers/fourvenues-token", { token: tokenInput.trim() })).data,
    onSuccess: (d) => {
      toast[d.valid === false ? "warning" : "success"](
        d.valid === false ? "Token guardado, pero no valida (revísalo)" : "Token guardado y validado"
      );
      setEditingToken(false);
      setTokenInput("");
      qc.invalidateQueries({ queryKey: ["admin-fv-token"] });
    },
    onError: (e) => toast.error(formatApiErrorDetail(e.response?.data?.detail) || "Error"),
  });

  const create = useMutation({
    mutationFn: async (payload) => (await api.post("/admin/scrapers", payload || newVenue)).data,
    onSuccess: () => {
      toast.success("Discoteca añadida");
      setAdding(false);
      setNewVenue({ name: "", city: "Palma de Mallorca", adapter_type: "fourvenues_api", url: "", slug: "" });
      inv();
    },
    onError: (e) => toast.error(formatApiErrorDetail(e.response?.data?.detail) || "Error"),
  });

  const remove = useMutation({
    mutationFn: async (id) => (await api.delete(`/admin/scrapers/${id}`)).data,
    onSuccess: () => { toast.success("Eliminado"); inv(); },
  });

  const runOne = useMutation({
    mutationFn: async (id) => (await api.post(`/admin/scrapers/${id}/run`)).data,
    onSuccess: (d) => {
      if (d.ok) toast.success(`${d.venue_name}: ${d.created} nuevos, ${d.updated} actualizados`);
      else toast.error(`Falló: ${d.error || "error"}`);
      inv();
    },
  });

  const runAll = useMutation({
    mutationFn: async () => (await api.post("/admin/scrapers/run-all")).data,
    onSuccess: (d) => {
      toast.success(`${d.venues_run} discotecas · ${d.total_new} nuevos · ${d.total_updated} actualizados`);
      inv();
      qc.invalidateQueries({ queryKey: ["events"] });
      qc.invalidateQueries({ queryKey: ["carousels"] });
    },
    onError: () => toast.error("Falló ejecución global"),
  });

  const fmtRel = (iso) => {
    if (!iso) return "nunca";
    const d = new Date(iso);
    const diff = Date.now() - d.getTime();
    const min = Math.floor(diff / 60000);
    if (min < 1) return "hace unos segundos";
    if (min < 60) return `hace ${min} min`;
    const h = Math.floor(min / 60);
    if (h < 24) return `hace ${h}h`;
    return d.toLocaleDateString("es-ES");
  };

  const toggleActive = useMutation({
    mutationFn: async (v) => (await api.put(`/admin/scrapers/${v.id}`, { ...v, active: !v.active })).data,
    onSuccess: () => inv(),
  });

  const isFv = newVenue.adapter_type === "fourvenues_api";

  return (
    <div className="px-4 mt-6" data-testid="admin-scrapers-panel">
      <div className="flex items-center gap-2 mb-2">
        <Bot className="w-4 h-4 text-emerald-300" />
        <h2 className="font-display text-base font-bold text-white flex-1">
          Scraper de discotecas
        </h2>
        <button
          onClick={() => runAll.mutate()}
          disabled={runAll.isPending}
          className="text-xs font-bold text-black bg-emerald-300 rounded-full px-3 py-1.5 flex items-center gap-1 active:scale-95 disabled:opacity-50"
          data-testid="scrapers-run-all"
        >
          {runAll.isPending ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <RefreshCw className="w-3.5 h-3.5" />}
          Actualizar todos
        </button>
      </div>
      <p className="text-white/40 text-[11px] mb-3 leading-snug">
        Cada 30 min se sincroniza con FourVenues. Detecta fiestas nuevas y cambios de entradas:
        a la venta, pocas entradas, agotado, y subidas/bajadas de precio; envía push automáticas.
      </p>

      {/* FourVenues guest token */}
      <div className="rounded-2xl border border-white/10 bg-white/[0.04] p-3 mb-3" data-testid="fv-token-box">
        <div className="flex items-center gap-2">
          <KeyRound className="w-4 h-4 text-amber-300" />
          <span className="text-sm font-bold text-white flex-1">Token FourVenues</span>
          {tokenStatus?.valid === true && (
            <span className="text-[10px] flex items-center gap-1 text-emerald-300"><ShieldCheck className="w-3.5 h-3.5" /> válido</span>
          )}
          {tokenStatus?.valid === false && (
            <span className="text-[10px] flex items-center gap-1 text-rose-300"><ShieldAlert className="w-3.5 h-3.5" /> caducado</span>
          )}
          {tokenStatus && tokenStatus.valid == null && tokenStatus.configured && (
            <span className="text-[10px] text-white/40">sin verificar</span>
          )}
        </div>
        <p className="text-white/40 text-[10px] mt-1">
          {tokenStatus?.configured ? `Configurado: ${tokenStatus.masked}` : "No configurado"} · necesario para leer FourVenues.
        </p>
        {!editingToken ? (
          <button
            onClick={() => setEditingToken(true)}
            className="mt-2 text-[11px] font-bold text-amber-300 underline"
          >
            {tokenStatus?.configured ? "Actualizar token" : "Añadir token"}
          </button>
        ) : (
          <div className="mt-2 flex flex-col gap-2">
            <textarea
              placeholder="Pega aquí el guest-token JWT (eyJ...)"
              value={tokenInput}
              onChange={(e) => setTokenInput(e.target.value)}
              rows={3}
              className="bg-white/5 border border-white/10 rounded-lg px-3 py-2 text-white text-[11px] placeholder:text-white/40 break-all"
            />
            <div className="flex gap-2">
              <button
                onClick={() => saveToken.mutate()}
                disabled={!tokenInput.trim() || saveToken.isPending}
                className="flex-1 h-9 rounded-lg bg-amber-300 text-black font-bold text-xs active:scale-95 disabled:opacity-50"
              >
                {saveToken.isPending ? "Guardando..." : "Guardar y validar"}
              </button>
              <button
                onClick={() => { setEditingToken(false); setTokenInput(""); }}
                className="px-4 h-9 rounded-lg bg-white/10 text-white text-xs"
              >
                Cancelar
              </button>
            </div>
          </div>
        )}
      </div>

      {isLoading && (
        <div className="py-8 flex justify-center"><Loader2 className="w-5 h-5 animate-spin text-white/50" /></div>
      )}

      <div className="flex flex-col gap-2">
        {venues.map((v) => {
          const isRunning = runOne.isPending && runOne.variables === v.id;
          return (
            <div
              key={v.id}
              className={`rounded-2xl border p-3 ${
                v.last_run_ok === false
                  ? "border-rose-400/30 bg-rose-400/5"
                  : v.active
                  ? "border-white/10 bg-white/[0.04]"
                  : "border-white/10 bg-white/[0.02] opacity-60"
              }`}
              data-testid={`scraper-venue-${v.id}`}
            >
              <div className="flex items-start gap-3">
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-1.5 flex-wrap">
                    <p className="font-bold text-sm text-white truncate">{v.name}</p>
                    {v.last_run_ok === true && <CheckCircle2 className="w-3.5 h-3.5 text-emerald-400" />}
                    {v.last_run_ok === false && <XCircle className="w-3.5 h-3.5 text-rose-400" />}
                    {!v.active && <span className="text-[9px] px-1.5 py-0.5 rounded bg-white/10 text-white/50 uppercase">Off</span>}
                  </div>
                  <p className="text-white/40 text-[11px] truncate flex items-center gap-1">
                    <Globe className="w-3 h-3" /> {v.slug ? `slug: ${v.slug}` : v.url}
                  </p>
                  <p className="text-white/40 text-[10px] mt-0.5">
                    {ADAPTER_LABELS[v.adapter_type] || v.adapter_type}
                  </p>
                  <div className="flex flex-wrap gap-2 mt-1.5 text-[10px] text-white/60">
                    <span>{v.last_run_events || 0} eventos</span>
                    <span className="text-emerald-300">+{v.last_run_new || 0} nuevos</span>
                    <span className="text-blue-300">~{v.last_run_updated || 0} actualiz.</span>
                    <span>· {fmtRel(v.last_run_at)}</span>
                  </div>
                  {v.last_run_error && (
                    <p className="text-rose-300/80 text-[10px] mt-1 truncate">⚠ {v.last_run_error}</p>
                  )}
                </div>
              </div>
              <div className="mt-2 grid grid-cols-3 gap-1.5">
                <button
                  onClick={() => runOne.mutate(v.id)}
                  disabled={isRunning}
                  className="text-[10px] font-bold text-black bg-qv-secondary rounded-lg py-2 flex items-center justify-center gap-1 active:scale-95 disabled:opacity-50"
                  data-testid={`scraper-run-${v.id}`}
                >
                  {isRunning ? <Loader2 className="w-3 h-3 animate-spin" /> : <Play className="w-3 h-3" />}
                  Ejecutar
                </button>
                <button
                  onClick={() => toggleActive.mutate(v)}
                  className="text-[10px] font-bold text-white bg-white/10 rounded-lg py-2 active:scale-95"
                >
                  {v.active ? "Pausar" : "Activar"}
                </button>
                <button
                  onClick={() => { if (window.confirm(`¿Eliminar ${v.name}?`)) remove.mutate(v.id); }}
                  className="text-[10px] font-bold text-white/70 bg-white/5 border border-white/10 rounded-lg py-2 flex items-center justify-center gap-1 active:scale-95"
                >
                  <Trash2 className="w-3 h-3" /> Borrar
                </button>
              </div>
            </div>
          );
        })}
      </div>

      {!adding ? (
        <button
          onClick={() => setAdding(true)}
          className="mt-3 w-full h-11 rounded-2xl border border-dashed border-white/20 text-white/60 text-sm font-bold flex items-center justify-center gap-1.5 active:scale-95 hover:text-white hover:border-white/40"
          data-testid="scrapers-add-btn"
        >
          <Plus className="w-4 h-4" /> Añadir discoteca
        </button>
      ) : (
        <div className="mt-3 rounded-2xl border border-white/10 bg-white/[0.04] p-3 flex flex-col gap-2">
          <input
            placeholder="Nombre (ej. Bruja Mallorca)"
            value={newVenue.name}
            onChange={(e) => setNewVenue({ ...newVenue, name: e.target.value })}
            className="h-10 bg-white/5 border border-white/10 rounded-lg px-3 text-white text-sm placeholder:text-white/40"
          />
          <select
            value={newVenue.adapter_type}
            onChange={(e) => setNewVenue({ ...newVenue, adapter_type: e.target.value })}
            className="h-10 bg-white/5 border border-white/10 rounded-lg px-3 text-white text-sm"
          >
            <option value="fourvenues_api" className="bg-black">FourVenues API (universal, recomendado)</option>
            <option value="nextjs_html" className="bg-black">HTML Next.js (webs propias)</option>
            <option value="fourvenues_public_api" className="bg-black">API pública /api/fourvenues (legacy)</option>
          </select>
          {isFv ? (
            <input
              placeholder="Slug FourVenues (ej. amok, lunita, over-club)"
              value={newVenue.slug}
              onChange={(e) => setNewVenue({ ...newVenue, slug: e.target.value.trim() })}
              className="h-10 bg-white/5 border border-white/10 rounded-lg px-3 text-white text-sm placeholder:text-white/40"
            />
          ) : (
            <input
              placeholder="URL (ej. https://brujamallorca.com)"
              value={newVenue.url}
              onChange={(e) => setNewVenue({ ...newVenue, url: e.target.value })}
              className="h-10 bg-white/5 border border-white/10 rounded-lg px-3 text-white text-sm placeholder:text-white/40"
            />
          )}
          {isFv && (
            <p className="text-white/40 text-[10px] -mt-1 leading-snug">
              El slug es lo que va tras <span className="text-white/60">site.fourvenues.com/es/</span> en la web del club.
            </p>
          )}
          <input
            placeholder="Ciudad"
            value={newVenue.city}
            onChange={(e) => setNewVenue({ ...newVenue, city: e.target.value })}
            className="h-10 bg-white/5 border border-white/10 rounded-lg px-3 text-white text-sm placeholder:text-white/40"
          />
          <div className="flex gap-2">
            <button
              onClick={() => {
                const payload = { ...newVenue };
                if (isFv && payload.slug && !payload.url) {
                  payload.url = `https://site.fourvenues.com/es/${payload.slug}`;
                }
                create.mutate(payload);
              }}
              disabled={!newVenue.name || (isFv ? !newVenue.slug : !newVenue.url) || create.isPending}
              className="flex-1 h-10 rounded-lg bg-qv-primary text-black font-bold text-sm active:scale-95 disabled:opacity-50"
            >
              {create.isPending ? "Guardando..." : "Añadir"}
            </button>
            <button
              onClick={() => setAdding(false)}
              className="px-4 h-10 rounded-lg bg-white/10 text-white text-sm"
            >
              Cancelar
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
