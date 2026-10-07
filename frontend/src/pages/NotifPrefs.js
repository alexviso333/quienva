import { useState, useEffect } from "react";
import { useQuery, useMutation } from "@tanstack/react-query";
import { useNavigate } from "react-router-dom";
import api from "@/lib/api";
import { AppShell } from "@/components/AppShell";
import { ChevronLeft, Loader2, Bell } from "lucide-react";
import { toast } from "@/lib/notify";
import { useTranslation } from "react-i18next";

function Toggle({ on, onClick }) {
  return (
    <button
      onClick={onClick}
      className={`w-11 h-6 rounded-full flex-shrink-0 transition-colors relative ${on ? "bg-qv-primary" : "bg-white/15"}`}
    >
      <span className={`absolute top-0.5 w-5 h-5 rounded-full bg-white transition-all ${on ? "left-[22px]" : "left-0.5"}`} />
    </button>
  );
}

export default function NotifPrefs() {
  const navigate = useNavigate();
  const { t } = useTranslation();
  const [prefs, setPrefs] = useState(null);
  const [keys, setKeys] = useState([]);
  const [mode, setMode] = useState("esenciales");
  const [extraTypes, setExtraTypes] = useState([]);
  const { data, isLoading } = useQuery({
    queryKey: ["notif-prefs"],
    queryFn: async () => (await api.get("/me/notif-prefs")).data,
    staleTime: 30_000,
  });
  useEffect(() => {
    if (data) {
      setPrefs(data.prefs);
      setKeys(data.keys);
      setMode(data.mode || "esenciales");
      setExtraTypes(data.extra_types || []);
    }
  }, [data]);

  const saveMode = useMutation({
    mutationFn: async (m) => (await api.put("/me/notif-mode", { mode: m })).data,
    onError: () => toast.error(t("notifprefs.toast_error")),
  });

  const save = useMutation({
    mutationFn: async (next) => (await api.put("/me/notif-prefs", { prefs: next })).data,
    onError: () => toast.error(t("notifprefs.toast_error")),
  });

  const toggle = (k) => {
    const next = { ...prefs, [k]: !prefs[k] };
    setPrefs(next);
    save.mutate(next);
  };

  return (
    <AppShell>
      <header className="px-5 pt-8 pb-4 flex items-center gap-3">
        <button onClick={() => navigate(-1)} className="p-1.5 rounded-lg bg-white/10 active:scale-95"><ChevronLeft className="w-5 h-5 text-white" /></button>
        <div>
          <h1 className="font-display text-2xl font-black tracking-tight flex items-center gap-2">
            <Bell className="w-5 h-5 text-qv-primary" /> {t("notifprefs.title")}
          </h1>
          <p className="text-white/45 text-xs">{t("notifprefs.subtitle")}</p>
        </div>
      </header>

      {isLoading || !prefs ? (
        <div className="py-16 flex justify-center"><Loader2 className="w-6 h-6 animate-spin text-white/50" /></div>
      ) : (
        <div className="px-4 flex flex-col gap-2" data-testid="notif-prefs">
          <div className="grid grid-cols-2 gap-2 mb-2" data-testid="notif-mode-picker">
            {[
              { id: "esenciales", title: "Esenciales", desc: "Tu gente, tu grupo, tus planes y tus fiestas" },
              { id: "todo", title: "Todo", desc: "También fiestas nuevas, entradas y recordatorios" },
            ].map((m) => {
              const active = mode === m.id;
              return (
                <button
                  key={m.id}
                  data-testid={`notif-mode-${m.id}`}
                  onClick={() => { setMode(m.id); saveMode.mutate(m.id); }}
                  className={`text-left rounded-2xl border p-3.5 transition-colors ${active ? "border-qv-primary/60 bg-qv-primary/12" : "border-white/10 bg-white/[0.04]"}`}
                >
                  <p className={`text-sm font-black ${active ? "text-qv-primary" : "text-white"}`}>{m.title}</p>
                  <p className="text-white/45 text-[11px] leading-snug mt-0.5">{m.desc}</p>
                </button>
              );
            })}
          </div>
          {keys.map((k) => {
            const isExtra = extraTypes.includes(k);
            const muted = isExtra && mode === "esenciales" && prefs[k] !== true;
            return (
            <div key={k} className={`flex items-center gap-3 rounded-2xl border border-white/10 bg-white/[0.04] p-3.5 ${muted ? "opacity-55" : ""}`}>
              <div className="flex-1 min-w-0">
                <p className="text-white text-sm font-semibold">{t(`notifprefs.labels.${k}.t`, { defaultValue: k })}</p>
                <p className="text-white/40 text-xs">
                  {muted ? "Silenciado en modo Esenciales" : t(`notifprefs.labels.${k}.d`, { defaultValue: "" })}
                </p>
              </div>
              <Toggle on={!!prefs[k] && !muted} onClick={() => toggle(k)} />
            </div>
            );
          })}
        </div>
      )}
    </AppShell>
  );
}
