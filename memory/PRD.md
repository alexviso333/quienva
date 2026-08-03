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

## Update 2026-08-02 c — Persistencia de medios (Cloudinary) + foto de grupo + feed
- **Cloudinary** integrado para almacenar fotos/vídeos fuera del disco (Render es efímero). `store_media()` sube a Cloudinary si hay claves (CLOUDINARY_URL o CLOUDINARY_CLOUD_NAME/API_KEY/API_SECRET) y devuelve secure_url; si no, fallback a disco `/api/files`. Migrados todos los uploads (eventos, avatares, historias, álbum, momentos, fotos de grupo, import-url). Frontend `mediaUrl()` ya soporta http(s) directas. requirements: cloudinary>=1.40.
- **Foto de grupo**: GET /groups/:id/photo-op (3+ miembros con 'voy' a la misma fiesta próxima), POST /groups/:id/photo (sube + publica mensaje con imagen + notifica), GET /groups/:id/photos. UI en ChatThread (CTA + visor). Mensajes de grupo ahora pueden llevar image_url.
- **Feed**: eliminada la barra de chips de fecha; navegación = selector Día/Discoteca/Calendario + géneros + filtros de venta. Racha visible arriba.
- Backend probado: 57/57 (foto grupo) + 65/65 (álbum/momento). Deploy check: PASS (único warn: N+1 en /events/discover, endpoint ya sin uso).
- PENDIENTE usuario: crear cuenta Cloudinary gratis y poner CLOUDINARY_URL en Render.

## Update 2026-08-02 d — P0 UX (demo-ready)
- MomentGate: modal bloqueante SOLO en horario de fiesta (20:00–06:00), espera a que se resuelva el permiso de notificaciones (no apila modales), y píldora movida a abajo (bottom-24) para no tapar el título "Los planes".
- Horas placeholder (23:59/00:00) ocultas en tarjetas y ficha (nuevo helper lib/format.js timeSuffix/cleanTime).
- Feed simplificado: entradas (a la venta/pocas/agotadas) + géneros colapsados tras botón "Filtros" con contador de filtros activos. Selector Día/Discoteca/Calendario visible siempre. Primera fiesta visible sin scroll.
- Verificado en pantalla (430px). Sin cambios de backend en este bloque.
- PENDIENTE (aprobado por el usuario, siguientes bloques): #7 estado "Tengo entrada" + prueba social, #10 CTA único de compra, #5A afiliación con tracking + #8 embudo con € en panel admin, #9 retargeting push, #11-13 informes de alcance para negociar con discotecas, #14 feed de actividad de amigos, #15 recap dominical, #16 verificar push real, #17 compartir IG/WhatsApp bonito, #19 nav 5 tabs, #20 limpiar /events/discover, #21 onboarding 3 pantallas, #22 skeletons/estados vacíos.

## Update 2026-08-02 f — Monetización + retención (todo el backlog aprobado)
- #5A/#6/#10: CTA "Conseguir entrada" prominente con precio; tracking de clic (/tickets/click) también en la tarjeta del feed.
- #7: estado "Tengo entrada" (POST /events/{id}/ticket) con prueba social (friends_with_ticket, total_tickets) en ficha.
- #8: panel /admin/dinero (AdminMoney.js) — embudo por evento (vistas→interés→van→clics→entradas→€) con comisión estimada (10% por defecto; 0€ hasta poner precio a eventos).
- #9: retargeting — botones "Avisar interesados" (/admin/events/{id}/notify-interested) y "Pocas entradas" (notify-low-stock).
- #11-13: informe por local (/admin/venue-report) + botón "Copiar informe para la discoteca".
- #14: muro de actividad de amigos (/me/activity) en el feed. #15: tarjeta recap semanal (/me/recap).
- #16: notificaciones se activan en la última slide del onboarding (VAPID ya configurado en dev; requiere prueba en móvil real).
- #17: compartir por WhatsApp ya existe en tarjetas/ficha (IG nativo pendiente-menor).
- #18: filtros (entradas+géneros) colapsados tras botón "Filtros". #19: barra inferior a 5 pestañas (quitado Mapa). #20: eliminado /events/discover (404).
- #21: onboarding de 3 slides mejorado (menciona El Momento, foto de grupo, entradas). #22: skeletons en carga del feed.
- Backend probado: 10/10 nuevos endpoints + regresión OK. Frontend verificado en pantalla (feed, /admin/dinero, ficha). Bug de hooks en EventDetail corregido.

