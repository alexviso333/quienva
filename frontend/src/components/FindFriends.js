import React, { useState, useMemo } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import api from "@/lib/api";
import { AvatarCircle } from "@/components/AvatarCircle";
import { getContacts, contactsSupported, inviteWhatsApp, shareInvite, inviteSms } from "@/lib/contacts";
import { Contact, Share2, UserPlus, Check, Loader2, Sparkles, Send } from "lucide-react";
import { toast } from "sonner";

/**
 * Cold-start friend finder: connect phone contacts (NATIVE on iPhone/Android,
 * Contact Picker on supported browsers) to find people already on ¿Quién va?,
 * invite the ones who aren't yet, plus WhatsApp / share links.
 */
export default function FindFriends() {
  const qc = useQueryClient();
  const { t } = useTranslation();
  const [matches, setMatches] = useState(null); // null = not run yet
  const [deviceContacts, setDeviceContacts] = useState([]); // [{name, phones[]}]
  const [scanning, setScanning] = useState(false);

  const { data: referral } = useQuery({
    queryKey: ["referral"],
    queryFn: async () => (await api.get("/me/referral")).data,
    staleTime: 5 * 60_000,
  });
  const code = referral?.code || "";

  const matchMut = useMutation({
    mutationFn: async (phones) => (await api.post("/me/match-contacts", { phones })).data,
    onSuccess: (data) => setMatches(data),
    onError: () => toast.error(t("findfriends.toast_match_error")),
  });

  const sendReq = useMutation({
    mutationFn: async (userId) => (await api.post("/friends/request", { user_id: userId })).data,
    onSuccess: (d, userId) => {
      toast.success(d.status === "accepted" ? t("findfriends.toast_now_friends") : t("findfriends.toast_request_sent"));
      setMatches((prev) => (prev || []).map((u) => (u.user_id === userId ? { ...u, relationship: { status: d.status === "accepted" ? "accepted" : "pending", direction: "out" } } : u)));
      qc.invalidateQueries({ queryKey: ["friends"] });
    },
    onError: (e) => toast.error(e.response?.data?.detail || t("findfriends.toast_error")),
  });

  const connectContacts = async () => {
    setScanning(true);
    try {
      const { phones, contacts } = await getContacts();
      if (!phones.length) { toast(t("findfriends.toast_no_contact_selected")); return; }
      setDeviceContacts(contacts);
      matchMut.mutate(phones);
    } catch (err) {
      if (err.code === "unsupported") {
        toast(t("findfriends.toast_unsupported"), { icon: "📵" });
      } else if (err.code === "denied") {
        toast(t("findfriends.toast_denied"), { icon: "🔒" });
      } else {
        toast(t("findfriends.toast_contacts_error"));
      }
    } finally {
      setScanning(false);
    }
  };

  const doShare = async () => {
    const res = await shareInvite(code);
    if (res === "copied") toast.success(t("findfriends.toast_link_copied"));
  };

  // Contacts NOT yet on ¿Quién va? → offer to invite them one by one.
  const toInvite = useMemo(() => {
    if (matches === null || !deviceContacts.length) return [];
    const matchedPhones = new Set((matches || []).map((u) => u.matched_phone).filter(Boolean));
    const seen = new Set();
    return deviceContacts
      .filter((c) => !c.phones.some((p) => matchedPhones.has(p)))
      .filter((c) => {
        const key = (c.phones[0] || c.name || "").trim();
        if (!key || seen.has(key)) return false;
        seen.add(key);
        return true;
      })
      .slice(0, 50);
  }, [matches, deviceContacts]);

  return (
    <section className="px-5 mt-4" data-testid="find-friends">
      <div className="rounded-2xl border border-qv-secondary/30 bg-gradient-to-br from-qv-secondary/10 via-white/[0.03] to-transparent p-4">
        <p className="flex items-center gap-2 font-display font-black text-white text-base">
          <Sparkles className="w-4 h-4 text-qv-secondary" /> {t("findfriends.title")}
        </p>
        <p className="text-white/55 text-xs mt-0.5 leading-relaxed">
          {t("findfriends.subtitle")}
        </p>

        <div className="grid grid-cols-1 gap-2 mt-3">
          <button
            data-testid="connect-contacts-btn"
            onClick={connectContacts}
            disabled={scanning || matchMut.isPending}
            className="h-12 rounded-2xl bg-qv-secondary text-black font-bold flex items-center justify-center gap-2 active:scale-95 disabled:opacity-60"
          >
            {scanning || matchMut.isPending ? <Loader2 className="w-4 h-4 animate-spin" /> : <Contact className="w-4 h-4" />} {t("findfriends.connect_contacts")}
          </button>
          <div className="grid grid-cols-2 gap-2">
            <button
              data-testid="invite-whatsapp-btn"
              onClick={() => inviteWhatsApp(code)}
              className="h-11 rounded-2xl bg-[#25D366]/15 border border-[#25D366]/40 text-[#4ee38a] font-bold text-sm flex items-center justify-center gap-2 active:scale-95"
            >
              WhatsApp
            </button>
            <button
              data-testid="invite-share-btn"
              onClick={doShare}
              className="h-11 rounded-2xl bg-white/5 border border-white/15 text-white font-bold text-sm flex items-center justify-center gap-2 active:scale-95"
            >
              <Share2 className="w-4 h-4" /> {t("findfriends.link")}
            </button>
          </div>
        </div>
        {!contactsSupported() && (
          <p className="text-white/35 text-[11px] mt-2 leading-tight">
            {t("findfriends.ios_note")}
          </p>
        )}
      </div>

      {matches !== null && (
        <div className="mt-3" data-testid="contact-matches">
          {matches.length === 0 ? (
            <p className="text-white/45 text-sm py-2">
              {t("findfriends.none_here")}
            </p>
          ) : (
            <>
              <p className="text-xs uppercase tracking-widest text-qv-secondary font-bold mb-2">
                {t("findfriends.already_here", { count: matches.length })}
              </p>
              <div className="flex flex-col gap-2">
                {matches.map((u) => {
                  const status = u.relationship?.status;
                  return (
                    <div key={u.user_id} className="flex items-center gap-3 bg-white/5 border border-white/10 rounded-2xl p-3" data-testid={`match-${u.username}`}>
                      <AvatarCircle name={u.name} picture={u.picture} size={44} ring={false} />
                      <div className="flex-1 min-w-0">
                        <p className="font-semibold truncate">{u.name}</p>
                        <p className="text-white/40 text-sm truncate">@{u.username}</p>
                      </div>
                      {status === "accepted" ? (
                        <span className="h-9 px-3 rounded-full bg-white/10 text-white/60 text-sm font-semibold flex items-center gap-1"><Check className="w-4 h-4" /> {t("findfriends.friends")}</span>
                      ) : status === "pending" ? (
                        <span className="h-9 px-3 rounded-full bg-white/10 text-white/60 text-sm font-semibold flex items-center">{t("findfriends.pending")}</span>
                      ) : (
                        <button
                          data-testid={`match-add-${u.username}`}
                          onClick={() => sendReq.mutate(u.user_id)}
                          className="h-9 px-4 rounded-full bg-qv-primary text-white text-sm font-semibold flex items-center gap-1.5 active:scale-95"
                        >
                          <UserPlus className="w-4 h-4" /> {t("findfriends.add")}
                        </button>
                      )}
                    </div>
                  );
                })}
              </div>
            </>
          )}

          {toInvite.length > 0 && (
            <div className="mt-4" data-testid="contacts-to-invite">
              <p className="text-xs uppercase tracking-widest text-white/50 font-bold mb-2">
                {t("findfriends.invite_rest_title")}
              </p>
              <div className="flex flex-col gap-2">
                {toInvite.map((c, i) => (
                  <div key={(c.phones[0] || c.name) + i} className="flex items-center gap-3 bg-white/[0.03] border border-white/10 rounded-2xl p-3" data-testid="invite-contact-row">
                    <AvatarCircle name={c.name} picture="" size={40} ring={false} />
                    <div className="flex-1 min-w-0">
                      <p className="font-semibold truncate">{c.name}</p>
                      <p className="text-white/35 text-xs truncate">{c.phones[0]}</p>
                    </div>
                    <button
                      onClick={() => inviteSms(c.phones[0], code)}
                      className="h-9 px-4 rounded-full bg-qv-secondary/20 border border-qv-secondary/40 text-qv-secondary text-sm font-semibold flex items-center gap-1.5 active:scale-95"
                    >
                      <Send className="w-4 h-4" /> {t("findfriends.invite")}
                    </button>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      )}
    </section>
  );
}
