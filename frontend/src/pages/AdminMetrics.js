import { useState, useMemo } from "react";
import { useNavigate } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import api, { API } from "@/lib/api";
import { ArrowLeft, Loader2, Eye, PartyPopper, Star, MousePointerClick, Ticket, Users, UserPlus, Clock, Globe, BarChart3, Download, TrendingUp, Zap, LineChart, Sparkles, User, ShieldAlert } from "lucide-react";

const WINDOWS = [7, 14, 30, 60, 90];

function Big({ icon: Icon, label, value, hint, color = "text-white" }) {
  return (
    <div className="rounded-2xl bg-white/[0.03] border border-white/10 p-3.5">
      <div className="flex items-center gap-2 text-[10px] uppercase tracking-wider text-white/50 font-bold">
        <Icon className={`w-3.5 h-3.5 ${color}`} /> {label}
      </div>
      <p className="font-display text-2xl font-black text-white mt-1 leading-none tabular-nums">{value}</p>
      {hint ? <p className="text-[10px] text-white/40 mt-1">{hint}</p> : null}
    </div>
  );
}

function Section({ title, children, icon: Icon }) {
  return (
    <div className="mt-5">
      <h2 className="flex items-center gap-2 text-sm font-black text-white mb-2 uppercase tracking-wider">
        {Icon ? <Icon className="w-4 h-4 text-qv-secondary" /> : null}
        {title}
      </h2>
      {children}
    </div>
  );
}

