// Cold-start helpers: read device contacts (where the browser allows it) and
// share invites. The Contact Picker API only exists on Chromium/Android over
// HTTPS; iOS Safari does NOT support it, so callers must handle the fallback.

export function contactsSupported() {
  return (
    typeof navigator !== "undefined" &&
    "contacts" in navigator &&
    typeof navigator.contacts?.select === "function" &&
    typeof window !== "undefined" &&
    "ContactsManager" in window
  );
}

export async function pickContactPhones() {
  if (!contactsSupported()) {
    const err = new Error("unsupported");
    err.code = "unsupported";
    throw err;
  }
  const contacts = await navigator.contacts.select(["tel"], { multiple: true });
  const phones = [];
  (contacts || []).forEach((c) => (c.tel || []).forEach((t) => t && phones.push(t)));
  return phones;
}

export function inviteUrl(code) {
  const origin = typeof window !== "undefined" ? window.location.origin : "";
  return code ? `${origin}/login?ref=${code}` : `${origin}/login`;
}

export function inviteText(code) {
  const url = inviteUrl(code);
  return `Únete a mí en ¿Quién va? 🎉 Descubre las fiestas del finde en Palma y mira a qué van tus amigos.${
    code ? ` Usa mi código ${code} y ganamos +100 pts.` : ""
  } ${url}`;
}

export function inviteWhatsApp(code) {
  window.open(`https://wa.me/?text=${encodeURIComponent(inviteText(code))}`, "_blank", "noopener,noreferrer");
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
