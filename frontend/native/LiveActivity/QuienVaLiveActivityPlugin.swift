//  QuienVaLiveActivityPlugin.swift
//  Capacitor plugin (APP target) that starts / updates / ends the plan Live
//  Activity and streams each activity's APNs push token back to JS so the
//  backend can update the Dynamic Island remotely.

import Foundation
import Capacitor
import ActivityKit

// Capacitor 7: los plugins locales (dentro del target App) NO se descubren solos.
// Se declaran con CAPBridgedPlugin y se registran en MainViewController.
@objc(QuienVaLiveActivityPlugin)
public class QuienVaLiveActivityPlugin: CAPPlugin, CAPBridgedPlugin {
    public let identifier = "QuienVaLiveActivityPlugin"
    public let jsName = "QuienVaLiveActivity"
    public let pluginMethods: [CAPPluginMethod] = [
        CAPPluginMethod(name: "isSupported", returnType: CAPPluginReturnPromise),
        CAPPluginMethod(name: "observeStartToken", returnType: CAPPluginReturnPromise),
        CAPPluginMethod(name: "startPlan", returnType: CAPPluginReturnPromise),
        CAPPluginMethod(name: "updatePlan", returnType: CAPPluginReturnPromise),
        CAPPluginMethod(name: "endPlan", returnType: CAPPluginReturnPromise),
    ]

    private var activities: [String: Any] = [:]   // slug -> Activity<QuienVaPlanAttributes>
    private var streaming = Set<String>()          // slugs cuyo token ya escuchamos
    private var startTokenObserved = false         // push-to-start ya enganchado

    /// Busca la actividad del plan: primero en memoria y, si la app se reinició,
    /// entre las que iOS mantiene vivas (Activity.activities).
    @available(iOS 16.2, *)
    private func findActivity(_ slug: String) -> Activity<QuienVaPlanAttributes>? {
        if let a = activities[slug] as? Activity<QuienVaPlanAttributes> { return a }
        if let a = Activity<QuienVaPlanAttributes>.activities.first(where: { $0.attributes.slug == slug }) {
            activities[slug] = a
            return a
        }
        return nil
    }

