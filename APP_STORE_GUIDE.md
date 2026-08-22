# 📱 Guía para publicar “¿Quién va?” en la App Store (y Google Play)

Tu app hoy es una **PWA** (web app instalable). Apple **no acepta PWAs puras** en la App Store,
así que hay que **envolverla en un contenedor nativo** con **Capacitor** (es el estándar y ya te lo
he dejado **preparado** en el repo). El código y la config están listos; solo faltan cosas que
**obligatoriamente** requieren tu intervención (cuenta de Apple + un Mac o servicio de build en la nube).

> ✅ Ya preparado por mí (en el repo):
> - `frontend/capacitor.config.json` (appId `me.quienva.app`, nombre, colores, splash, status bar).
> - La app ya tiene iconos (`public/icons/icon-512.png`, `apple-touch-icon.png`) y `manifest.json`.
> - Esta guía paso a paso.
>
> ⚠️ Lo que TÚ necesitas conseguir (no se puede hacer desde aquí):
> - **Cuenta Apple Developer** — 99 $/año → https://developer.apple.com/programs/
> - **Un Mac con Xcode** (para iOS). Alternativa sin Mac: servicio de build en la nube
>   (**Codemagic**, **Ionic Appflow** o **EAS Build**).
> - Para Android: **cuenta Google Play Developer** — 25 $ pago único → https://play.google.com/console

---

## 1) Instalar Capacitor (una sola vez, en tu ordenador)

Desde `frontend/`:

```bash
cd frontend
yarn add @capacitor/core @capacitor/cli @capacitor/ios @capacitor/android
yarn add @capacitor/splash-screen @capacitor/status-bar @capacitor/app @capacitor/push-notifications
```

> No hace falta ejecutar `cap init`: ya existe `capacitor.config.json`.

## 2) Generar el build web y añadir plataformas

```bash
# 1. Compila la web (genera la carpeta build/)
yarn build

# 2. Añade las plataformas nativas (crea carpetas ios/ y android/)
npx cap add ios
npx cap add android

# 3. Copia el build web dentro de las apps nativas
npx cap sync
```

## 3) Iconos y splash automáticos

Coloca un icono cuadrado de **1024×1024** en `frontend/assets/icon.png` y un splash de
**2732×2732** en `frontend/assets/splash.png`, y ejecuta:

```bash
yarn add -D @capacitor/assets
npx capacitor-assets generate --iconBackgroundColor '#0A0A0C' --splashBackgroundColor '#0A0A0C'
npx cap sync
```

Esto crea todos los tamaños de icono y splash para iOS y Android.

## 4) Abrir en Xcode (iOS) y firmar

```bash
npx cap open ios
```

En Xcode:
1. Selecciona el target **App** → pestaña **Signing & Capabilities**.
2. Marca **Automatically manage signing** y elige tu **Team** (tu cuenta Apple Developer).
3. **Bundle Identifier**: `me.quienva.app` (debe coincidir con el de App Store Connect).
4. Sube la versión/compilación (Version 1.0, Build 1).
5. **Product → Archive** → **Distribute App** → **App Store Connect**.

## 5) App Store Connect (ficha de la app)

Ve a https://appstoreconnect.apple.com → **Apps → +** y rellena:
- **Nombre**: ¿Quién va?
- **Idioma principal**: Español (España)
- **Bundle ID**: `me.quienva.app`
- **Categoría**: Estilo de vida / Entretenimiento
- **Clasificación por edad**: 17+ (contenido sobre ocio nocturno / alcohol).
- **Capturas** (obligatorias): 6.7" (iPhone 15 Pro Max) y 5.5". Puedes generarlas desde el simulador.
- **Descripción, palabras clave, URL de soporte y de privacidad** (ver plantillas abajo).
- **Privacidad de la app**: declara qué datos recoges (email de Google login, ubicación de ciudad,
  fotos que suben los usuarios en “Momentos”). Marca “no se usan para rastreo”.

## 6) Android (Google Play) — opcional, en paralelo

```bash
npx cap open android
```
En Android Studio: **Build → Generate Signed Bundle/APK → Android App Bundle (.aab)**, crea un
keystore y súbelo en **Google Play Console → Crear app**.

---

## 🔔 IMPORTANTE: Notificaciones push en la app nativa

En la web usas **Web Push (VAPID)**. Dentro del contenedor nativo de iOS **eso no funciona**;
Apple exige **push nativo (APNs)**. Para que las notificaciones funcionen en la app de la App Store
hay que añadir el plugin `@capacitor/push-notifications` y registrar el token del dispositivo en tu
backend. Es un paso adicional (medio día de trabajo). **Puedo implementarlo cuando ya tengas la
cuenta Apple** (necesito la Key de APNs desde tu cuenta). Mientras tanto, la app funciona perfecta;
solo las notis push nativas quedarían pendientes.

---

## 📝 Plantillas para la ficha (rellenar/ajustar)

**Subtítulo (30 car.):** Fiestas, amigos y entradas

**Descripción:**
> ¿Quién va? es la forma más fácil de saber qué se mueve esta noche. Descubre las fiestas y
> discotecas de tu ciudad, mira a qué planes van tus amigos, consigue tus entradas al mejor precio
> y guarda los recuerdos de cada noche. Ibiza, Madrid, Barcelona, Palma y Marbella.
>
> • Descubre fiestas de esta semana y este finde
> • Mira qué amigos van y no salgas solo
> • Entradas y precios en tiempo real
> • Momentos: revive tus noches con fotos de grupo

**Palabras clave:** fiestas, discotecas, ibiza, madrid, entradas, noche, planes, amigos, eventos, marbella

**URL de soporte:** https://quienva.me
**URL de privacidad:** https://quienva.me/privacidad  (asegúrate de que exista y sea accesible)

---

## ✅ Checklist antes de enviar a revisión (Apple)
- [ ] Cuenta Apple Developer activa (99 $/año).
- [ ] Bundle ID `me.quienva.app` creado en App Store Connect.
- [ ] Iconos y splash generados (paso 3).
- [ ] La app abre y navega sin pantallas en blanco (prueba en simulador y en un iPhone real).
- [ ] Login con Google funciona dentro del contenedor (revisa dominios permitidos).
- [ ] Política de privacidad publicada y enlazada.
- [ ] Capturas de pantalla subidas (6.7" y 5.5").
- [ ] Clasificación por edad 17+.
- [ ] (Opcional recomendado) Push nativo APNs implementado.

## 💡 Consejos para “triunfar” tras el lanzamiento
1. **ASO**: usa el nombre de las ciudades en el subtítulo/keywords (mucha gente busca “fiestas Ibiza”).
2. **Lanza por ciudad**: empuja primero donde ya tienes tracción (Palma/Ibiza) y pide reseñas ahí.
3. **Pide valoraciones en el momento bueno** (justo después de que el usuario ve “Momentos” o marca “Voy”).
4. **Deep links**: comparte enlaces `quienva.me/event/...` que abran la app si está instalada.
5. **Notificaciones con criterio** (ya es opt-in): avisa de fiestas nuevas de su ciudad y de tus amigos.
