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

## Update 2026-08-03 e — Fase 3 (UX/privacidad) + Fase 4 (rendimiento)
- **@usuario (privacidad)**: helper display_name(u)="@username". Aplicado a TODOS los serializadores de otros usuarios (búsqueda —también se quitó poder buscar por nombre real—, perfil por username, solicitudes/lista de amigos, badges/perfil, ranking, descubrir, digest, listas voy/interesa/estuve, autores de chat/DM/grupo y miembros, historias, y todos los mensajes de notificación que incrustaban el nombre). public_user (uno mismo, /auth/me) sigue devolviendo el nombre real. Admin conserva nombres reales. Frontend: AvatarCircle ignora "@" para iniciales; quitadas líneas @usuario redundantes en Friends/UserProfile/Rankings. Backend probado 40/40.
- **Campanilla (avisos de cambios)**: añadida en CompactEventCard (botón campana arriba-dcha, badge de amigos desplazado) y en EventDetail (junto a compartir), reutilizando POST/DELETE /events/{id}/follow + is_following.
- **Fecha clara (madrugada)**: helper formatPartyDate en lib/format.js — eventos con hora 00:00–05:59 se muestran en la noche a la que pertenecen (día anterior) con etiqueta "· madrugada" (p. ej. "vie 3 · 0:30 · madrugada"). Solo display, no toca fecha guardada. Aplicado en EventCard, CompactEventCard, EventDetail.
- **Aviso de ciudad (opt-in, OFF por defecto)**: user.city_change_alerts + PUT /me/city-alerts; _notify_event_audience también notifica a usuarios con opt-in de esa ciudad (cambios de precio/estado de cualquier evento). Toggle en Ajustes (Globe2, ON/OFF).
- **Rendimiento (Fase 4)**: App.js con React.lazy + Suspense (code-splitting por ruta; bundle inicial mucho menor → carga notablemente más rápida en Vercel free). Login/Feed/AuthCallback eager. Índice compuesto users(city, city_change_alerts). Sin cambios de UI ni de comportamiento.
- PENDIENTE: adaptador Xceed (el usuario ofreció capturar con Burp Suite la API autenticada de xceed → viable si el token es estático).

## Update 2026-08-03 f — Aislamiento por ciudad (cada ciudad = su propia app) + más discotecas
- **Regiones**: CITY_REGIONS agrupa cada app-city con sus sub-zonas (Palma de Mallorca = toda la isla: Magaluf, Can Picafort, Alcúdia, Calvià…). Helpers city_query_value / region_for_city.
- **Aislamiento aplicado**: feed (/events), géneros, /venues (Locales), /venues/meta/zones (zonas), y notificaciones (_notify_new_event_city + city_change_alerts) — todo por región. Un usuario de Ibiza solo ve Ibiza; Palma ve toda Mallorca (ahora también Magaluf, que antes no salía). Probado 53/53, cero fugas.
- **Directorio para todas las ciudades**: nueva sync_scraper_venues_to_directory() crea automáticamente una ficha de Local (con scraper_slug + coords) para cada club FourVenues; NO toca las fichas curadas de Mallorca (auto_generated flag). Corre en arranque y tras cada scrape.
- **Coordenadas para el mapa**: FourVenues no da geo en su API, así que se geocodificaron (Nominatim) los ~52 clubs nuevos y se hornearon en _VENUE_COORDS (por nombre). Centros de ciudad añadidos a _ZONE_COORDS como fallback. Todos los locales de todas las ciudades salen con pin en el mapa.
- **Cobertura ampliada**: 55 scrapers FourVenues auto (Mallorca 17, Ibiza 10, Madrid 14, Barcelona 9, Marbella 5) + 117 locales de directorio + ~1.700 eventos. Añadidas Florida Park (Madrid) y Luz de Gas (Barcelona).
- **AUTO-ACTUALIZACIÓN**: todos los FourVenues (55) se auto-actualizan igual que Mallorca (precio, estado de venta, fiestas nuevas + aviso). Las superclubs NO-FourVenues (Amnesia, Hï, Ushuaïa, DC10, UNVRS, Fabrik, Pacha/Shôko/Razzmatazz/Apolo BCN, Olivia Valère…) están en el directorio pero NO se auto-actualizan (necesitan adaptador por plataforma). PENDIENTE: adaptador Xceed (el usuario ofreció capturar la API con Burp Suite → viable si el token es estático/reutilizable).

