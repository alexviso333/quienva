# ⚠️ REGLAS DEL LINK DE AFILIADO (RRPP FourVenues + ClubTickets) — LEER ANTES DE TOCAR

> **Para cualquier IA / desarrollador que trabaje en esta app (¿Quién va? / quienva.me).**
> Estas reglas mueven DINERO REAL (comisiones del dueño). NO las cambies sin seguir
> el protocolo de verificación del final. El dueño ya perdió comisiones por cambios
> "por la cara". Respeta esto siempre.

## 1. El modelo (lo que el dueño quiere, SIEMPRE)

- **SIEMPRE que se pueda usar el link de afiliado del dueño, se usa.**
- **PERO solo en los eventos que el dueño REALMENTE lleva** (los que aparecen en su
  feed RRPP de FourVenues con slug `quienva`, o los de ClubTickets con su código `aff`).
- **NUNCA se inventan eventos.** El scraper puede traer TODOS los eventos de una
  discoteca (p. ej. Roller Club trae 28 aunque el dueño solo lleve 1) — eso está bien.
  Solo el/los eventos que el dueño lleva reciben su link; el resto mantienen su link
  directo, INTACTO (reescribirlos rompería el checkout de esos eventos).

## 2. Formato de link CORRECTO (verificado por el dueño en móvil real)

Para un evento de FourVenues que llevamos, con **código de NUESTRO feed quienva** `<CODE>`:

| Formato | URL | Resultado |
|---|---|---|
| **1 (EL BUENO ✅)** | `https://site.fourvenues.com/es/quienva/events/<CODE>` | Lleva al checkout atribuido a quienva. **ES EL QUE USAMOS.** |
| 2 (pretty sin código) | `https://www.fourvenues.com/quienva/events/<slug-evento>` | **404** ❌ — NO usar. |
| 3 (iframe) | `https://www.fourvenues.com/iframe/quienva/events/<CODE>` | Funciona y atribuye, pero abierto suelto es una "página iframe rara". Se usa solo para `fv_embed_url`. |

- `<CODE>` **DEBE** salir de NUESTRO feed quienva (`_AFFILIATE_MAP`). Los códigos de
  FourVenues son **por-microsite** (quienva y la web del club tienen códigos DISTINTOS
  para el mismo evento). Usar el código del club bajo nuestro slug apunta a OTRO evento
  (fue el bug "Jueves FITZ → Mila X Golden Room"). Nunca construyas el link con el código
  del club.
- Código relevante: `_auto_commission_url_for()` (formato 1), `_fv_embed_url()` (formato 3),
  `_affiliate_match()` (¿llevamos este evento?), `refresh_affiliate_events()` (rellena el mapa).

## 3. Por qué "aparecía Mi link pero al clicar iba al club" (bug resuelto)

- El **badge "Mi link"** y el **enlace servido** usaban lógicas distintas:
  - El badge no comprobaba frescura del feed → siempre aparecía si había match.
  - El enlace SÍ comprobaba frescura (ventana de 6h) → si el feed llevaba >6h sin
    refrescar con éxito, caía al link directo del club (sin comisión).
  - Resultado: badge decía "Mi link" pero el botón iba al club. Pasó en Sevilla.
- **Arreglos aplicados (mantener):**
  1. `_affiliate_map_is_fresh()` → ventana **24h** (antes 6h). Los códigos son estables
     días/semanas; 6h era demasiado corto y creaba huecos donde se perdía el link.
  2. `is_affiliate` (badge) ahora usa **`_served_link_is_ours(ev)`**: mira el link que
     REALMENTE se sirve. Así el badge y el botón NUNCA pueden discrepar: si por lo que sea
     un evento cae al link del club, el badge se oculta (en vez de mentir).

## 4. Overrides manuales

- `link_override` (panel admin → editar evento) **SIEMPRE gana**. Se usa para arreglar a
  mano un link roto puntual. El scraper nunca lo toca. Si apunta a `/quienva/`, el badge
  lo detecta como nuestro (correcto).

## 5. ClubTickets

- Cualquier link a `clubtickets.com` recibe `?aff=<CLUBTICKETS_AFF>` (idempotente). Un
  link de clubtickets SIN nuestro código NO es nuestro (evento que no llevamos).

## 6. PROTOCOLO antes de cambiar el formato del link (OBLIGATORIO)

1. **NO** cambies el formato del link "a ciegas". Cloudflare bloquea las peticiones de
   servidor (403), así que NO se puede verificar el destino desde el backend/scripts.
2. Pide al DUEÑO que abra el/los formatos candidatos **en su móvil** y confirme cuál lleva
   al checkout atribuido a quienva.
3. Solo entonces cambia `_auto_commission_url_for()` / `_fv_embed_url()`.
4. Verifica en producción (`GET https://quienva.onrender.com/api/events?city=<Ciudad>`) que
   `commission_url` de los eventos que llevamos empieza por `https://site.fourvenues.com/es/quienva/events/`.

## 7. Ciudades nuevas SIN actualizar la app

- La app (web y iOS nativa vía Capacitor) lee la lista de ciudades de `/api/cities` en
  tiempo real. Añadir una ciudad en el panel admin → aparece al instante en todos los
  usuarios **sin actualizar la app** (solo redeploy del backend en Render).
- Para que una discoteca de una ciudad nueva se auto-clasifique en el panel de Afiliación,
  añade sus palabras clave a `_CITY_KEYWORDS` (backend). Ej.: Sevilla ya está añadida.
