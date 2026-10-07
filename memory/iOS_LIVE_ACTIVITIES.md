# iOS Native — Live Activities (push-to-start, iOS 17.2+)

Para que las dos nuevas burbujas de **Dynamic Island + Lockscreen** funcionen hay que añadir código Swift en el proyecto iOS (Codemagic rebuild).

El backend ya está listo: hace `push-to-start` por APNs con `apns-push-type: liveactivity` y payload estándar `attributes-type` + `attributes` + `content-state`.

---

## 1. `MomentActivityAttributes` (el rayo "⚡ ES EL MOMENTO")

Añadir una Widget Extension nueva (o reutilizar la existente). Dentro:

```swift
import ActivityKit
import SwiftUI
import WidgetKit

struct MomentActivityAttributes: ActivityAttributes {
    public struct ContentState: Codable, Hashable {
        var phase: String          // "momento" | "ended"
        var deadline: String?      // ISO-8601 string (on_time deadline)
        var event_name: String
        var capturing_now: Int
        var my_likes: Int
    }
    var event_id: String
    var event_name: String
}
```

Widget config (SwiftUI):

```swift
struct MomentLiveActivityWidget: Widget {
    var body: some WidgetConfiguration {
        ActivityConfiguration(for: MomentActivityAttributes.self) { context in
            // Lockscreen banner
            VStack(alignment: .leading, spacing: 6) {
                HStack {
                    Image(systemName: "bolt.fill")
                        .foregroundStyle(.yellow)
                    Text("¡EL MOMENTO!").font(.headline).bold()
                    Spacer()
                    if let d = context.state.deadline, let date = ISO8601DateFormatter().date(from: d) {
                        Text(timerInterval: Date()...date, countsDown: true)
                            .monospacedDigit()
                    }
                }
                Text(context.state.event_name).font(.subheadline).foregroundStyle(.secondary)
            }
            .padding()
            .activityBackgroundTint(.black)
        } dynamicIsland: { context in
            DynamicIsland {
                DynamicIslandExpandedRegion(.leading) {
                    Image(systemName: "bolt.fill").foregroundStyle(.yellow)
                }
                DynamicIslandExpandedRegion(.trailing) {
                    if let d = context.state.deadline, let date = ISO8601DateFormatter().date(from: d) {
                        Text(timerInterval: Date()...date, countsDown: true)
                            .monospacedDigit()
                    }
                }
                DynamicIslandExpandedRegion(.bottom) {
                    Text(context.state.event_name).bold()
                }
            } compactLeading: {
                Image(systemName: "bolt.fill").foregroundStyle(.yellow)
            } compactTrailing: {
                if let d = context.state.deadline, let date = ISO8601DateFormatter().date(from: d) {
                    Text(timerInterval: Date()...date, countsDown: true)
                        .monospacedDigit()
                }
            } minimal: {
                Image(systemName: "bolt.fill").foregroundStyle(.yellow)
            }
        }
    }
}
```

**Push-to-start token upload** (al abrir la app o al login):

```swift
if #available(iOS 17.2, *) {
    Task {
        for await data in Activity<MomentActivityAttributes>.pushToStartTokenUpdates {
            let token = data.map { String(format: "%02x", $0) }.joined()
            await QuienVaAPI.registerLiveActivityStartToken(kind: "moment", token: token)
        }
    }
}
```

El backend lo recibe aquí: `POST /api/live-activity/start-token` con `{"kind":"moment","token":"<hex>"}` (requiere auth).

---

## 2. `PlanInviteActivityAttributes` (la burbuja "👥 X te invita")

Mismo patrón:

```swift
struct PlanInviteActivityAttributes: ActivityAttributes {
    public struct ContentState: Codable, Hashable {
        var phase: String          // "pending" | "voted"
        var deadline: String?
        var yes_count: Int
        var no_count: Int
        var pending_count: Int
    }
    var plan_id: String
    var plan_slug: String?
    var inviter_name: String
    var plan_title: String
}
```

Widget con un `Button(intent: PlanVoteIntent)` para que el usuario pueda hacer tap "Voy / No voy" directamente desde el lockscreen (iOS 17+ Interactive Live Activities).

**Push-to-start token upload**:

```swift
if #available(iOS 17.2, *) {
    Task {
        for await data in Activity<PlanInviteActivityAttributes>.pushToStartTokenUpdates {
            let token = data.map { String(format: "%02x", $0) }.joined()
            await QuienVaAPI.registerLiveActivityStartToken(kind: "plan_invite", token: token)
        }
    }
}
```

---

## 3. ¿Cómo probar sin esperar?

En `/admin/metricas` hay un botón nuevo **"Probar notificación EL MOMENTO (y Live Activity)"** que dispara los dos pushes al dispositivo del admin. Verás en el iPhone:

- Push suave in-app (NO ruidoso: respeta Focus/No molestar)
- Si tu app tiene subido el start-token → arranca la Live Activity en la Dynamic Island con countdown 2:00 bajando

Si `live_activities_started = 0` cuando pulses el botón, es que falta subir el `start-token` desde el paso 1 o 2 de arriba.

---

## 4. Suavizado del push

El push del Momento ya **NO** usa `interruption_level: time-sensitive`. Es un push normal, para no molestar. La urgencia visual la da ahora la Live Activity (si está disponible) + el modal in-app rediseñado.
