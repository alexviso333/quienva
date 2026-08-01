import { useState, useEffect } from "react";
import { useQuery, useMutation } from "@tanstack/react-query";
import { useNavigate } from "react-router-dom";
import api from "@/lib/api";
import { AppShell } from "@/components/AppShell";
import { ChevronLeft, Loader2, Bell } from "lucide-react";
import { toast } from "sonner";

const LABELS = {
  new_event: { t: "Nuevas fiestas en tu ciudad", d: "Cuando se publica una fiesta nueva" },
  tickets_on_sale: { t: "Entradas a la venta", d: "Justo cuando salen a la venta" },
  tickets_low_stock: { t: "Pocas entradas", d: "Cuando quedan pocas" },
  tickets_sold_out: { t: "Agotado", d: "Cuando se agotan las entradas" },
  tickets_price_down: { t: "Bajada de precio", d: "Cuando baja el precio" },
  tickets_price_up: { t: "Subida de precio", d: "Nueva fase / sube el precio" },
  friend_going: { t: "Amigos van a un plan", d: "Cuando un amigo se apunta" },
};

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
  const [prefs, setPrefs] = useState(null);
  const [keys, setKeys] = useState([]);
  const { data, isLoading } = useQuery({
    queryKey: ["notif-prefs"],
    queryFn: async () => (await api.get("/me/notif-prefs")).data,
    staleTime: 30_000,
  });
  useEffect(() => {
    if (data) { setPrefs(data.prefs); setKeys(data.keys); }
  }, [data]);

  const save = useMutation({
    mutationFn: async (next) => (await api.put("/me/notif-prefs", { prefs: next })).data,
    onError: () => toast.error("No se pudo guardar"),
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
            <Bell className="w-5 h-5 text-qv-primary" /> Avisos
          </h1>
          <p className="text-white/45 text-xs">Elige qué notificaciones quieres recibir</p>
        </div>
      </header>

      {isLoading || !prefs ? (
        <div className="py-16 flex justify-center"><Loader2 className="w-6 h-6 animate-spin text-white/50" /></div>
      ) : (
        <div className="px-4 flex flex-col gap-2" data-testid="notif-prefs">
          {keys.map((k) => (
            <div key={k} className="flex items-center gap-3 rounded-2xl border border-white/10 bg-white/[0.04] p-3.5">
              <div className="flex-1 min-w-0">
                <p className="text-white text-sm font-semibold">{LABELS[k]?.t || k}</p>
                <p className="text-white/40 text-xs">{LABELS[k]?.d || ""}</p>
              </div>
              <Toggle on={!!prefs[k]} onClick={() => toggle(k)} />
            </div>
          ))}
        </div>
      )}
    </AppShell>
  );
}
