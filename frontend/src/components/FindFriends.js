import React, { useState, useMemo } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import api from "@/lib/api";
import { AvatarCircle } from "@/components/AvatarCircle";
import { getContacts, contactsSupported, inviteWhatsApp, shareInvite, inviteWhatsAppTo } from "@/lib/contacts";
import { Contact, Share2, UserPlus, Check, Loader2, Sparkles, Send } from "lucide-react";
import { toast } from "sonner";

/**
 * Cold-start friend finder. Reads the device address book (NATIVE on iPhone/
 * Android, Contact Picker on supported browsers) and shows ONE unified list of
 * your contacts: each row clearly marks whether that person is already on
 * ¿Quién va? (tap "Añadir") or not (tap "Invitar"). Nothing is added
 * automatically — the user chooses each action, one by one.
 */
export default function FindFriends() {
  const qc = useQueryClient();
  const { t } = useTranslation();
  const [ran, setRan] = useState(false);
  const [deviceContacts, setDeviceContacts] = useState([]); // [{name, phones[]}]
  const [matches, setMatches] = useState([]);                // users found on the app
  const [scanning, setScanning] = useState(false);

  const { data: referral } = useQuery({
    queryKey: ["referral"],
    queryFn: async () => (await api.get("/me/referral")).data,
    staleTime: 5 * 60_000,
  });
  const code = referral?.code || "";

  const matchMut = useMutation({
    mutationFn: async (phones) => (await api.post("/me/match-contacts", { phones })).data,
    onSuccess: (data) => { setMatches(data || []); setRan(true); },
    onError: () => toast.error(t("findfriends.toast_match_error")),
  });

  const sendReq = useMutation({
    mutationFn: async (userId) => (await api.post("/friends/request", { user_id: userId })).data,
    onSuccess: (d, userId) => {
      toast.success(d.status === "accepted" ? t("findfriends.toast_now_friends") : t("findfriends.toast_request_sent"));
      setMatches((prev) => prev.map((u) => (u.user_id === userId ? { ...u, relationship: { status: d.status === "accepted" ? "accepted" : "pending", direction: "out" } } : u)));
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
      if (err.code === "unsupported") toast(t("findfriends.toast_unsupported"), { icon: "📵" });
      else if (err.code === "denied") toast(t("findfriends.toast_denied"), { icon: "🔒" });
      else toast(t("findfriends.toast_contacts_error"));
    } finally {
      setScanning(false);
    }
  };

  const doShare = async () => {
    const res = await shareInvite(code);
    if (res === "copied") toast.success(t("findfriends.toast_link_copied"));
  };

  // ONE unified list: every device contact + whether they're on the app.
  const { onApp, toInvite } = useMemo(() => {
    const byPhone = new Map();
    matches.forEach((u) => { if (u.matched_phone) byPhone.set(u.matched_phone, u); });
    const onA = [];
    const inv = [];
    const seen = new Set();
    deviceContacts.forEach((c) => {
      const key = (c.phones[0] || c.name || "").trim();
      if (!key || seen.has(key)) return;
      seen.add(key);
      const user = c.phones.map((p) => byPhone.get(p)).find(Boolean);
      if (user) onA.push({ ...c, user });
      else inv.push(c);
    });
    // People on the app first; among them, those you can still add before friends.
    onA.sort((a, b) => (a.user.relationship?.status === "accepted") - (b.user.relationship?.status === "accepted"));
    return { onApp: onA, toInvite: inv.slice(0, 100) };
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

        <button
          data-testid="connect-contacts-btn"
          onClick={connectContacts}
          disabled={scanning || matchMut.isPending}
          className="w-full h-12 mt-3 rounded-2xl bg-qv-secondary text-black font-bold flex items-center justify-center gap-2 active:scale-95 disabled:opacity-60"
        >
          {scanning || matchMut.isPending ? <Loader2 className="w-4 h-4 animate-spin" /> : <Contact className="w-4 h-4" />} {t("findfriends.connect_contacts")}
        </button>

        {/* Generic share (not "invite everyone") — a subtle secondary option. */}
        <div className="grid grid-cols-2 gap-2 mt-2">
          <button data-testid="invite-whatsapp-btn" onClick={() => inviteWhatsApp(code)} className="h-10 rounded-xl bg-[#25D366]/12 border border-[#25D366]/30 text-[#4ee38a] font-semibold text-xs flex items-center justify-center gap-1.5 active:scale-95">WhatsApp</button>
          <button data-testid="invite-share-btn" onClick={doShare} className="h-10 rounded-xl bg-white/5 border border-white/12 text-white/80 font-semibold text-xs flex items-center justify-center gap-1.5 active:scale-95"><Share2 className="w-3.5 h-3.5" /> {t("findfriends.link")}</button>
        </div>

        {!contactsSupported() && (
          <p className="text-white/35 text-[11px] mt-2 leading-tight">{t("findfriends.ios_note")}</p>
        )}
      </div>

      {ran && (
        <div className="mt-4" data-testid="contact-list">
          {onApp.length === 0 && toInvite.length === 0 && (
            <p className="text-white/45 text-sm py-2">{t("findfriends.none_here")}</p>
          )}

          {/* --- Already on ¿Quién va? (you choose who to add) --- */}
          {onApp.length > 0 && (
            <>
              <p className="text-xs uppercase tracking-widest text-qv-secondary font-bold mb-2">
                {t("findfriends.already_here", { count: onApp.length })}
              </p>
              <div className="flex flex-col gap-2 mb-4">
                {onApp.map((c) => {
                  const u = c.user;
                  const status = u.relationship?.status;
                  return (
                    <div key={u.user_id} className="flex items-center gap-3 bg-white/5 border border-white/10 rounded-2xl p-3" data-testid={`match-${u.username}`}>
                      <AvatarCircle name={u.name} picture={u.picture} size={44} ring={false} />
                      <div className="flex-1 min-w-0">
                        <p className="font-semibold truncate">{c.name}</p>
                        <p className="text-qv-secondary/90 text-xs truncate">@{u.username} · {t("findfriends.on_app")}</p>
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

          {/* --- Not on the app yet (invite one by one) --- */}
          {toInvite.length > 0 && (
            <>
              <p className="text-xs uppercase tracking-widest text-white/45 font-bold mb-2">
                {t("findfriends.not_here", { count: toInvite.length })}
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
                      onClick={() => inviteWhatsAppTo(c.phones[0], code)}
                      className="h-9 px-4 rounded-full bg-[#25D366]/15 border border-[#25D366]/40 text-[#4ee38a] text-sm font-semibold flex items-center gap-1.5 active:scale-95"
                    >
                      <Send className="w-4 h-4" /> {t("findfriends.invite")}
                    </button>
                  </div>
                ))}
              </div>
            </>
          )}
        </div>
      )}
    </section>
  );
}
