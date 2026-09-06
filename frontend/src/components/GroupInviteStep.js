import { useState } from "react";
import { useTranslation } from "react-i18next";
import { MessageCircle, Copy, Share2, Users, Loader2, Check } from "lucide-react";
import api from "@/lib/api";
import { toast } from "sonner";
import { groupInviteWhatsApp, shareGroupInvite, groupInviteUrl } from "@/lib/contacts";

// Onboarding "Monta tu grupo" step. The user names + creates their main group,
// then shares a group invite link by WhatsApp. Anyone who signs up through that
// link auto-joins the group and becomes friends with every member. This is the
// core viral loop: one tap invites the whole crew.
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
      return created;
    } catch (e) {
      toast.error(t("groupinvite.err_create", "No se pudo crear el grupo, inténtalo de nuevo"));
      return null;
    } finally {
      setBusy(false);
    }
  };

  const shareWhatsApp = async () => {
    const g = group || (await createGroup());
    if (g) groupInviteWhatsApp(g.name, g.code);
  };

  const doShare = async () => {
    const g = group || (await createGroup());
    if (!g) return;
    const res = await shareGroupInvite(g.name, g.code);
    if (res === "copied") toast.success(t("groupinvite.copied", "¡Enlace copiado!"));
  };

  const copyLink = async () => {
    const g = group || (await createGroup());
    if (!g) return;
    try {
      await navigator.clipboard.writeText(groupInviteUrl(g.code));
      toast.success(t("groupinvite.copied", "¡Enlace copiado!"));
    } catch {
      // iOS/Safari without clipboard permission → fall back to the native share.
      const res = await shareGroupInvite(g.name, g.code);
      if (res === "copied") toast.success(t("groupinvite.copied", "¡Enlace copiado!"));
    }
  };

  return (
    <div className="flex flex-col gap-4 w-full" data-testid="group-invite-step">
      {!group ? (
        <div className="relative">
          <Users className="absolute left-4 top-1/2 -translate-y-1/2 w-5 h-5 text-white/40 pointer-events-none" />
          <input
            data-testid="group-name-input"
            value={name}
            onChange={(e) => setName(e.target.value)}
            maxLength={40}
            placeholder={t("groupinvite.name_placeholder", "Nombre del grupo (ej. Clase de Bio)")}
            className="w-full h-14 rounded-2xl bg-white/5 border border-white/12 pl-12 pr-4 text-white placeholder-white/40 focus:outline-none focus:border-qv-primary/60"
          />
        </div>
      ) : (
        <div className="flex items-center gap-2 rounded-2xl bg-qv-primary/10 border border-qv-primary/30 px-4 py-3" data-testid="group-created">
          <Check className="w-5 h-5 text-qv-primary flex-shrink-0" />
          <p className="text-sm text-white">
            {t("groupinvite.ready", "Grupo")} <span className="font-bold">{group.name}</span> {t("groupinvite.ready2", "listo. Invita a tu gente 👇")}
          </p>
        </div>
      )}

      <button
        type="button"
        data-testid="group-invite-whatsapp"
        onClick={shareWhatsApp}
        disabled={busy}
        className="h-14 rounded-2xl bg-[#25D366] text-black font-bold text-base flex items-center justify-center gap-2 active:scale-95 transition-transform shadow-[0_0_22px_rgba(37,211,102,0.35)] disabled:opacity-60"
      >
        {busy ? <Loader2 className="w-5 h-5 animate-spin" /> : <MessageCircle className="w-5 h-5" />}
        {t("groupinvite.whatsapp", "Montar grupo por WhatsApp")}
      </button>

      <div className="flex gap-2">
        <button
          type="button"
          data-testid="group-invite-share"
          onClick={doShare}
          disabled={busy}
          className="flex-1 h-12 rounded-2xl bg-white/5 border border-white/15 text-white font-semibold flex items-center justify-center gap-2 active:scale-95 disabled:opacity-60"
        >
          <Share2 className="w-4 h-4" /> {t("groupinvite.share", "Compartir")}
        </button>
        <button
          type="button"
          data-testid="group-invite-copy"
          onClick={copyLink}
          disabled={busy}
          className="flex-1 h-12 rounded-2xl bg-white/5 border border-white/15 text-white font-semibold flex items-center justify-center gap-2 active:scale-95 disabled:opacity-60"
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
