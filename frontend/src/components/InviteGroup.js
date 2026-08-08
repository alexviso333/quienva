import { useQuery } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import { MessageCircle, Copy, Share2 } from "lucide-react";
import api from "@/lib/api";
import { toast } from "sonner";

// Reusable "bring your group" block. Opens WhatsApp with a pre-written message
// + the user's personal referral link (quienva.me/login?ref=CODE) so inviting
// the whole group is a single tap. This is the core cold-start / density lever.
export default function InviteGroup({ className = "" }) {
  const { t } = useTranslation();
  const { data: referral } = useQuery({
    queryKey: ["referral"],
    queryFn: async () => (await api.get("/me/referral")).data,
    staleTime: 5 * 60_000,
  });

  const code = referral?.code || "";
  // Always use the short, on-brand public domain (quienva.me) — not
  // window.location.origin — so shared links stay clean even when the sender
  // is on a Vercel preview host.
  const PUBLIC_BASE = "https://quienva.me";
  const url = code ? `${PUBLIC_BASE}/?ref=${code}` : `${PUBLIC_BASE}/`;
  const message = `${t("invite.wa_message")} ${url}`;

  const openWhatsApp = () => {
    window.open(`https://wa.me/?text=${encodeURIComponent(message)}`, "_blank", "noopener,noreferrer");
  };

  const copy = async () => {
    try {
      await navigator.clipboard.writeText(url);
      toast.success(t("invite.copied"));
    } catch {
      /* ignore */
    }
  };

  const share = async () => {
    try {
      if (navigator.share) await navigator.share({ title: "Quienva", text: message, url });
      else await copy();
    } catch {
      /* user cancelled */
    }
  };

  return (
    <div className={`flex flex-col gap-3 w-full ${className}`} data-testid="invite-group">
      <button
        type="button"
        data-testid="invite-whatsapp"
        onClick={openWhatsApp}
        className="h-14 rounded-2xl bg-[#25D366] text-black font-bold text-base flex items-center justify-center gap-2 active:scale-95 transition-transform shadow-[0_0_22px_rgba(37,211,102,0.35)]"
      >
        <MessageCircle className="w-5 h-5" /> {t("invite.whatsapp")}
      </button>
      <div className="flex gap-2">
        <button
          type="button"
          data-testid="invite-share"
          onClick={share}
          className="flex-1 h-12 rounded-2xl bg-white/5 border border-white/15 text-white font-semibold flex items-center justify-center gap-2 active:scale-95"
        >
          <Share2 className="w-4 h-4" /> {t("invite.share")}
        </button>
        <button
          type="button"
          data-testid="invite-copy"
          onClick={copy}
          className="flex-1 h-12 rounded-2xl bg-white/5 border border-white/15 text-white font-semibold flex items-center justify-center gap-2 active:scale-95"
        >
          <Copy className="w-4 h-4" /> {t("invite.copy")}
        </button>
      </div>
    </div>
  );
}
