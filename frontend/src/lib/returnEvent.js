import api from "@/lib/api";

const KEY = "qv_return_event";

/**
 * Sprint 3 — reciprocity / WhatsApp funnel.
 *
 * When a guest arriving on a public event page triggers signup, we remember the
 * event so that right after authenticating they land back on that same event
 * (avatars now unlocked) instead of the generic feed.
 */
export function setReturnEvent(eventId) {
  if (!eventId) return;
  try {
    localStorage.setItem(KEY, eventId);
  } catch {
    /* ignore */
  }
}

/**
 * Read + clear the pending return-event. If present, attribute a signup
 * conversion to that event (fire-and-forget) and return the SPA path to
 * navigate to. Returns null when there is nothing pending.
 */
export function consumeReturnEvent() {
  let id = null;
  try {
    id = localStorage.getItem(KEY);
    if (id) localStorage.removeItem(KEY);
  } catch {
    /* ignore */
  }
  if (id) {
    api.post("/metrics/event-signup", { event_id: id }).catch(() => {});
    return `/event/${id}`;
  }
  return null;
}