    @objc func isSupported(_ call: CAPPluginCall) {
        if #available(iOS 16.2, *) {
            call.resolve(["supported": ActivityAuthorizationInfo().areActivitiesEnabled])
        } else {
            call.resolve(["supported": false])
        }
    }

    /// Push-to-start (iOS 17.2+): escucha el token push-to-start de
    /// `QuienVaPlanAttributes` y lo emite a JS (listener "planStartToken").
    /// JS lo sube al backend con POST /api/live-activity/start-token
    /// (kind="plan_invite") para que el servidor pueda ARRANCAR la Live
    /// Activity de la invitación a plan de forma remota SIN abrir la app.
    @objc func observeStartToken(_ call: CAPPluginCall) {
        guard #available(iOS 17.2, *) else {
            call.resolve(["observing": false, "reason": "needs iOS 17.2+"]); return
        }
        if startTokenObserved {
            call.resolve(["observing": true, "already": true]); return
        }
        startTokenObserved = true
        Task {
            for await data in Activity<QuienVaPlanAttributes>.pushToStartTokenUpdates {
                let token = data.map { String(format: "%02x", $0) }.joined()
                self.notifyListeners("planStartToken", data: ["token": token])
            }
        }
        call.resolve(["observing": true])
    }

    @objc func startPlan(_ call: CAPPluginCall) {
        guard #available(iOS 16.2, *) else { call.resolve(["started": false]); return }
        guard ActivityAuthorizationInfo().areActivitiesEnabled else {
            call.resolve(["started": false, "reason": "disabled"]); return
        }
        let slug = call.getString("slug") ?? ""
        if slug.isEmpty { call.reject("slug required"); return }
        if let existing = findActivity(slug) {
            // Ya existía (p.ej. tras reiniciar la app): re-emitimos su token una vez.
            if !streaming.insert(slug).inserted {
                call.resolve(["started": true, "already": true, "activityId": existing.id]); return
            }
            Task {
                for await tokenData in existing.pushTokenUpdates {
                    let token = tokenData.map { String(format: "%02x", $0) }.joined()
                    self.notifyListeners("planToken", data: ["slug": slug, "token": token, "activityId": existing.id])
                }
            }
            call.resolve(["started": true, "already": true, "activityId": existing.id]); return
        }

        let attrs = QuienVaPlanAttributes(
            titulo: call.getString("titulo") ?? "Tu plan",
            ciudad: call.getString("ciudad") ?? "",
            slug: slug
        )
        let state = QuienVaPlanAttributes.ContentState(
            dentro: call.getInt("dentro") ?? 0,
            umbral: call.getInt("umbral") ?? 0,
            cierraEpoch: call.getDouble("cierraEpoch"),
            ganadora: call.getString("ganadora"),
            estado: call.getString("estado") ?? "abierto",
            lugar: call.getString("lugar"),
            lugarVotos: call.getInt("lugarVotos"),
            numOpciones: call.getInt("numOpciones")
        )
        do {
            let activity = try Activity.request(
                attributes: attrs,
                content: .init(state: state, staleDate: Date().addingTimeInterval(4 * 3600)),
                pushType: .token
            )
            activities[slug] = activity
            streaming.insert(slug)
            // Stream the per-activity push token to JS (listener "planToken").
            Task {
                for await tokenData in activity.pushTokenUpdates {
                    let token = tokenData.map { String(format: "%02x", $0) }.joined()
                    self.notifyListeners("planToken", data: ["slug": slug, "token": token, "activityId": activity.id])
                }
            }
            call.resolve(["started": true, "activityId": activity.id])
        } catch {
            call.resolve(["started": false, "reason": error.localizedDescription])
        }
    }

    @objc func updatePlan(_ call: CAPPluginCall) {
        guard #available(iOS 16.2, *) else { call.resolve(); return }
        let slug = call.getString("slug") ?? ""
        guard let activity = findActivity(slug) else {
            call.resolve(["updated": false]); return
        }
        let state = QuienVaPlanAttributes.ContentState(
            dentro: call.getInt("dentro") ?? 0,
            umbral: call.getInt("umbral") ?? 0,
            cierraEpoch: call.getDouble("cierraEpoch"),
            ganadora: call.getString("ganadora"),
            estado: call.getString("estado") ?? "abierto",
            lugar: call.getString("lugar"),
            lugarVotos: call.getInt("lugarVotos"),
            numOpciones: call.getInt("numOpciones"),
            cambio: call.getBool("cambio")
        )
        Task {
            if #available(iOS 16.2, *), let body = call.getString("alertBody"), !body.isEmpty {
                // Cambio de sitio ganador: alerta -> vibración + isla destacada.
                let alert = AlertConfiguration(
                    title: LocalizedStringResource(stringLiteral: call.getString("alertTitle") ?? "¡Cambio de plan!"),
                    body: LocalizedStringResource(stringLiteral: body),
                    sound: .default
                )
                await activity.update(.init(state: state, staleDate: Date().addingTimeInterval(4 * 3600)),
                                      alertConfiguration: alert)
            } else {
                await activity.update(.init(state: state, staleDate: Date().addingTimeInterval(4 * 3600)))
            }
            call.resolve(["updated": true])
        }
    }

    @objc func endPlan(_ call: CAPPluginCall) {
        guard #available(iOS 16.2, *) else { call.resolve(); return }
        let slug = call.getString("slug") ?? ""
        guard let activity = findActivity(slug) else {
            call.resolve(["ended": false]); return
        }
        activities.removeValue(forKey: slug)
        streaming.remove(slug)
        Task {
            await activity.end(nil, dismissalPolicy: .after(Date().addingTimeInterval(900)))
            call.resolve(["ended": true])
        }
    }
}
