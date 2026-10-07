import { useState, useMemo } from "react";
import { useNavigate } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import api, { API } from "@/lib/api";
import { ArrowLeft, Loader2, Eye, PartyPopper, Star, MousePointerClick, Ticket, Users, UserPlus, Clock, Globe, BarChart3, Download, TrendingUp, Zap, LineChart, Sparkles } from "lucide-react";

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
  const [testing, setTesting] = useState(null);
  const [testResult, setTestResult] = useState(null);

  const { data, isLoading, refetch, isFetching } = useQuery({
    queryKey: ["admin-metrics", days],
    queryFn: async () => (await api.get(`/admin/metrics?days=${days}`)).data,
    staleTime: 30000,
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
      fetch(`${base}/admin/metrics/export.csv?days=${days}`, {
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

        {/* Preview "El Momento" — admin-only visual test */}
        <div className="px-5 mt-2">
          <button
            onClick={async () => {
              try {
                const r = await api.post("/admin/moment/test");
                const d = r?.data || {};
                const parts = [
                  `prompt_id: ${d.prompt_id || "?"}`,
                  `APNs: ${d.apns_configured ? "ON" : "OFF"}`,
                  `tokens Live Activity: ${d.live_activity_tokens_admin ?? 0}`,
                ];
                alert(
                  "✅ Momento REAL disparado:\n\n" + parts.join("\n") +
                  "\n\n" + (d.hint || "") +
                  "\n\nAhora abre la app en tu iPhone (TestFlight)."
                );
                // Navegar al feed para ver el modal WOW aparecer con datos reales
                navigate("/feed");
              } catch (e) {
                alert("❌ Error disparando el Momento: " + (e?.response?.data?.detail || e.message));
              }
            }}
            data-testid="metrics-preview-moment"
            className="w-full h-12 rounded-2xl bg-gradient-to-r from-pink-500 via-orange-400 to-yellow-300 text-black font-display font-black text-sm flex items-center justify-center gap-2 active:scale-[0.98] shadow-[0_10px_30px_-10px_rgba(236,72,153,0.6)]"
          >
            <Sparkles className="w-4 h-4" strokeWidth={2.5} />
            Disparar "El Momento" REAL (solo yo)
          </button>
          <p className="text-[10px] text-white/40 text-center mt-1.5">
            Flujo completo: push APNs + Live Activity + modal in-app. Solo tu usuario lo recibe.
          </p>
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
