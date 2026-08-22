# 🔗 Deep Links (para que TikTok abra la app en la fiesta) — ACTIVAR CUANDO TENGAS LA CUENTA APPLE

Esto es lo que hace que, al tocar un enlace `quienva.me/event/...` desde la bio de TikTok
(o cualquier sitio), se **abra tu app directamente en esa fiesta** si está instalada, en vez de
abrir el navegador. Es la pieza clave para convertir seguidores de TikTok en usuarios de la app.

## Qué necesito de ti para activarlo (2 datos)
1. **Apple Team ID** (10 caracteres, aparece en developer.apple.com → Membership).
2. **SHA-256 de la firma de la app Android** (lo da Google Play Console → App integrity, o
   `keytool -list -v -keystore tu.keystore`). Solo si publicas también en Android.

Con eso yo dejo los ficheros finales y añado el código del listener de deep links.

## Paso 1 — Servir los ficheros de asociación (en el dominio, vía Vercel)
Copia estos dos ficheros a `frontend/public/.well-known/` y rellena los placeholders:
- `apple-app-site-association`  (SIN extensión, se sirve como JSON) → pon tu **TEAMID**.
- `assetlinks.json` → pon tu **SHA-256** (solo Android).

Apple/Google los leerán en:
- `https://quienva.me/.well-known/apple-app-site-association`
- `https://quienva.me/.well-known/assetlinks.json`

> IMPORTANTE: deben responder **200 y JSON directo** (sin redirección). Como tu apex redirige a
> `www`, declara el Associated Domain como `applinks:www.quienva.me` **y** `applinks:quienva.me`
> para cubrir ambos, y comprueba que `/.well-known/...` NO se redirige.

## Paso 2 — Xcode (iOS): Associated Domains
En Signing & Capabilities → **+ Capability → Associated Domains** y añade:
```
applinks:quienva.me
applinks:www.quienva.me
```

## Paso 3 — Código (lo pongo yo)
Con `@capacitor/app` escuchamos `appUrlOpen` y navegamos a la ruta interna:
```js
import { App } from '@capacitor/app';
App.addListener('appUrlOpen', ({ url }) => {
  try {
    const path = new URL(url).pathname; // p.ej. /event/123 o /fiesta/123/slug
    window.location.replace(path);      // React Router abre la ficha del evento
  } catch (_) {}
});
```

## Resultado (tu embudo de TikTok)
1. En el vídeo dices: “descarga ¿Quién va? — link en bio”.
2. La bio lleva a `quienva.me/event/<fiesta-del-vídeo>`.
3. Si tienen la app → se abre **en esa fiesta**. Si no → web + banner de descarga.
4. Instalan → vuelven a **esa** fiesta (no a una home vacía) → activación mucho mayor.
