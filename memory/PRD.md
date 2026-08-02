# PRD — ¿Quién va?

## Problem statement (original)
Mobile-first PWA "¿Quién va?" for youth (16-25) in Palma de Mallorca to decide weekend plans by seeing nightlife events and, crucially, which of their friends are attending each one. The differentiator is the social layer: who of your circle is going where. Not competing on catalog size.

## User personas
- **Joven asistente**: browses the feed, marks Voy/Me interesa, adds friends, checks who's going.
- **Admin (founder)**: single admin account, manages events via admin panel.

## Architecture
- Backend: FastAPI (`/app/backend/server.py`), MongoDB (motor). Auth via unified `session_token` (httpOnly cookie + Bearer). Object storage for image uploads (Emergent objstore).
- Frontend: React 19 + react-router + react-query + framer-motion + Tailwind + shadcn/ui. Mobile-first, dark "Electric & Neon" theme (Unbounded + Outfit fonts).
- Collections: users, sessions, friendships, events, interests, notifications, files.

## Integrations
- Emergent Google OAuth (social login) + email/password (bcrypt) — coexist via session_token.
- Emergent Object Storage (event images, avatars).

## Core requirements (static)
1. Registration/profile (name, photo, city); Google + email; logout. ✅
2. Friends: search by username, requests, accept, list. ✅
3. Admin panel CRUD events (name, venue, address, date, time, image, genre, commission flag+url / more-info url). ✅
4. Feed sorted by date, filters by date (hoy/finde/semana) + genre. ✅
5. CORE: Voy / Me interesa exclusive toggle; friend avatars + aggregate text; empty state. ✅
6. Action button: Conseguir entrada (commission) / Más información. ✅
7. In-app notifications (bell) on friend "Voy" + friend requests/accepts. ✅ (weekly digest scheduler deferred)
- Privacy: interests visible only to accepted friends. ✅

## Implemented (2026-07-30 → 2026-07-31)
- Full auth (email/password + Google OAuth callback), admin seed (admin@quienva.app).
- Friends flow, events feed + filters, Voy/Me interesa core with social proof + privacy.
- Admin CRUD + image upload, avatar upload, in-app notifications with unread badge.
- Weekly digest (Fri 12:00 APScheduler + admin trigger); invite link auto-add (?add=username); Web Push (VAPID) + PWA manifest/service worker/icon.
- DENSER compact feed; Event reminders (voy few hours before + me_interesa day-of); "Estuve"/Recuerdos past-events mode; mutual friends count; WhatsApp share + deep link.
- Event Detail page /event/:id (map + directions + full friend lists); Racha de salidas (streak) on Profile; Top del finde banner.
- Historias de Anoche (ephemeral 24h stories, friends-only, upload validated image/≤8MB, viewer, delete); Modo Descubrir (genre-based recommendations, matched-first then popularity fallback).
- Verified: 70/70 backend tests pass; frontend flows 100%.

## Self-hosting note (future)
App is env-driven and portable. To host fully independent of Emergent later, replace only: (1) object storage (integrations.emergentagent.com) and (2) Emergent Google OAuth (auth.emergentagent.com). Email/password auth, Mongo, Web Push (self-owned VAPID) are already independent.

## Backlog / Not yet built
- P1: Weekly summary notification (Friday digest) — needs scheduler/cron.
- P1: Real push notifications (PWA push) & email notifications (user selected all three channels; only in-app built).
- P2: Import friends from phone contacts.
- P2: Invite deep-link auto-add via ?add=username.
- P2: PWA manifest/service worker for installability + offline.
- P2: Multi-city expansion.

## Next tasks
- Add PWA manifest + service worker for installability.
- Implement weekly digest (scheduled job).
- Optional push/email notification channels.

## Update 2026-08-01 — FourVenues scraper + Venue Directory
- Universal `fourvenues_api` scraper: any FourVenues club/promoter by slug → real prices, sold-out & few-left. 13 sources seeded (amok, fitz-mallorca, over-club, lunita, mar-salada, luna-palma, palma-events, velvet-club, megasport, boomerang, bcm-mallorca, tabana-mallorca, danzu). Guest token in backend/.env FOURVENUES_GUEST_TOKEN (+ editable in admin). Runs every 30 min, fires push on sale-state transitions + price up/down.
- Venue Directory (`venues` collection, 27 locales incl. pueblos): public /api/venues + admin CRUD; frontend /locales page with open-days, maps, instagram, and per-venue upcoming events. Non-FourVenues venues (Banana, Milano, free pubs) added as manual directory entries.
- NOTE: backend/.env + frontend/.env had been wiped; restored (DB_NAME=quienva, admin re-seeded, VAPID regenerated).

## Update 2026-08-02 — Álbum privado, El Momento doble (BeReal), notis obligatorias, fix lag
- **Álbum ahora es PRIVADO por defecto**: cada foto/vídeo solo lo ve el autor hasta que lo comparte. Nuevo compartir selectivo por foto con amigos concretos, grupos, o "todos mis amigos" (POST /events/:id/album/:uid/share, /unshare; GET devuelve buckets `mine` + `shared`). Fix: borrar solo el dueño (403 a terceros). Notif `album_shared` a nuevos destinatarios.
- **El Momento**: nueva pantalla dedicada `/momento` con captura estilo BeReal — UN toque captura cámara trasera + frontal (secuencial ~0.7s) y las compone en una sola imagen (grande trasera + miniatura selfie). Fallback a subir foto si la cámara está bloqueada.
- **Gate del Momento** (`MomentGate`, global): nuevo endpoint GET /api/me/active-moment. Si tienes un momento pendiente (evento con interés + prompt no expirado + sin capturar) sale un modal bloqueante al abrir la app; "Ahora no" deja una píldora pequeña en el feed "Hacer tu Momento ahora". FOMO: la galería de otros sigue oculta hasta que subes la tuya; se muestra cuántos amigos ya subieron.
- **Notificaciones obligatorias**: PushPermissionGate ahora insiste hasta que se conceden (solo escape si el navegador las bloquea). Se persiste `qv_push_granted_{uid}`.
- **Feed**: eliminados los filtros "Todos" y "Descubrir"; por defecto "Este finde". Toggle Voy/Me interesa ahora OPTIMISTA (sin lag) en Feed y EventDetail.
- Notificaciones de moment_prompt/moment/moment_friend enrutan a /momento.
- NOTA: .env (backend+frontend) borrados otra vez y restaurados en dev (DB quienva re-seed, admin admin@quienva.app/admin123, VAPID regenerado, Google+FourVenues vacíos).
- Backend: 65/65 tests OK (álbum sharing matrix, active-moment lifecycle, regresión).
