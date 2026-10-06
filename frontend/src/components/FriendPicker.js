import { useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import { Check, Search, Loader2, UserPlus, Clock } from "lucide-react";
import { useNavigate } from "react-router-dom";
import { AvatarCircle } from "@/components/AvatarCircle";
import { useAuth } from "@/context/AuthContext";
import api from "@/lib/api";

// Selector de amigos DE LA APP para invitarlos a un plan.
// Dos modos:
//  - sin `slug`: lista plana de /friends (se usa al CREAR el plan).
//  - con `slug`: /plans/{slug}/invitables, que marca a quién ya se invitó o ya
//    ha respondido (se usa dentro de un plan ya creado).
// Si el usuario no tiene cuenta no se renderiza nada: el plan se sigue pudiendo
// compartir por enlace, que es el camino sin fricción para los que no la tienen.
export default function FriendPicker({ slug = null, selected = [], onChange, max = 30 }) {
  const { t } = useTranslation();
  const { user } = useAuth();
  const navigate = useNavigate();
  const [q, setQ] = useState("");

  const { data, isLoading } = useQuery({
    queryKey: slug ? ["plan-invitables", slug] : ["friends-picker"],
    queryFn: async () => {
      const { data } = await api.get(slug ? `/plans/${slug}/invitables` : "/friends");
      return slug ? data.friends || [] : (data || []).map((f) => ({ ...f, estado: "nuevo" }));
    },
    enabled: !!user,
    staleTime: 60000,
  });

  const friends = useMemo(() => {
    const list = data || [];
    const needle = q.trim().toLowerCase();
    if (!needle) return list;
    return list.filter((f) => `${f.name || ""} ${f.username || ""}`.toLowerCase().includes(needle));
  }, [data, q]);

  if (!user) return null;

  const toggle = (id) => {
    if (selected.includes(id)) onChange(selected.filter((x) => x !== id));
    else if (selected.length < max) onChange([...selected, id]);
  };

  if (isLoading) {
    return (
      <div className="flex items-center justify-center py-5" data-testid="friend-picker-loading">
        <Loader2 className="w-5 h-5 text-qv-primary animate-spin" />
      </div>
    );
  }

  // Sin amigos todavía: en vez de un hueco vacío, el camino para conseguirlos.
  if (!(data || []).length) {
    return (
      <button
        type="button"
        data-testid="friend-picker-empty"
        onClick={() => navigate("/friends")}
        className="w-full flex items-center gap-3 rounded-2xl border border-dashed border-white/15 bg-white/[0.02] p-3 text-left active:scale-[0.99]"
      >
        <span className="w-9 h-9 rounded-xl bg-qv-secondary/15 flex items-center justify-center shrink-0">
          <UserPlus className="w-4 h-4 text-qv-secondary" />
        </span>
        <span className="min-w-0 flex-1">
          <span className="block text-sm font-bold text-white">{t("friendpicker.empty_title", "Aún no tienes amigos en la app")}</span>
          <span className="block text-xs text-white/50">{t("friendpicker.empty_sub", "Añádelos y podrás montar el plan en un toque")}</span>
        </span>
      </button>
    );
  }

  return (
    <div data-testid="friend-picker">
      {(data || []).length > 6 ? (
        <div className="relative mb-2">
          <Search className="w-4 h-4 text-white/30 absolute left-3 top-1/2 -translate-y-1/2" />
          <input
            value={q}
            onChange={(e) => setQ(e.target.value)}
            placeholder={t("friendpicker.search", "Buscar amigo...")}
            data-testid="friend-picker-search"
            className="w-full bg-[#0a0712] border border-white/12 rounded-xl pl-9 pr-3 py-2.5 text-sm outline-none focus:border-qv-primary/50"
          />
        </div>
      ) : null}

      <div className="flex flex-col gap-1 max-h-[42vh] overflow-y-auto -mx-1 px-1">
        {friends.map((f) => {
          const taken = f.estado && f.estado !== "nuevo";
          const on = selected.includes(f.user_id);
          return (
            <button
              key={f.user_id}
              type="button"
              disabled={taken}
              data-testid={`friend-pick-${f.user_id}`}
              onClick={() => toggle(f.user_id)}
              className={`flex items-center gap-2.5 rounded-xl border p-2 text-left transition-colors ${
                taken
                  ? "border-white/8 bg-white/[0.02] opacity-55"
                  : on
                    ? "border-qv-primary/60 bg-qv-primary/10"
                    : "border-white/10 bg-white/[0.03]"
              }`}
            >
              <AvatarCircle name={f.name} picture={f.picture} size={32} ring={false} />
              <span className="min-w-0 flex-1">
                <span className="block text-sm font-semibold text-white truncate">{f.name}</span>
                {taken ? (
                  <span className="block text-[11px] text-white/45">
                    {f.estado === "invitado"
                      ? t("friendpicker.already_invited", "Ya invitado")
                      : t("friendpicker.already_answered", "Ya ha respondido")}
                  </span>
                ) : null}
              </span>
              {taken ? (
                <Clock className="w-4 h-4 text-white/30 shrink-0" />
              ) : (
                <span
                  className={`w-5 h-5 rounded-full border flex items-center justify-center shrink-0 ${
                    on ? "bg-qv-primary border-qv-primary" : "border-white/25"
                  }`}
                >
                  {on ? <Check className="w-3 h-3 text-white" /> : null}
                </span>
              )}
            </button>
          );
        })}
        {friends.length === 0 ? (
          <p className="text-white/40 text-xs text-center py-3">{t("friendpicker.no_match", "Ningún amigo con ese nombre")}</p>
        ) : null}
      </div>
    </div>
  );
}
