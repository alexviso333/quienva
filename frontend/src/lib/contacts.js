// Cold-start helpers: read device contacts and share invites.
// - On the NATIVE app (Capacitor iOS/Android) we use the native Contacts plugin
//   so iPhone users CAN read their address book (the web Contact Picker API does
//   NOT exist in iOS WebView/Safari).
// - On the web we fall back to the Contact Picker API (Chromium/Android only);
//   elsewhere callers handle the "unsupported" case (invite via WhatsApp/share).

import { Capacitor } from "@capacitor/core";

// True when running inside the native app AND the Contacts plugin is available.
export function isNativeContacts() {
  try {
    return Capacitor.isNativePlatform() && Capacitor.isPluginAvailable("Contacts");
  } catch {
    return false;
  }
}

// True when the browser exposes the Contact Picker API (Chromium/Android, HTTPS).
function webPickerSupported() {
  return (
    typeof navigator !== "undefined" &&
    "contacts" in navigator &&
    typeof navigator.contacts?.select === "function" &&
    typeof window !== "undefined" &&
    "ContactsManager" in window
  );
}

// Can this device import contacts at all (native OR web picker)?
export function contactsSupported() {
  return isNativeContacts() || webPickerSupported();
}

// Read contacts and return { phones: [raw...], contacts: [{ name, phones:[raw...] }] }.
// Throws Error with .code = "unsupported" | "denied" when it can't proceed.
export async function getContacts() {
  // ---- Native (iOS / Android via Capacitor) ----
  if (isNativeContacts()) {
    const { Contacts } = await import("@capacitor-community/contacts");
    const perm = await Contacts.requestPermissions();
    if (perm?.contacts !== "granted") {
      const err = new Error("denied");
      err.code = "denied";
      throw err;
    }
    const res = await Contacts.getContacts({ projection: { name: true, phones: true } });
    const contacts = [];
    const phones = [];
    (res?.contacts || []).forEach((c) => {
      const nums = (c.phones || []).map((p) => p.number).filter(Boolean);
      if (!nums.length) return;
      const name = c.name?.display || [c.name?.given, c.name?.family].filter(Boolean).join(" ") || nums[0];
      contacts.push({ name, phones: nums });
      nums.forEach((n) => phones.push(n));
    });
    return { phones, contacts };
  }

  // ---- Web Contact Picker (Chromium / Android) ----
  if (!webPickerSupported()) {
    const err = new Error("unsupported");
    err.code = "unsupported";
    throw err;
  }
  const picked = await navigator.contacts.select(["name", "tel"], { multiple: true });
  const contacts = [];
  const phones = [];
  (picked || []).forEach((c) => {
    const nums = (c.tel || []).filter(Boolean);
    if (!nums.length) return;
    const name = (c.name && c.name[0]) || nums[0];
    contacts.push({ name, phones: nums });
    nums.forEach((n) => phones.push(n));
  });
  return { phones, contacts };
}

// Backward-compatible: just the phone numbers.
export async function pickContactPhones() {
  const { phones } = await getContacts();
  return phones;
}

// Public canonical domain used for shareable / invite links so the URL is
// always the short, on-brand one (quienva.me).
const PUBLIC_BASE = "https://quienva.me";

export function inviteUrl(code) {
  return code ? `${PUBLIC_BASE}/?ref=${code}` : `${PUBLIC_BASE}/`;
}

export function inviteText(code) {
  const url = inviteUrl(code);
  const lines = [
    "¡Hola! 👋 Estoy usando *¿Quién va?* para descubrir las mejores fiestas y ver a qué van mis amigos.",
    "",
    "Móntate el finde conmigo y no te pierdas ningún plan 🎉",
  ];
  if (code) {
    lines.push("", `🎁 Entra con mi código *${code}* y los dos ganamos 100 puntos.`);
  }
  lines.push("", url);
  return lines.join("\n");
}

export function inviteWhatsApp(code) {
  window.open(`https://wa.me/?text=${encodeURIComponent(inviteText(code))}`, "_blank", "noopener,noreferrer");
}

// Invite ONE contact by opening the SMS composer pre-filled with the invite.
// iOS uses `sms:<number>&body=`, Android uses `sms:<number>?body=`.
export function inviteSms(number, code) {
  const text = inviteText(code);
  const num = (number || "").replace(/\s+/g, "");
  const isApple = typeof navigator !== "undefined" && /iphone|ipad|ipod|mac os/i.test(navigator.userAgent || "");
  const sep = isApple ? "&" : "?";
  const href = `sms:${num}${num ? sep : ""}body=${encodeURIComponent(text)}`;
  try {
    window.location.href = href;
  } catch {
    inviteWhatsApp(code);
  }
}

export async function shareInvite(code) {
  const text = inviteText(code);
  const url = inviteUrl(code);
  try {
    if (navigator.share) {
      await navigator.share({ title: "¿Quién va?", text, url });
      return "shared";
    }
    await navigator.clipboard.writeText(text);
    return "copied";
  } catch {
    return "cancelled";
  }
}