## Update 2026-08-03 — Fase 1 (privacidad, bugs, UX) + Descubrir
- **Privacidad por defecto = Solo amigos**: `attendance_privacy` ahora "amigos" por defecto (registro, Google y lectura de usuarios existentes sin el campo). Ajuste sigue editable (todos/amigos/nadie).
- **Nuevo `moment_privacy`** ("amigos" por defecto | "publico"): controla si tus capturas de El Momento pueden salir en Descubrir. Editable en Ajustes. Validación 400 para valores inválidos.
- **Bug mensaje leído (fix)**: al abrir un DM (`GET /dm/{id}/messages`) ahora también se marcan como leídas las notificaciones tipo "dm" de esa persona; frontend invalida los badges. Ya no queda "pendiente".
- **Recap del lunes = semana entera**: `generate_weekend_recap` cubre lunes→domingo (antes solo vie→dom); mensaje "Recuerdo de la semana".
- **Modo compacto por defecto**: `useCompactMode` ahora compacto salvo que el usuario elija "vista completa" ("0"). Tarjeta compacta con **botón "Voy" mini** (optimista) esquina inferior derecha.
- **Notificaciones**: botón "Activar notificaciones" siempre visible en Ajustes (si el navegador no lo soporta, avisa).
- **"?" en archivo de historias (fix)**: `SafeImg` con fallback de imagen rota (evita el glifo "?" del navegador) en archivo, visor y Descubrir.
- **Descubrir** (`GET /api/discover` + página `/descubrir`, acceso desde Amigos): perfiles recomendados de tu ciudad (excluye amigos/pendientes/bloqueados/uno mismo) + feed de "El Momento" público (solo de quien activó moment_privacy=publico). Pensado para recién llegados/guiris. Cargado bajo demanda (no afecta al feed).
- NOTA: .env (backend+frontend) borrados otra vez en dev y restaurados (DB quienva, admin re-seed, VAPID regenerado). Multi-ciudad (Fase 2) aplazada a petición del usuario.
- Backend probado: 7/7 OK. Frontend compila; login verificado en pantalla.

## Update 2026-08-03 b — Descubrir v2 (filtros + likes + onboarding guiri)
- **Descubrir con filtros**: `/discover` calcula `shared_events` por persona (fiestas de ESTA semana a las que vais los dos). Toggle "Van a tus fiestas (N)" + badge "Coincidís en N". Estas personas suben arriba en el orden.
- **Likes en El Momento público**: nueva colección `capture_reactions` + `POST /api/captures/{id}/like` (toggle, notifica al autor). `/discover` incluye `likes` e `i_liked` por momento. UI: corazón con contador en rejilla y en el visor (optimista). Índices añadidos.
- **Onboarding guiri**: en el Feed, si el usuario no tiene amigos, banner "¿Nuevo por aquí?" a Descubrir + auto-abre Descubrir una vez (flag localStorage `qv_discover_seen`).
- Backend probado: 21/21 OK.
- PENDIENTE debatir con usuario: cómo surfacear fiestas GRATIS/pubs (hoy el feed solo muestra eventos scrapeados de FourVenues = de pago con comisión; los pubs están escondidos en /locales).