function Table({ columns, rows, testId }) {
  if (!rows || rows.length === 0) {
    return <p className="text-white/40 text-sm py-4 text-center">Sin datos todavía.</p>;
  }
  return (
    <div className="rounded-2xl overflow-x-auto bg-white/[0.03] border border-white/10" data-testid={testId}>
      <table className="w-full text-left text-sm">
        <thead>
          <tr className="text-[10px] uppercase tracking-wider text-white/40 border-b border-white/10">
            {columns.map((c, i) => (
              <th key={i} className={`px-3 py-2 font-bold ${c.right ? "text-right" : ""}`}>{c.label}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((r, i) => (
            <tr key={i} className="border-b border-white/5 last:border-0">
              {columns.map((c, j) => (
                <td key={j} className={`px-3 py-2 ${c.right ? "text-right tabular-nums font-semibold text-white" : "text-white/80"}`}>
                  {c.render ? c.render(r) : r[c.key]}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function Bar({ value, max, color = "bg-qv-primary" }) {
  const pct = max > 0 ? Math.min(100, Math.round((value / max) * 100)) : 0;
  return (
    <div className="h-1.5 rounded-full bg-white/10 overflow-hidden">
      <div className={`h-full ${color}`} style={{ width: `${pct}%` }} />
    </div>
  );
}

export default function AdminMetrics() {
  const navigate = useNavigate();
  const [days, setDays] = useState(30);
  const [includeAdmin, setIncludeAdmin] = useState(false);
  const [testing, setTesting] = useState(null);
  const [testResult, setTestResult] = useState(null);

  const { data, isLoading, refetch, isFetching } = useQuery({
    queryKey: ["admin-metrics", days, includeAdmin],
    queryFn: async () => (await api.get(
      `/admin/metrics?days=${days}&include_admin=${includeAdmin ? 1 : 0}`
    )).data,
    staleTime: 30000,
  });

  // Diagnostico Live Activity / isla dinamica (muestra por que el Momento
  // no sale aunque los planes si: tokens por kind, APNs config, etc.)
  const { data: laDiag, refetch: refetchLa } = useQuery({
    queryKey: ["admin-live-activities-diag"],
    queryFn: async () => (await api.get("/admin/live-activities")).data,
    staleTime: 15000,
  });

  const runTest = async (kind) => {
    setTesting(kind);
    setTestResult(null);
    try {
      const url = kind === "moment"
        ? "/admin/moment/test"
        : "/admin/weekly-report/trigger";
      const { data: d } = await api.post(url);
      setTestResult({ kind, ok: true, data: d });
    } catch (e) {
      setTestResult({ kind, ok: false, error: e?.message || "error" });
    } finally {
      setTesting(null);
    }
  };

  const totals = data?.totals;
  const conversion = useMemo(() => {
    if (!totals) return null;
    const v = (totals.anon_visitors || 0) + (totals.new_users_window || 0);
    if (v === 0) return null;
    return Math.round(((totals.new_users_window || 0) / v) * 1000) / 10;
  }, [totals]);

  const dailyChart = useMemo(() => {
    if (!data) return null;
    const map = {};
    const opens = data.daily_opens || {};
    const sign = data.daily_signups || {};
    Object.keys(opens).forEach((d) => { map[d] = { date: d, opens: opens[d], signups: sign[d] || 0 }; });
    Object.keys(sign).forEach((d) => {
      if (!map[d]) map[d] = { date: d, opens: 0, signups: sign[d] };
    });
    const rows = Object.values(map).sort((a, b) => a.date.localeCompare(b.date));
    const maxOpens = Math.max(1, ...rows.map((r) => r.opens));
    const maxSign = Math.max(1, ...rows.map((r) => r.signups));
    return { rows, maxOpens, maxSign };
  }, [data]);

  const activityRows = useMemo(() => {
    const ac = data?.activity_counts || {};
    const arr = Object.entries(ac).map(([k, v]) => ({ event: k, n: v }));
    arr.sort((a, b) => b.n - a.n);
    return arr;
  }, [data]);
  const activityMax = activityRows.length ? activityRows[0].n : 1;

  const downloadCsv = () => {
    try {
      const base = API || "";
      const token = localStorage.getItem("qv_token") || "";
      // Fetch con auth header y descarga como blob.
      fetch(`${base}/admin/metrics/export.csv?days=${days}&include_admin=${includeAdmin ? 1 : 0}`, {
        credentials: "include",
        headers: token ? { Authorization: `Bearer ${token}` } : {},
      })
        .then((r) => r.blob())
        .then((blob) => {
          const url = URL.createObjectURL(blob);
          const a = document.createElement("a");
          a.href = url;
          a.download = `quienva-metrics-${days}d.csv`;
          document.body.appendChild(a);
          a.click();
          a.remove();
          URL.revokeObjectURL(url);
        })
        .catch(() => {});
    } catch (e) { /* ignore */ }
  };

  return (
    <div className="min-h-screen qv-app-bg">
      <div className="max-w-md mx-auto min-h-screen pb-10">
        <header className="px-5 pt-8 pb-4 flex items-center gap-3">
          <button data-testid="metrics-back" onClick={() => navigate("/admin")} className="w-10 h-10 rounded-full bg-white/5 border border-white/10 flex items-center justify-center active:scale-95">
            <ArrowLeft className="w-5 h-5" />
          </button>
          <div className="flex-1 min-w-0">
            <h1 className="font-display text-2xl font-black tracking-tighter">Métricas</h1>
            <p className="text-white/40 text-xs">Panel completo · solo admin</p>
          </div>
          <button
            onClick={downloadCsv}
            data-testid="metrics-export-csv"
            className="h-10 px-3 rounded-xl bg-qv-primary/15 border border-qv-primary/40 text-qv-primary text-xs font-bold flex items-center gap-1.5 active:scale-95"
          >
            <Download className="w-3.5 h-3.5" /> CSV
          </button>
        </header>

        {/* Momento de prueba — admin only */}
        <div className="px-5 mt-2 space-y-2">
          <div className="flex gap-2">
            <button
              onClick={async () => {
                try {
                  const r = await api.post("/admin/moment/test");
                  const d = r?.data || {};
                  const diag = [
                    `prompt_id: ${d.prompt_id || "?"}`,
                    `expira: ${d.on_time_deadline ? new Date(d.on_time_deadline).toLocaleTimeString() : "?"} (deadline on-time) · ${d.expires_at ? new Date(d.expires_at).toLocaleTimeString() : "?"} (expiración)`,
                    `APNs configurado: ${d.apns_configured ? "✅ SÍ" : "❌ NO"}`,
                    `Push to-start tokens iOS: ${d.live_activity_tokens_admin ?? 0}`,
                    `Push notifs enviadas: ${d.notified ?? 0}`,
                  ];
                  const problems = [];
                  if (!d.apns_configured) problems.push("❌ APNs no está configurado en el backend (faltan certificados). Sin esto no habrá push ni Dynamic Island.");
                  if ((d.live_activity_tokens_admin ?? 0) === 0) problems.push("❌ Tu iPhone no ha subido ningún push-to-start token con kind='moment'. La app Swift debe implementar MomentActivityAttributes + Activity.pushToStartTokenUpdates y llamar POST /api/live-activity/start-token.");
                  alert(
                    "✅ Momento REAL disparado:\n\n" + diag.join("\n") +
                    (problems.length ? "\n\n⚠️ Por qué NO ves Dynamic Island:\n" + problems.join("\n") : "") +
                    "\n\nAhora abre la app en tu iPhone (TestFlight) para ver el modal in-app."
                  );
                  navigate("/feed");
                } catch (e) {
                  alert("❌ Error disparando el Momento: " + (e?.response?.data?.detail || e.message));
                }
              }}
              data-testid="metrics-preview-moment"
              className="flex-[2] h-12 rounded-2xl bg-gradient-to-r from-pink-500 via-orange-400 to-yellow-300 text-black font-display font-black text-sm flex items-center justify-center gap-2 active:scale-[0.98] shadow-[0_10px_30px_-10px_rgba(236,72,153,0.6)]"
            >
              <Sparkles className="w-4 h-4" strokeWidth={2.5} />
              Disparar Momento REAL
            </button>
            <button
              onClick={async () => {
                if (!confirm("¿Parar el Momento de prueba ahora mismo?")) return;
                try {
                  const r = await api.post("/admin/moment/__test_moment_admin/stop");
                  const d = r?.data || {};
                  alert(
                    "🛑 Momento detenido:\n\n" +
                    `prompt borrado: ${d.prompt_deleted}\n` +
                    `Live Activities terminadas (end push): ${d.live_activities_ended}\n` +
                    `Marcadas como ended localmente: ${d.live_activities_marked_locally}\n` +
                    `Capturas limpiadas (admin): ${d.captures_deleted_for_admin}\n\n` +
                    "Puedes volver a lanzar el test cuando quieras."
                  );
                } catch (e) {
                  alert("❌ Error parando el Momento: " + (e?.response?.data?.detail || e.message));
                }
              }}
              data-testid="metrics-stop-moment"
              className="flex-1 h-12 rounded-2xl bg-white/10 border border-white/15 text-white font-display font-black text-xs flex items-center justify-center gap-1.5 active:scale-[0.98]"
              aria-label="Parar Momento de prueba"
            >
              🛑 Parar
            </button>
          </div>
          <p className="text-[10px] text-white/40 text-center">
            Flujo completo: push APNs + Live Activity + modal in-app. Test expira en 15 min; real = hasta que acaba la fiesta.
          </p>

          {/* Diagnostico Live Activity / Dynamic Island */}
          {laDiag ? (
            <div className="mt-2 rounded-2xl bg-white/[0.03] border border-white/10 p-3" data-testid="la-diagnose">
              <div className="flex items-center justify-between mb-2">
                <p className="text-[11px] font-bold text-white/80">Diagnóstico Live Activity</p>
                <button
                  onClick={() => refetchLa()}
                  className="text-[10px] text-qv-primary font-bold"
                  data-testid="la-diagnose-refresh"
                >
                  Actualizar
                </button>
              </div>
              <div className="grid grid-cols-2 gap-2 text-[11px]">
                <div className="flex flex-col">
                  <span className="text-white/40 text-[9px] uppercase">APNs</span>
                  <span className={`font-bold ${laDiag.apns_configured ? "text-emerald-400" : "text-red-400"}`}>
                    {laDiag.apns_configured ? "✅ ON" : "❌ OFF"}
                  </span>
                </div>
                <div className="flex flex-col">
                  <span className="text-white/40 text-[9px] uppercase">Entorno</span>
                  <span className="font-bold text-white/80">{laDiag.apns_environment || "?"}</span>
                </div>
                <div className="flex flex-col">
                  <span className="text-white/40 text-[9px] uppercase">Token Momento (tú)</span>
                  <span className={`font-bold ${laDiag.my_moment_token ? "text-emerald-400" : "text-red-400"}`}>
                    {laDiag.my_moment_token ? "✅ Registrado" : "❌ FALTA"}
                  </span>
                </div>
                <div className="flex flex-col">
                  <span className="text-white/40 text-[9px] uppercase">Token Plan (tú)</span>
                  <span className={`font-bold ${laDiag.my_plan_token ? "text-emerald-400" : "text-red-400"}`}>
                    {laDiag.my_plan_token ? "✅ Registrado" : "❌ FALTA"}
                  </span>
                </div>
                <div className="flex flex-col">
                  <span className="text-white/40 text-[9px] uppercase">Tokens moment (red)</span>
                  <span className="font-bold text-white/80 tabular-nums">
                    {laDiag.push_to_start_tokens_by_kind?.moment ?? 0}
                  </span>
                </div>
                <div className="flex flex-col">
                  <span className="text-white/40 text-[9px] uppercase">Tokens plan (red)</span>
                  <span className="font-bold text-white/80 tabular-nums">
                    {laDiag.push_to_start_tokens_by_kind?.plan_invite ?? 0}
                  </span>
                </div>
              </div>
              {Array.isArray(laDiag.diagnosis) && laDiag.diagnosis.length > 0 ? (
                <div className="mt-2 space-y-1">
                  {laDiag.diagnosis.map((m, i) => (
                    <p key={i} className="text-[10px] text-amber-200 leading-tight">{m}</p>
                  ))}
                </div>
              ) : null}
              <p className="text-[9px] text-white/30 mt-2">
                Topic: <span className="font-mono">{laDiag.liveactivity_topic}</span> · Live Activities totales: {laDiag.total} ({laDiag.activas} activas)
              </p>
            </div>
          ) : null}
        </div>

        {/* Ventana temporal */}
        <div className="px-5">
          <div className="flex items-center gap-1 p-1 rounded-2xl bg-white/5 border border-white/10" data-testid="metrics-window">
            {WINDOWS.map((w) => (
              <button
                key={w}
                onClick={() => setDays(w)}
                data-testid={`metrics-window-${w}`}
                className={`flex-1 py-2 rounded-xl text-xs font-bold ${days === w ? "bg-white text-black" : "text-white/60"}`}
              >
                {w}d
              </button>
            ))}
          </div>
        </div>

        {/* Toggle: incluir acciones de admins (yo). Default OFF — mis tests
            no contaminan las métricas reales. */}
        <div className="px-5 mt-2">
          <button
            type="button"
            onClick={() => setIncludeAdmin((v) => !v)}
            data-testid="metrics-include-admin"
            className={`w-full flex items-center justify-between gap-3 px-3.5 py-2.5 rounded-2xl border transition-colors ${
              includeAdmin
                ? "bg-amber-500/10 border-amber-500/40"
                : "bg-white/[0.03] border-white/10"
            }`}
            aria-pressed={includeAdmin}
          >
            <div className="flex items-center gap-2 min-w-0">
              <ShieldAlert className={`w-4 h-4 ${includeAdmin ? "text-amber-300" : "text-white/40"}`} />
              <div className="min-w-0 text-left">
                <p className={`text-xs font-bold ${includeAdmin ? "text-amber-200" : "text-white/80"}`}>
                  {includeAdmin ? "Incluyendo mis acciones (admins)" : "Excluyendo mis acciones (admins)"}
                </p>
                <p className="text-[10px] text-white/40 leading-tight">
                  {includeAdmin
                    ? "Los tests que haces contaminan estas cifras."
                    : "Default. Tus tests no afectan a las métricas."}
                </p>
              </div>
            </div>
            <span
              className={`relative w-10 h-6 rounded-full transition-colors shrink-0 ${
                includeAdmin ? "bg-amber-400" : "bg-white/15"
              }`}
            >
              <span
                className={`absolute top-0.5 w-5 h-5 rounded-full bg-white shadow-md transition-transform ${
                  includeAdmin ? "translate-x-4" : "translate-x-0.5"
                }`}
              />
            </span>
          </button>
        </div>

        {isLoading && !data ? (
          <div className="flex justify-center py-20"><Loader2 className="w-7 h-7 animate-spin text-qv-primary" /></div>
        ) : !data ? (
          <p className="text-white/50 text-center py-10">No se pudieron cargar las métricas.</p>
        ) : (
          <div className="px-5 mt-4" data-testid="metrics-content">
            {/* Resumen BIG */}
            <div className="grid grid-cols-2 gap-2.5">
              <Big icon={Users} label="Usuarios totales" value={totals.users} color="text-qv-secondary" />
              <Big icon={UserPlus} label={`Nuevos ${days}d`} value={totals.new_users_window} hint={conversion != null ? `${conversion}% conversión visitantes` : ""} color="text-qv-primary" />
              <Big icon={Eye} label="Visitantes anónimos" value={totals.anon_visitors} hint={`${totals.anon_pageviews} pageviews`} />
              <Big icon={UserPlus} label="No se registraron" value={totals.anon_not_signed_up} color="text-orange-300" />
              <Big icon={PartyPopper} label="Van (voy)" value={totals.going_total} color="text-qv-primary" />
              <Big icon={Star} label="Interesados" value={totals.interested_total} color="text-qv-secondary" />
              <Big icon={MousePointerClick} label="Clics entradas" value={totals.ticket_clicks_total} />
              <Big icon={Ticket} label="Entradas (tengo)" value={totals.tickets_total} color="text-emerald-300" />
              <Big icon={Zap} label="Planes creados" value={totals.plans_created} color="text-pink-300" />
              <Big icon={BarChart3} label="Eventos registrados" value={totals.total_events_logged} hint="todas las acciones" />
            </div>

            {/* Sesiones */}
            <Section title="Sesión promedio" icon={Clock}>
              <div className="rounded-2xl bg-white/[0.03] border border-white/10 p-3.5 flex items-center justify-between">
                <div>
                  <p className="font-display text-3xl font-black text-white tabular-nums">{data.sessions?.avg_session_minutes ?? "—"} min</p>
                  <p className="text-white/40 text-xs mt-1">media por sesión · {data.sessions?.users_measured} usuarios medidos</p>
                </div>
                <TrendingUp className="w-10 h-10 text-qv-secondary/60" />
              </div>
            </Section>

            {/* Daily chart */}
            {dailyChart && dailyChart.rows.length > 0 && (
              <Section title="Actividad diaria" icon={LineChart}>
                <div className="rounded-2xl bg-white/[0.03] border border-white/10 p-3" data-testid="metrics-daily">
                  <div className="flex flex-col gap-1.5">
                    {dailyChart.rows.slice(-20).map((r) => (
                      <div key={r.date} className="flex items-center gap-2 text-[11px]">
                        <span className="w-16 text-white/50 shrink-0">{r.date.slice(5)}</span>
                        <div className="flex-1">
                          <Bar value={r.opens} max={dailyChart.maxOpens} color="bg-qv-secondary" />
                        </div>
                        <span className="w-10 text-right tabular-nums text-white/70 font-semibold">{r.opens}</span>
                        <span className="w-8 text-right tabular-nums text-qv-primary font-bold">+{r.signups}</span>
                      </div>
                    ))}
                  </div>
                  <p className="text-[10px] text-white/40 mt-2">cian = aperturas · rosa = nuevos registros</p>
                </div>
              </Section>
            )}

            {/* Top eventos por views */}
            <Section title="Top eventos · vistas" icon={Eye}>
              <Table
                testId="metrics-top-views"
                columns={[
                  { label: "Evento", key: "name", render: (r) => <div className="min-w-0"><p className="truncate font-semibold text-white">{r.name}</p><p className="text-[10px] text-white/40 truncate">{r.venue} · {r.city}</p></div> },
                  { label: "Vistas", key: "views", right: true },
                  { label: "Van", key: "going", right: true },
                ]}
                rows={data.top_views || []}
              />
            </Section>

            {/* Top eventos por "voy" */}
            <Section title="Top eventos · voy" icon={PartyPopper}>
              <Table
                testId="metrics-top-going"
                columns={[
                  { label: "Evento", key: "name", render: (r) => <div className="min-w-0"><p className="truncate font-semibold text-white">{r.name}</p><p className="text-[10px] text-white/40 truncate">{r.venue}</p></div> },
                  { label: "Voy", key: "going", right: true },
                  { label: "Interés", key: "interested", right: true },
                ]}
                rows={data.top_going || []}
              />
            </Section>

            {/* Top eventos por interés */}
            <Section title="Top eventos · interés" icon={Star}>
              <Table
                testId="metrics-top-interest"
                columns={[
                  { label: "Evento", key: "name", render: (r) => <div className="min-w-0"><p className="truncate font-semibold text-white">{r.name}</p><p className="text-[10px] text-white/40 truncate">{r.venue}</p></div> },
                  { label: "Interés", key: "interested", right: true },
                  { label: "Vistas", key: "views", right: true },
                ]}
                rows={data.top_interested || []}
              />
            </Section>

            {/* Top clicks en comprar */}
            <Section title="Top clics 'Comprar entrada'" icon={MousePointerClick}>
              <Table
                testId="metrics-top-clicks"
                columns={[
                  { label: "Evento", key: "name", render: (r) => <div className="min-w-0"><p className="truncate font-semibold text-white">{r.name}</p><p className="text-[10px] text-white/40 truncate">{r.venue}</p></div> },
                  { label: "Clics", key: "ticket_clicks", right: true },
                  { label: "Entradas", key: "tickets", right: true },
                ]}
                rows={data.top_clicks || []}
              />
            </Section>

            {/* Ciudades */}
            <Section title="Ciudades más visitadas" icon={Globe}>
              <Table
                testId="metrics-cities"
                columns={[
                  { label: "Ciudad", key: "city" },
                  { label: "Vistas", key: "views", right: true },
                ]}
                rows={data.top_cities || []}
              />
            </Section>

            {/* Primera acción tras registro */}
            <Section title="Primera acción tras registrarse" icon={UserPlus}>
              <Table
                testId="metrics-first-actions"
                columns={[
                  { label: "Acción", key: "event" },
                  { label: "N usuarios", key: "n", right: true },
                ]}
                rows={data.first_actions_after_signup || []}
              />
            </Section>

            {/* Breakdown de TODOS los eventos */}
            <Section title="Todas las acciones registradas" icon={BarChart3}>
              <div className="rounded-2xl bg-white/[0.03] border border-white/10 p-3" data-testid="metrics-activity-breakdown">
                <div className="flex flex-col gap-1.5">
                  {activityRows.slice(0, 40).map((r) => (
                    <div key={r.event} className="flex items-center gap-2 text-[11px]">
                      <span className="flex-1 min-w-0 truncate text-white/80 font-mono">{r.event}</span>
                      <div className="w-32 shrink-0">
                        <Bar value={r.n} max={activityMax} color="bg-qv-primary" />
                      </div>
                      <span className="w-14 text-right tabular-nums text-white font-semibold">{r.n}</span>
                    </div>
                  ))}
                </div>
                {activityRows.length === 0 && <p className="text-white/40 text-sm text-center py-4">Sin eventos registrados en este rango.</p>}
              </div>
            </Section>

            {/* Breakdown por usuario */}
            <Section title="Acciones por usuario" icon={User}>
              <div className="rounded-2xl bg-white/[0.03] border border-white/10 overflow-x-auto" data-testid="metrics-per-user">
                {(!data.per_user || data.per_user.length === 0) ? (
                  <p className="text-white/40 text-sm py-4 text-center">Sin datos de usuarios en este rango.</p>
                ) : (
                  <table className="w-full text-left text-xs min-w-[640px]">
                    <thead>
                      <tr className="text-[10px] uppercase tracking-wider text-white/40 border-b border-white/10">
                        <th className="px-2.5 py-2 font-bold">Usuario</th>
                        <th className="px-2 py-2 font-bold text-right">Total</th>
                        <th className="px-2 py-2 font-bold text-right">Views</th>
                        <th className="px-2 py-2 font-bold text-right">Vista ev.</th>
                        <th className="px-2 py-2 font-bold text-right">Voy</th>
                        <th className="px-2 py-2 font-bold text-right">Interés</th>
                        <th className="px-2 py-2 font-bold text-right">Estuve</th>
                        <th className="px-2 py-2 font-bold text-right">Clics</th>
                        <th className="px-2 py-2 font-bold text-right">Entr.</th>
                        <th className="px-2 py-2 font-bold text-right">Planes</th>
                        <th className="px-2 py-2 font-bold text-right">Mom.</th>
                      </tr>
                    </thead>
                    <tbody>
                      {data.per_user.map((u) => (
                        <tr key={u.user_id} className="border-b border-white/5 last:border-0">
                          <td className="px-2.5 py-2 min-w-[160px]">
                            <p className="font-semibold text-white truncate flex items-center gap-1.5">
                              {u.name}
                              {u.is_admin ? (
                                <span className="text-[8px] uppercase tracking-widest bg-amber-500/20 text-amber-300 px-1.5 py-0.5 rounded-full font-bold">adm</span>
                              ) : null}
                            </p>
                            <p className="text-[10px] text-white/40 truncate">@{u.username || "—"} · {u.email}</p>
                          </td>
                          <td className="px-2 py-2 text-right tabular-nums font-black text-white">{u.total_actions}</td>
                          <td className="px-2 py-2 text-right tabular-nums text-white/80">{u.pageviews}</td>
                          <td className="px-2 py-2 text-right tabular-nums text-white/80">{u.event_views}</td>
                          <td className="px-2 py-2 text-right tabular-nums text-qv-primary font-semibold">{u.going}</td>
                          <td className="px-2 py-2 text-right tabular-nums text-qv-secondary font-semibold">{u.interested}</td>
                          <td className="px-2 py-2 text-right tabular-nums text-white/70">{u.estuve}</td>
                          <td className="px-2 py-2 text-right tabular-nums text-white/80">{u.ticket_clicks}</td>
                          <td className="px-2 py-2 text-right tabular-nums text-emerald-300 font-semibold">{u.tickets}</td>
                          <td className="px-2 py-2 text-right tabular-nums text-pink-300 font-semibold">{u.plans_created}</td>
                          <td className="px-2 py-2 text-right tabular-nums text-yellow-300 font-semibold">{u.moments_captured}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                )}
                <p className="text-[10px] text-white/40 px-3 py-2">
                  Top 100 por total de acciones. {includeAdmin ? "Incluye admins." : "Admins excluidos."}
                </p>
              </div>
            </Section>

            <div className="mt-6 flex items-center justify-center gap-2 text-xs text-white/40">
              <button onClick={() => refetch()} disabled={isFetching} className="flex items-center gap-1.5 px-3 py-2 rounded-xl bg-white/5 border border-white/10 active:scale-95 disabled:opacity-50">
                {isFetching ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <TrendingUp className="w-3.5 h-3.5" />}
                Refrescar
              </button>
              <span>· datos de los últimos {days} días</span>
            </div>

            {/* Herramientas admin: probar notificaciones + Live Activities sin
                esperar a que llegue el momento real o el cron del lunes. */}
            <Section title="Herramientas de prueba" icon={Zap}>
              <div className="rounded-2xl bg-white/[0.03] border border-white/10 p-3.5 flex flex-col gap-2.5" data-testid="admin-tools">
                <button
                  onClick={() => runTest("moment")}
                  disabled={testing === "moment"}
                  data-testid="admin-test-moment"
                  className="w-full h-11 rounded-xl bg-gradient-to-r from-yellow-300 via-orange-400 to-pink-500 text-black font-black text-sm flex items-center justify-center gap-2 active:scale-[0.98] disabled:opacity-60"
                >
                  {testing === "moment" ? <Loader2 className="w-4 h-4 animate-spin" /> : <Zap className="w-4 h-4" />}
                  Probar notificación "EL MOMENTO" (y Live Activity)
                </button>
                <button
                  onClick={() => runTest("weekly")}
                  disabled={testing === "weekly"}
                  data-testid="admin-test-weekly"
                  className="w-full h-11 rounded-xl bg-white/[0.08] border border-white/15 text-white font-bold text-sm flex items-center justify-center gap-2 active:scale-[0.98] disabled:opacity-60"
                >
                  {testing === "weekly" ? <Loader2 className="w-4 h-4 animate-spin" /> : <TrendingUp className="w-4 h-4" />}
                  Disparar resumen semanal ahora
                </button>
                {testResult && (
                  <div
                    data-testid="admin-test-result"
                    className={`rounded-xl text-xs p-2.5 ${testResult.ok ? "bg-emerald-500/10 border border-emerald-500/30 text-emerald-200" : "bg-red-500/10 border border-red-500/30 text-red-200"}`}
                  >
                    {testResult.ok ? (
                      <>
                        <b>✓ Enviado.</b>
                        {testResult.kind === "moment" ? (
                          <span className="block mt-1 text-white/70">
                            {testResult.data?.apns_configured
                              ? `Live Activities arrancadas: ${testResult.data?.live_activities_started ?? 0}`
                              : "APNs no configurado — solo push in-app"}
                            {testResult.data?.hint ? (
                              <span className="block text-[10px] mt-1 text-white/50">{testResult.data.hint}</span>
                            ) : null}
                          </span>
                        ) : (
                          <span className="block mt-1 text-white/70">
                            Snapshot generado · {testResult.data?.snapshot?.users?.new ?? 0} usuarios nuevos
                          </span>
                        )}
                      </>
                    ) : (
                      <>✗ Error: {String(testResult.error)}</>
                    )}
                  </div>
                )}
                <p className="text-[10.5px] text-white/40 leading-snug mt-1">
                  La notificación llega como push suave (NO ruidosa) + modal in-app. En iPhone 16.2+
                  con la app rebuilt y con start-token subido, además arranca la Live Activity en la
                  Dynamic Island con el countdown.
                </p>
              </div>
            </Section>
          </div>
        )}
      </div>
    </div>
  );
}