## Update 2026-08-03 g — Zar guestlist (solo_lista) + estado de fixes previos
- **Zar Society (solo lista/guestlist)**: FourVenues devuelve 409 `rate_not_exist_for_event` en tickets-types porque Zar NO vende entradas, solo lista. `scrapers/fourvenues_api.py`: `_tickets` detecta el 409 y devuelve sentinel `__guestlist__`; `_pricing` lo mapea a `sale_state="solo_lista"` con price_tiers=[]. Verificado en vivo (12 eventos Zar → solo_lista, sin precio inventado) y en DB.
  - Frontend: nuevo estado `solo_lista` en SALE_STATE_META de EventCard.js y CompactEventCard.js (badge violeta "Solo lista", icono ClipboardList; se muestra aunque no haya precio). EventDetail.js: badge "📋 Solo lista / Guestlist" + botón "Apuntarme a la lista" (en vez de "Conseguir entrada"). El CTA sigue enlazando a FourVenues (apuntarse a la lista).
  - Verificado por API: GET /api/events/{zar} → sale_state=solo_lista, current_price=None.
- **Fix 00:00 → 23:59 (confirmado)**: migración idempotente ya aplicada (0 eventos scrapeados a 00:00, 428 a 23:59). Normalización en ingesta activa. NO revertir.
- **Gate de notificaciones**: se mantiene con "Sí, activar" / "No, gracias" (decisión forzada, sin skip) por defecto, según decisión del usuario.
- **ClubTickets (Ushuaïa/Hï)**: PENDIENTE. Sin cuenta de afiliado. Scraping directo bloqueado por Cloudflare (403). Vía posible: captura Burp Suite/DevTools de la API interna que llama su web (URLs, método, headers, cookies incl. Authorization/cf_clearance, y JSON de respuesta). Solo será replicable server-side como FourVenues si el token NO depende de un cf_clearance por-navegador/IP. Alternativa: Playwright headless con stealth (frágil). De momento en directorio con enlace manual.
- NOTA: usuario pidió NO gastar créditos verificando con el agente de pruebas; verificado por API/DB/compilación.


