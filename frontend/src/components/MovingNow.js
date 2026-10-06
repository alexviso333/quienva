import { useTranslation } from "react-i18next";
import { TrendingUp } from "lucide-react";

// "Se está moviendo" ya no es un carrusel aparte en el feed (empujaba "Esta
// noche" fuera de la primera pantalla). Ahora es una etiqueta pequeña sobre las
// propias tarjetas de los eventos con actividad REAL (nunca inventamos números).

export function movementScore(e) {
  return (e?.total_going || 0) * 2
    + (e?.total_interested || 0)
    + (e?.signups_today || 0) * 3
    + (((e?.friends_going || []).length) + ((e?.friends_interested || []).length)) * 4;
}

// Solo actividad agregada significativa (evita "prueba social" de 1 RSVP).
export const MIN_MOVEMENT = 4;

export function isMoving(e) {
  return movementScore(e) >= MIN_MOVEMENT;
}

export function MovingBadge({ event, size = "md" }) {
  const { t } = useTranslation();
  if (!isMoving(event)) return null;
  const sm = size === "sm";
  return (
    <span
      data-testid={`moving-badge-${event.id}`}
      title={t("moving.title", "Se está moviendo")}
      className={`inline-flex items-center gap-1 rounded-full bg-black/55 backdrop-blur-sm border border-qv-secondary/40 text-qv-secondary font-black uppercase tracking-wider ${sm ? "text-[9px] px-1.5 py-0.5" : "text-[10px] px-2 py-1"}`}
    >
      <TrendingUp className={sm ? "w-2.5 h-2.5" : "w-3 h-3"} />
      {t("moving.badge_short", "Se mueve")}
    </span>
  );
}

export default MovingBadge;
