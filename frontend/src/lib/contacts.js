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
  // Warm, personal, benefit-led invite — reads like a friend recommending an
  // app, not like spam. No city name (the app is multi-city).
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
