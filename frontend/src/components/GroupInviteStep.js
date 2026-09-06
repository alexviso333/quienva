import { useState } from "react";
import { useTranslation } from "react-i18next";
import { MessageCircle, Copy, Share2, Users, Loader2, Check, Sparkles } from "lucide-react";
import api from "@/lib/api";
import { toast } from "sonner";
import { groupInviteWhatsApp, shareGroupInvite, groupInviteUrl } from "@/lib/contacts";

// Onboarding "Monta tu grupo" step, redesigned as TWO clear phases so it never
// feels crowded or confusing:
//   Phase A — name the group and tap ONE explicit button: "Crear mi grupo".
//   Phase B — the group now exists; a success banner appears and only THEN do the
//             invite actions show (WhatsApp primary, share/copy secondary).
// This removes the old confusion where a single button both created AND shared.
export default function GroupInviteStep({ onCreated }) {
  const { t } = useTranslation();
  const [name, setName] = useState("");
  const [busy, setBusy] = useState(false);
  const [group, setGroup] = useState(null); // { id, name, code }

  const createGroup = async () => {
    const clean = name.trim() || t("groupinvite.default_name", "Mi grupo");
    setBusy(true);
    try {
      const { data: g } = await api.post("/groups", { name: clean });
      const { data: inv } = await api.get(`/groups/${g.id}/invite`);
      const created = { id: g.id, name: clean, code: inv.code };
      setGroup(created);
      onCreated?.(created);
    } catch (e) {
      toast.error(t("groupinvite.err_create", "No se pudo crear el grupo, inténtalo de nuevo"));
    } finally {
      setBusy(false);
    }
  };

  const shareWhatsApp = () => group && groupInviteWhatsApp(group.name, group.code);

  const doShare = async () => {
    if (!group) return;
    const res = await shareGroupInvite(group.name, group.code);
    if (res === "copied") toast.success(t("groupinvite.copied", "¡Enlace copiado!"));
  };

  const copyLink = async () => {
    if (!group) return;
    try {
      await navigator.clipboard.writeText(groupInviteUrl(group.code));
      toast.success(t("groupinvite.copied", "¡Enlace copiado!"));
    } catch {
      // iOS/Safari without clipboard permission → fall back to the native share.
      const res = await shareGroupInvite(group.name, group.code);
      if (res === "copied") toast.success(t("groupinvite.copied", "¡Enlace copiado!"));
    }
  };

  // ---- PHASE A: create the group (clean, one clear action) ----
  if (!group) {
    return (
      <div className="flex flex-col gap-3.5 w-full" data-testid="group-invite-step">
        <div className="relative">
          <Users className="absolute left-4 top-1/2 -translate-y-1/2 w-5 h-5 text-white/40 pointer-events-none" />
          <input
            data-testid="group-name-input"
            value={name}
            onChange={(e) => setName(e.target.value)}
            maxLength={40}
            onKeyDown={(e) => { if (e.key === "Enter") createGroup(); }}
            placeholder={t("groupinvite.name_placeholder", "Nombre del grupo (ej. Clase de Bio)")}
            className="w-full h-14 rounded-2xl bg-white/5 border border-white/12 pl-12 pr-4 text-white placeholder-white/40 focus:outline-none focus:border-qv-primary/60"
          />
        </div>
        <button
          type="button"
          data-testid="group-create-btn"
          onClick={createGroup}
          disabled={busy}
          className="h-14 rounded-2xl bg-qv-primary text-white font-bold text-base flex items-center justify-center gap-2 active:scale-95 transition-transform disabled:opacity-60"
        >
          {busy ? <Loader2 className="w-5 h-5 animate-spin" /> : <Sparkles className="w-5 h-5" />}
          {t("groupinvite.create", "Crear mi grupo")}
        </button>
        <p className="text-white/40 text-xs text-center leading-relaxed px-2">
          {t("groupinvite.create_hint", "En el siguiente paso invitas a tu gente. Quien entre por tu enlace se une solo y os hacéis amigos.")}
        </p>
      </div>
    );
  }

  // ---- PHASE B: group created → invite your crew ----
  return (
    <div className="flex flex-col gap-3.5 w-full" data-testid="group-invite-step">
      <div className="flex items-center gap-3 rounded-2xl bg-qv-primary/10 border border-qv-primary/30 px-4 py-3.5" data-testid="group-created">
        <div className="w-10 h-10 rounded-full bg-qv-primary/20 flex items-center justify-center shrink-0">
          <Check className="w-5 h-5 text-qv-primary" />
        </div>
        <div className="min-w-0">
          <p className="text-sm text-white font-bold truncate">{group.name}</p>
          <p className="text-white/55 text-xs">{t("groupinvite.ready_sub", "Grupo creado. Ahora invita a tu gente 👇")}</p>
        </div>
      </div>

      <button
        type="button"
        data-testid="group-invite-whatsapp"
        onClick={shareWhatsApp}
        className="h-14 rounded-2xl bg-[#25D366] text-black font-bold text-base flex items-center justify-center gap-2 active:scale-95 transition-transform shadow-[0_0_22px_rgba(37,211,102,0.35)]"
      >
        <MessageCircle className="w-5 h-5" />
        {t("groupinvite.invite_whatsapp", "Invitar por WhatsApp")}
      </button>

      <div className="flex gap-2">
        <button
          type="button"
          data-testid="group-invite-share"
          onClick={doShare}
          className="flex-1 h-12 rounded-2xl bg-white/5 border border-white/15 text-white font-semibold flex items-center justify-center gap-2 active:scale-95"
        >
          <Share2 className="w-4 h-4" /> {t("groupinvite.share", "Compartir")}
        </button>
        <button
          type="button"
          data-testid="group-invite-copy"
          onClick={copyLink}
          className="flex-1 h-12 rounded-2xl bg-white/5 border border-white/15 text-white font-semibold flex items-center justify-center gap-2 active:scale-95"
        >
          <Copy className="w-4 h-4" /> {t("groupinvite.copy", "Copiar enlace")}
        </button>
      </div>

      <p className="text-white/40 text-xs text-center leading-relaxed px-2">
        {t("groupinvite.hint", "Quien entre por tu enlace se une solo a tu grupo y os hacéis amigos automáticamente.")}
      </p>
    </div>
  );
}
