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