## Update 2026-08-03 c — Fiestas gratis/pubs + locales nuevos (aparte pero visible)
- **Sección de feed "También esta noche"** (`FeedVenuesTonight`): muestra locales del directorio abiertos HOY que NO son ticketing FourVenues (o son gratis). Va DEBAJO de las fiestas de pago (FourVenues siguen primeras = comisión intacta) pero visible, con enlace a Locales. Tarjetas con badge Gratis/Entradas → abren buy_url o Instagram o /locales.
- **Campo `buy_url`** añadido al modelo VenueInput + directorio + ficha de Locales (botón "Entradas") para locales que venden por su propia web/otra plataforma.
- **24 locales nuevos** añadidos al directorio (deduplicados, SIN bares puros; beach clubs NO incluidos a la espera de confirmación del usuario). Discotecas + pubs de Mallorca/Magaluf/Alcúdia/Playa de Palma/Cala Rajada.
- **3 scrapers FourVenues nuevos** en _SEED_VENUES: Zar Society (`zar-mallorca`), Galaxy (`galaxy-mallorca`), Panama Jack (`panama-jack-magaluf`) — slugs sacados de URLs reales de fourvenues.com; en producción scrapearán eventos como el resto. Otros (Selva, Kaelum, Stereo, Mansion) con buy_url a su web/eventbrite/ticketib. Mega-Park/Oberbayern/Night Flight/pubs = free_entry.
- Verificado: 53 locales, 17 scrapers, /venues devuelve buy_url; feed muestra la sección (8 tarjetas "hoy"), Descubrir OK, banner guiri OK.

## Update 2026-08-03 d — Fase 1 (multi-ciudad + FourVenues) + Fase 2 (WhatsApp bonito)
- **Multi-ciudad**: `SUPPORTED_CITIES` + `GET /api/cities` (público). Selector de ciudad (dropdown) en registro (Login.js) y Ajustes (Settings.js): Palma de Mallorca, Ibiza, Madrid, Barcelona, Marbella/Puerto Banús. El feed ya filtraba por `user.city`; Mallorca intacta (aislada por ciudad).
- **FourVenues automatizado en 4 ciudades nuevas**: sembradas ~36 discotecas verificadas EN VIVO contra cli-api-service (total 53 scrapers). Ibiza (Pacha, Lío, Es Paradis, Eden, Pikes, Chinois, Swag, Ibiza Rocks, Bora Bora, Cova Santa), Madrid (LuLa, Chango, Deseo/Nazca, Vandido, Green, Jowke, Kube, Teatro Kapital, Teatro Barceló, Sala Mon, Opium, Gabana, Medias Puri), Barcelona (Opium, Bling Bling, Costa Este, Downtown, Twenties, Sutton, Otto Zutz, City Hall), Marbella (Fitz, Mirage, Marina Beach Club, Opium, Tibu). Se auto-actualizan igual que Mallorca (precios, agotado, pocas, bajadas, fiestas nuevas) cada 30 min.
- **Superclubs no-FourVenues** (Amnesia, Hï, Ushuaïa, DC10, [UNVRS], Fabrik, Pacha/Shôko/Razzmatazz/Apolo/Input BCN, Olivia Valère, La Suite, Momento…) añadidas al **directorio** con `buy_url` (visibles + monetizables). Xceed NO viable ahora: su API es de partner (401) y las páginas no traen datos embebidos → requiere clave de partner.
- **Protección free tier**: `run_all_scrapers` limitado a 4 discotecas en paralelo; push "nuevo evento" suprimido en el PRIMER run de cada discoteca (evita avalancha al onboardear ciudad/club).
- **WhatsApp bonito (Fase 2)**: `GET /api/share/event/{id}` sirve HTML con Open Graph/Twitter (og:title, og:description=local·fecha·precio, og:image=cartel específico de la fiesta) + redirect a la app. Frontend comparte esta URL (API base) → tarjeta compacta y visual, no textazo. Redirect al FRONTEND vía `FRONTEND_URL` (para split Vercel+Render).
- Backend probado: 51/51 OK. Selector de ciudad verificado en pantalla.
- PENDIENTE producción usuario: en Render añadir `FRONTEND_URL=<dominio Vercel>` para que el enlace de WhatsApp abra el front correcto. (.env dev estaba borrado → restaurado: DB quienva, admin re-seed, VAPID regenerado, FOURVENUES_GUEST_TOKEN puesto.)
- APLAZADO por el usuario: Fase 3 (campanilla compacta+ficha, solo @usuario, fecha ambigua, aviso cambios ciudad opt-in) y Fase 4 (rendimiento). Pendiente futuro: adaptador Xceed si se consigue clave de partner.