## Update 2026-08-03 h — Ushuaïa + Hï automatizados con PRECIOS (scraper Night League)
- **Descubrimiento (vía Burp del usuario)**: ClubTickets NO es scrapeable (Cloudflare JS challenge "Just a moment…", cf-mitigated: challenge; sin cf_clearance reutilizable). PERO las webs OFICIALES de Ushuaïa (theushuaiaexperience.com) y Hï (hiibiza.com) responden 200 sin challenge y son apps Nuxt que EMBEBEN todo el calendario + precios en `__NUXT_DATA__` (devalue).
- **Nuevo adaptador `nightleague`** (`scrapers/nightleague.py`): parser devalue (resuelve refs y tags ShallowReactive/Ref…). Soporta 2 formas:
  - A) `ct-availability` (Ushuaïa): feed del club entero en CUALQUIER página → residencia{slug,name,start,dates[]} → dates{date,active_tickets,tickets[{name,price}]}. Precio real (ClubTickets embebido, sin Cloudflare). URL de compra construida como `clubtickets.com/clubbing/ushuaia-ibiza/{slug}/{fecha}`.
  - B) JSON-LD schema.org `Event` (Hï): startDate + AggregateOffer(lowPrice/availability) + url de compra por fecha.
  - Descubre residencias desde la landing + `/events-calendar` (reconstruye URLs desde slugs sueltos con el prefijo detectado). Coords horneadas (Platja d'en Bossa).
- **Resultado verificado (en vivo + BD + feed API)**: Ushuaïa 56 eventos (9 residencias: ANTS, Calvin Harris, elrow, FMIF/Guetta, Martin Garrix, Swedish House Mafia, Tomorrowland+DVLM, Hugel), Hï 64 eventos (15 residencias) — TODOS con precio real (30–275€), estado de venta, cartel y enlace de compra por fecha. city="Ibiza". Feed de Ibiza pasa a 749 eventos.
- **Integración**: adapter `nightleague` en `_ALLOWED_ADAPTERS` + factory; sembrados en `_SEED_VENUES` (Ushuaïa `ushuaia-ibiza`, Hï `hi-ibiza`, adapter nightleague, city Ibiza). Se auto-actualizan cada 30 min como FourVenues (precios, agotado, fiestas nuevas + push). Migración vincula las fichas curadas del directorio a los scrapers (scraper_slug) y borra la ficha auto-generada duplicada → 1 sola ficha por club en Locales/Mapa.
- **Fix infra**: el frontend servía llamadas a `/undefined/api/...` (bundle sin REACT_APP_BACKEND_URL inyectado); reiniciado el servicio → ahora apunta a la URL correcta.
- **Xceed (PENDIENTE, decisión usuario)**: `xceed.me/es/ibiza/events` es accesible (sin challenge) y su payload Flight trae ~48 eventos, pero de venues MENORES no cubiertos (TANTRA IBIZA, 528 Ibiza, Ibiza Rocks Hotel, barcos) y SIN precio en el listado (habría que pedir cada evento). Su API `events.xceed.me/v1/events` ignora los filtros de ciudad. Aporte modesto + más frágil. A la espera de confirmar si merece la pena.

## Update 2026-08-03 i — Xceed automatizado en TODAS las ciudades CON precios (adapter `xceed`)
- Usuario confirmó: Xceed para clubs+eventos en cualquier ciudad, buenas discotecas, auto-update total, con precio.
- **Hallazgo**: las páginas de detalle de Xceed (`/es/{ciudad}/event/{slug}/{id}`) emiten **JSON-LD schema.org Event** con `startDate`, `location` (@type NightClub/MusicVenue) y `offers[]` (name, price EUR, availability). Precio real por evento.
- **Nuevo adaptador `xceed`** (`scrapers/xceed.py`): por ciudad → GET listado `/es/{slug}/events` → descubre URLs de detalle → concurrencia (6) → parsea JSON-LD de cada evento. Filtra SOLO clubs (`@type` NightClub/MusicVenue) y descarta barcos/cruceros por nombre. Convierte startDate UTC→Europe/Madrid. Precio de todas las tarifas (ordenadas), estado (a_la_venta/agotado/no_a_la_venta), imagen, geo si existe, enlace de compra Xceed. external_id `xc:{id}`.
- **Slugs de ciudad Xceed**: ibiza, madrid, barcelona, marbella, palma-de-mallorca. Sembrados 5 venues-fuente en `_SEED_VENUES` (adapter xceed, slug="" para NO crear locales basura en el directorio; el venue real se toma del `location` de cada evento).
- **Resultado verificado (BD + feed API)**: 130 eventos nuevos con precio e imagen, aislados por ciudad — Ibiza 29 (TANTRA, 528, Ibiza Rocks), Madrid 38 (Pirandello, Goya Social Club, Nazca…), Barcelona 45 (SEASEACLUB, Moog, City Hall, Jamboree, W-Noxe), Marbella 5 (Pangea Puerto Banús), Palma 13 (Selva Club…). Feed Barcelona: 30 clubs Xceed presentes, 0 fugas de otras ciudades. Sin locales "Xceed" basura en el directorio.
- **Auto-update**: los 5 venues-fuente + Ushuaïa + Hï entran en el scheduler de 30 min como el resto (precios, agotado, fiestas nuevas + push).
- **Notas/limitaciones**: (a) algunos eventos Xceed son diurnos/gratuitos (p.ej. "Good Mornings" 11:00, "GRATIS* VIERNES") — se pueden filtrar más si molesta; (b) los venues de Xceed aún NO tienen ficha de Locale/pin en el mapa (aparecen en el feed; el mapa usa el directorio). Mejora futura: crear locales dinámicos para venues Xceed usando su geo.

## Update 2026-08-03 j — Pins de Xceed en el Mapa (locales dinámicos por geo)
- Nueva `sync_xceed_venues_to_directory()` (server.py): agrupa los eventos Xceed por venue+ciudad y crea/actualiza una ficha de Locale (colección `venues`, marcador `xceed_venue: True`) con la geo embebida en los eventos, imagen y ciudad. Evita duplicar venues ya cubiertos (curados/FourVenues) comparando por nombre normalizado (`_norm_name`, sin acentos/puntuación). Se ejecuta al arranque y tras cada `run_all_scrapers` (idempotente).
- `/api/venues`: los venues `xceed_venue` reciben `upcoming_events` vía `_xceed_venue_counts()` (conteo por nombre normalizado + ciudad). `/api/venues/{id}`: para venues Xceed lista los eventos por `venue`==nombre + ciudad + fecha futura (los eventos Xceed no tienen un scraped_venue por local).
- Añadido `import unicodedata`.
- **Verificado (API)**: 31 locales Xceed creados con geo real; Barcelona 11 (City Hall, Jamboree Dance/Jazz…), Ibiza 4 (TANTRA, 528, Ibiza Rocks, Playa San Antonio), Palma 4 (Es Gremi, Sotano Club…), todos con lat/lng y `upcoming_events` correctos. Ficha TANTRA IBIZA: xceed_venue=True, geo y 10 eventos con precio. `MapPage.js` pinta un Marker por cada venue con lat/lng → los pins salen en el mapa con su badge de nº de eventos.

## Update 2026-08-03 k — Admin por ciudad + fiestas pasadas + rendimiento del feed
- **Panel admin por ciudad** (`pages/Admin.js`): selector de ciudad arriba (Mallorca/Ibiza/Madrid/Barcelona/Marbella; testids `admin-city-<valor>`) = un panel de fiestas por ciudad. Dentro, 3 subsecciones (testids `admin-tab-upcoming|momentos|past`): **Próximas** (con botón "Nueva fiesta" + form con selector de ciudad), **Momentos** (fiestas agrupadas por día, botón rayo por fila para lanzar "El Momento"), **Pasadas** (fiestas ya celebradas). Cada fila tiene botón de **stats** (`admin-stats-<id>`) que abre `AdminEventStats`.
- **Backend** `GET /api/admin/events`: nuevos params `city` (region-aware vía `city_query_value`) y `scope` (upcoming/past/all) + proyección ligera (antes devolvía los ~1700 eventos completos → mucho más rápido).
- **Auto-borrado 3 días**: `cleanup_old_events()` borra eventos (y sus interests/tickets/follows/metrics/history/album/moment_captures) con fecha < hoy-3. Se ejecuta al arranque y tras cada `run_all_scrapers` (cada 30 min). → las stats de fiestas pasadas viven 3 días y luego desaparecen; también mantiene la BD ligera.
- **Rendimiento del feed**: el backend ya iba rápido (0,25s / 700KB para 765 eventos, sin N+1). El cuello era el frontend montando cientos de tarjetas de golpe. `FeedPlans.js` ahora hace **renderizado progresivo por nº de tarjetas** (CARD_PAGE=20 iniciales + IntersectionObserver `feed-load-more` que revela más al hacer scroll) en vistas Día y Discoteca. Imágenes con `loading="lazy"`.
- **00:00→23:59**: confirmado que a nivel de datos NO hay eventos a las 00:00 (todos desplazados a 23:59 del día anterior en ingesta + migración). El usuario veía una versión vieja (no había hecho push a GitHub). Sin cambios adicionales necesarios.
- **Verificado**: testing agent (frontend) PASÓ panel admin (ciudades + subsecciones + stats) y paginación del feed. Endpoints admin por curl: Madrid 199, Ibiza 765, Barcelona 450, past filtra bien. Ajustes finales (paginación por tarjetas, DialogTitle a11y en stats, useMemo) compilan limpio.




## Update 2026-08-04 — Rendimiento (imágenes) + panel de control (fiestas)
- **Imágenes optimizadas (rendimiento)**: se cambió `mediaUrl` → `mediaThumb` (Cloudinary `f_auto,q_auto,w_,c_limit`; calidad automática ALTA, sin verse pixeladas) en tarjetas del feed (EventCard w_900, CompactEventCard w_800), avatares (AvatarCircle size*3), detalle de evento (w_1200), stories (w_1080), Feed top (w_200), Admin thumb (w_200), Memories (w_200/400), EventMoment (w_500). `mediaThumb` solo transforma URLs de res.cloudinary.com; URLs externas (scrapers) se devuelven intactas → cero riesgo. Añadido `preconnect`/`dns-prefetch` a res.cloudinary.com en index.html. Backend ya estaba optimizado (índices, GZip, sin N+1) y React Query con staleTime 5m — no se tocó.
- **Panel de control → Fiestas → "Todas las fiestas"**: el desplegable "Fiestas pasadas" (colapsable) se movió a JUSTO debajo de la barra de búsqueda (antes de la lista de próximas), para no tener que bajar hasta el final. (AdminDashboard.js)
- **Panel de control → "El Momento"**: AdminMomentPanel agrupa ahora las fiestas — "esta noche" se muestran expandidas y "Próximos días" (siguientes días) en un desplegable colapsado por defecto. "Esta noche" = noche en curso (antes de las 6:00 cuenta como la del día anterior).
- **Infra preview**: backend/.env y frontend/.env volvían a estar vacíos (borrados) → backend caía por KeyError MONGO_URL y el frontend llamaba a /undefined/api. Restaurados para el preview (MONGO_URL local, DB_NAME=quienva, REACT_APP_BACKEND_URL del preview). NO afecta a producción (Render/Vercel tienen su propio env). Admin re-sembrado: admin@quienva.app / admin123.

## Update 2026-08-04 b — Carga priorizada de "El Momento" + caché offline
- **El Momento (carga por prioridad)**: `GET /api/admin/moments` acepta `scope=tonight|later|all` (tonight = noche en curso; antes de las 06:00 Madrid cuenta como la del día anterior). AdminMomentPanel hace 2 queries: `tonight` (carga ya) y `later` (`enabled: tonightQuery.isSuccess`, arranca solo tras cargar las de hoy) + indicador "Cargando próximos días…". El badge del panel usa scope=tonight (comparte caché). Backend probado 9/9 (tonight+later==all, auth guard, campos intactos, scope desconocido→all).
- **Caché offline (últimas fiestas al instante con poca cobertura)**:
  - React Query persistido en localStorage vía `PersistQueryClientProvider` + `createSyncStoragePersister` (index.js). Solo se persisten queries de contenido (events, carousels, top-weekend, genres, event, discover, past-events, cities, stories); maxAge 24h, buster "v1", gcTime subido a 24h. Muestra las últimas fiestas al instante y refresca en 2º plano.
  - Service worker (public/service-worker.js) ampliado: network-first para navegación (fallback a shell cacheado) + stale-while-revalidate para assets hasheados; precache best-effort de index.html/manifest/icons. No cachea /api ni cross-origin (Cloudinary). Mantiene push/notificationclick.
  - AuthContext resiliente sin red: cachea `qv_user`, hidrata al instante y NO cierra sesión ante error de red (solo ante 401/403 real). Verificado: reload offline se queda en /feed con 17 fiestas y sesión intacta (antes salía en blanco / redirigía a login).
- Instaladas deps: @tanstack/react-query-persist-client@5.56.2, @tanstack/query-sync-storage-persister@5.56.2.

## Update 2026-08-05 — FIX badge/link afiliado (desfase 1 día) + clubs que llevo
- **Root cause (verificado)**: `refresh_affiliate_events` calculaba la fecha desde `dates.start` (00:00) pero NO aplicaba la normalización 00:00→día anterior 23:59 que sí hace la ingesta. La clave `(venue,date,name)` quedaba 1 día por delante del evento guardado → casi ninguna fiesta de madrugada (la mayoría) hacía match → sin badge "Mi link", sin link de afiliado, sin prioridad. Corregido replicando la misma normalización en el refresh.
- **Cobertura**: añadidos a `_SEED_VENUES` 10 clubs que el usuario lleva vía su link quienva y que no estaban sembrados (Madrid: Fitz Madrid, TIFFANY'S THE CLUB, CrisTo Social Club, Gunilla Club, Todos Santos, Teatro Magno, Shôko Madrid, PERRO NEGRO MADRID; Marbella: Funky Buddha Puerto Banús, Xcess Banús). Antes p.ej. Fitz Madrid no se scrapeaba → imposible marcarlo.
- **Verificado por API real (no agente de pruebas, por petición)**: Madrid Fitz Madrid 27 eventos → 7 con is_affiliate=true (los que lleva) y resto false; Palma amok 70 → 0 (falso positivo resuelto), Fitz Mallorca 7 marcados; top-7 del feed = afiliados (orden ya correcto). El "7 en el panel de fitz" es CORRECTO (lleva 7 de sus fiestas, no todas).
- **Frontend NO tocado**: el badge verde "Mi link" (admin-only) y el orden afiliado-primero en Día/Discotecas/Calendario ya estaban implementados.
- **PRODUCCIÓN**: es cambio de código → requiere "Save to GitHub" para desplegar a Render. El token de FourVenues en prod se lee de DB app_settings primero y luego de env FOURVENUES_GUEST_TOKEN; conviene pegar el token nuevo en el panel admin para asegurar.

## Update 2026-08-05 b — FIX paginación afiliado (700 vs 172) + auto-sembrado de clubs que llevo
- **Causa real del under-count (verificada)**: la API FourVenues devuelve un pageSize VARIABLE (~170) menor que el pedido (200). El bucle paraba con `if len(items) < 200: break` → cortaba tras la página 1 → solo ~172 de ~700 eventos (solo las próximas ~2 semanas), por eso Fitz Mallorca salía con 7 en vez de sus ~27. Ahora pagina HASTA página vacía → 700 eventos, 58 venues. Verificado: Fitz Mallorca 27/27 y Fitz Madrid 27/27 marcados (Ago 5–31).
- **Auto-sembrado dinámico** (`_auto_seed_affiliate_clubs` en refresh_affiliate_events): crea automáticamente un scraper FourVenues para cada club que llevo (por su org.slug) que esté en una ciudad soportada y que aún no scrapeemos. Se mantiene solo cada 20 min → los clubs nuevos que coja en mi link aparecen sin tocar código.
  - Clasificación de ciudad robusta: `_supported_city_for` usa solo el segmento de ciudad tras el código postal (evita trampas de nombres de calle "Calle Barcelona"/"Las Palmas") y la ciudad soportada MÁS FRECUENTE del club (bueno para promotores itinerantes). Se quitó el token ambiguo "arenal" (colisionaba Jávea "Platja de l'Arenal" con "El Arenal" de Mallorca → KANDHALA se colaba en Palma).
  - Dedup en 2 capas: por slug exacto y por subconjunto de tokens del nombre (`_names_refer_same`) → evita duplicar clubs ya scrapeados con otro slug (p.ej. "CHANGO CLUB MADRID" baila-carino-chango-club NO duplica "Chango Madrid" discoteca-chango). OJO: `_norm_name` quita espacios; para tokens se usa `_name_tokens`.
  - Marca `auto_affiliate: True` en scraped_venues.
- Los 10 seeds estáticos añadidos antes (Fitz Madrid, etc.) se mantienen para cobertura inmediata; el dedup por slug evita choques con el auto-sembrado.

## Update 2026-08-05 c — 4 mejoras afiliado (orden por precio, marco discoteca, alerta token, panel cobertura)
- **Orden por precio dentro de mis eventos**: en list_events, la ordenación es 2-tier. Tier 0 (mis eventos por mi link) ahora se ordena de MÁS CARO a más barato (precio actual desc) y luego fecha (más caro ≈ más comisión/mejor disco). Tier 1 (el resto) sigue: importancia de discoteca → featured → popularidad → fecha. El primer campo (mío=0/otros=1) garantiza que nunca se comparan tipos entre tiers. Verificado: 40→35→30…→20.
- **Marco en mis discotecas (vista Discotecas, solo admin)**: FeedPlans.js byVenue añade `mine = items.some(is_affiliate)`; la cabecera del grupo se pinta con marco/glow lima + chip "Mi link" cuando mine. Como is_affiliate es null para usuarios normales, mine siempre es false para ellos → solo lo veo yo.
- **Alerta de token caducado**: ya existía _alert_admins_token_expired (in-app + push vía create_notification, throttle 12h), disparada tras cada scrape si el token es inválido. Añadido: también se dispara desde refresh_affiliate_events al recibir 401 (detección más temprana).
- **Panel de cobertura (AdminAffiliatePanel)**: GET /api/admin/affiliate-status ahora devuelve matched_count total y, por venue, matched = nº de fiestas PRÓXIMAS que salen realmente marcadas en la app (join por nombre normalizado), además de events (las que llevo por el link). El panel muestra "marcadas/llevadas" por club y resalta en ROJO los clubs que llevo (in_app) con 0 marcadas (huecos de cobertura, p.ej. CHANGO CLUB MADRID 2/0 por nombre de org distinto). Orden: huecos primero, luego por volumen.

## Update 2026-08-05 d — FIX hueco Chango (match afiliado por alias de club aunque org difiera)
- Problema: clubs que llevo cuyo nombre de organización en quienva difiere del scrapeado (ej: "CHANGO CLUB MADRID" vs "CHANGO MADRID") no se marcaban -> huecos rojos en panel.
- Fix: _affiliate_match(ev) -> (slug, aff_venue_norm). (1) match exacto (venue,date,name); (2) fallback por (date, nombre-fiesta exacto) + _venue_alias (subconjunto de tokens distintivos, ignorando tokens de ciudad/filler _CITY_TOKENS). Nunca marca por date+name solo (evita mislabel de fiestas homónimas de otros clubs). _AFFILIATE_BY_DN indexa (date, norm_name)->[(venue_original, slug)]. affiliate-status atribuye matched al club de afiliado.
- Verificado por testing agent (8/8): Chango 6/6 (4 exacto + 2 alias 'Vacanciones'), panel CHANGO MADRID 4/4 y CHANGO CLUB MADRID 2/2, URLs afiliado OK, orden afiliado-primero por precio desc, sin falsos positivos (el evento de AMOK 05-09 'El Tardeo de Reggaeton Viejo' es match exacto legítimo, quienva sí lo lleva).

## Update 2026-08-05 e — Pack crecimiento (ya existía) verificado + config producción
- El pack (instalar PWA + compartir WhatsApp + tarjetas OG) YA estaba implementado por un desarrollo anterior: InstallPwaBanner (render en Feed.js, beforeinstallprompt + instrucciones iOS), botón compartir WhatsApp en EventCard y EventDetail, y endpoint backend GET /api/share/event/{id} que sirve HTML con OG (og:title=nombre, og:description=venue·fecha·precio, og:image=póster) y redirige a FRONTEND_URL/event/{id}. Verificado en vivo: OG correcto con póster real.
- Dominio producción del usuario (Vercel): https://quienva-vnnx.vercel.app
- FIX: index.html tenía OG con dominio preview obsoleto (events-priority-feed...) -> cambiado a https://quienva-vnnx.vercel.app; textos "Palma" generalizados ("tu ciudad", "Los planes del finde").
- CONFIG PRODUCCIÓN CRÍTICA: en Render hay que fijar FRONTEND_URL=https://quienva-vnnx.vercel.app; si no, share_event redirige al dominio del backend (Render) y los links compartidos no abren la app. En preview se fijó FRONTEND_URL al dominio del preview.
- PENDIENTE opcional (no hecho, usuario no confirmó): vista previa pública de evento al abrir link compartido sin cuenta (hoy /event/:id es protegida -> muro de login).

## Update 2026-08-05 f — SEO por ciudad + imagen para Instagram Stories
- SEO (backend, público, server-rendered): GET /api/ciudad/{slug} = página crawlable "Fiestas en {ciudad} hoy y este finde" con lista real de eventos (póster, local·fecha·precio, links a /event/{id}), OG/canonical, enlaces a otras ciudades. GET /api/sitemap.xml (portada+feed+5 ciudades) y GET /api/robots.txt. Slugs desde SUPPORTED_CITIES (+ alias palma/mallorca/eivissa/puerto-banus). Verificado: madrid 200, 60 eventos, sitemap 7 urls.
- frontend/vercel.json: añadidas rewrites para servir bajo el dominio Vercel: /fiestas/:city, /sitemap.xml, /robots.txt -> https://quienva.onrender.com/api/... (OJO: si el dominio de Render cambia, actualizar estas destinations).
- Instagram Stories (backend Pillow): GET /api/story-image/{event_id} = JPEG 1080x1920 (fondo póster difuminado+oscurecido, tarjeta del póster con esquinas redondeadas+sombra, marca ¿QUIÉN VA?, nombre, local·fecha, pill de precio, footer). Fuentes FreeSans/FreeSansBold empaquetadas en backend/assets/fonts (funcionan en Render). Verificado visualmente.
- Frontend: EventDetail botón "Stories" (icono Instagram) junto al de WhatsApp -> fetch de la imagen + navigator.share({files}) en móvil, con fallback a descarga en desktop.
- Producción: requiere FRONTEND_URL en Render y "Save to GitHub". Tras deploy: enviar sitemap en Google Search Console.

## Update 2026-08-05 g — Story image: tipografía de marca (Unbounded/Outfit) + acabado
- story_image ahora usa las fuentes de marca: Unbounded (variable, weight 800/900) para marca+título y Outfit para texto (empaquetadas en backend/assets/fonts como Unbounded.ttf/Outfit.ttf, cargadas con set_variation_by_axes).
- Marca "¿QUIÉN VA?" con degradado neón cian->magenta + sombra suave (helper gtext). Subtítulo "LOS PLANES DEL FINDE" con tracking. Póster con borde neón cian + sombra. Nombre en Unbounded 800 blanco con sombra (auto-encoge a 50 si 3 líneas). line2 Outfit, pill de precio lima, footer pill "Míralo en ¿Quién va?" con borde cian. Scrim inferior para legibilidad. Nombre: se limpian sufijos ruido (**, _, ~, |).
- Verificado visualmente: acabado mucho más pro/coherente con la marca.

## Update 2026-08-05 h — 3 estilos de imagen Stories + verificación Google
- index.html: añadida meta google-site-verification (content JmiHtiZWYlDwQ4ax4u9kWdXeciixgyShawQZJLQcFFQ).
- story_image acepta ?style=neon|full|minimal (default neon). neon=fondo póster difuminado+degradado neón+borde cian; full=póster a sangre con scrims arriba/abajo y texto abajo; minimal=fondo oscuro limpio + tarjeta con borde blanco. Verificado visualmente los 3.
- Frontend EventDetail: el botón Instagram abre un SELECTOR (overlay) con 3 miniaturas (preview vía /story-image?style=..); al tocar una se comparte/descarga ese estilo. Estados storyPicker/storyBusy. Lint OK.

## Update 2026-08-06 — FIX crash EventDetail (selector 3 estilos) + estilo Stories unificado
- **Root cause del bloqueo (P0)**: una reversión previa quedó a medias — se quitó el estado `storyPicker`/`setStoryPicker` pero el overlay JSX que lo usaba seguía en `EventDetail.js` (línea ~190) → ReferenceError → ficha del evento en blanco y botones inertes. Además el botón IG y la campana se solapaban en `right-16`.
- **Fix frontend** (`EventDetail.js`): eliminado por completo el overlay del selector de 3 estilos. El botón de Instagram ahora comparte 1 sola imagen directamente (`shareStory("neon")`) → sin generación múltiple, sin bloqueo. Recolocados los botones de cabecera (campana `right-28`, IG `right-16`, WhatsApp `right-4`) sin solaparse.
- **Estilo Stories unificado** (`server.py` `story_image`): a petición del usuario (le gusta el fondo difuminado del neón pero las letras del minimal) → estilo único = fondo póster difuminado (neon) + tipografía limpia BLANCA + borde blanco del póster (minimal). Se ignora el parámetro `?style`. Verificado por API (200, JPEG 1080x1920) y visualmente.
- Verificado: backend genera la imagen OK; frontend compila sin errores (crash resuelto). NO se usó agente de pruebas (petición del usuario).
- **Producción**: cambio de código → requiere "Save to GitHub" para desplegar a Vercel (front) + Render (back).
