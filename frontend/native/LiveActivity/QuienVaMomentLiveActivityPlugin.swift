//  QuienVaMomentLiveActivityPlugin.swift
//  Capacitor plugin (APP target) que arranca/actualiza/termina la Live
//  Activity del "⚡ EL MOMENTO" en el dispositivo. Mismo patrón que
//  QuienVaLiveActivityPlugin para planes.

import Foundation
import Capacitor
import ActivityKit

@objc(QuienVaMomentLiveActivityPlugin)
public class QuienVaMomentLiveActivityPlugin: CAPPlugin, CAPBridgedPlugin {
    public let identifier = "QuienVaMomentLiveActivityPlugin"
    public let jsName = "QuienVaMomentLiveActivity"
    public let pluginMethods: [CAPPluginMethod] = [
        CAPPluginMethod(name: "isSupported", returnType: CAPPluginReturnPromise),
        CAPPluginMethod(name: "observeStartToken", returnType: CAPPluginReturnPromise),
        CAPPluginMethod(name: "startMoment", returnType: CAPPluginReturnPromise),
        CAPPluginMethod(name: "updateMoment", returnType: CAPPluginReturnPromise),
        CAPPluginMethod(name: "endMoment", returnType: CAPPluginReturnPromise),
    ]

    private var activities: [String: Any] = [:]   // eventId -> Activity
    private var streaming = Set<String>()          // eventIds con token ya escuchado
    private var startTokenObserved = false         // push-to-start ya enganchado

    @available(iOS 16.2, *)
    private func findActivity(_ eventId: String) -> Activity<QuienVaMomentAttributes>? {
        if let a = activities[eventId] as? Activity<QuienVaMomentAttributes> { return a }
        if let a = Activity<QuienVaMomentAttributes>.activities.first(where: { $0.attributes.eventId == eventId }) {
            activities[eventId] = a
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
    /// `QuienVaMomentAttributes` y lo emite a JS (listener "momentStartToken").
    /// JS lo sube al backend con POST /api/live-activity/start-token
    /// (kind="moment") para que el servidor pueda ARRANCAR la Live Activity /
    /// Dynamic Island de forma remota SIN que la app esté abierta.
    @objc func observeStartToken(_ call: CAPPluginCall) {
        guard #available(iOS 17.2, *) else {
            call.resolve(["observing": false, "reason": "needs iOS 17.2+"]); return
        }
        if startTokenObserved {
            call.resolve(["observing": true, "already": true]); return
        }
        startTokenObserved = true
        Task {
            for await data in Activity<QuienVaMomentAttributes>.pushToStartTokenUpdates {
                let token = data.map { String(format: "%02x", $0) }.joined()
                self.notifyListeners("momentStartToken", data: ["token": token])
            }
        }
        call.resolve(["observing": true])
    }

    @objc func startMoment(_ call: CAPPluginCall) {
        guard #available(iOS 16.2, *) else { call.resolve(["started": false]); return }
        guard ActivityAuthorizationInfo().areActivitiesEnabled else {
            call.resolve(["started": false, "reason": "disabled"]); return
        }
        let eventId = call.getString("eventId") ?? ""
        if eventId.isEmpty { call.reject("eventId required"); return }
        if let existing = findActivity(eventId) {
            if !streaming.insert(eventId).inserted {
                call.resolve(["started": true, "already": true, "activityId": existing.id]); return
            }
            Task {
                for await tokenData in existing.pushTokenUpdates {
                    let token = tokenData.map { String(format: "%02x", $0) }.joined()
                    self.notifyListeners("momentToken", data: [
                        "eventId": eventId, "token": token, "activityId": existing.id,
                    ])
                }
            }
            call.resolve(["started": true, "already": true, "activityId": existing.id]); return
        }

        let attrs = QuienVaMomentAttributes(
            eventId: eventId,
            ciudad: call.getString("ciudad") ?? ""
        )
        let state = QuienVaMomentAttributes.ContentState(
            fase: call.getString("fase") ?? "momento",
            deadlineEpoch: call.getDouble("deadlineEpoch"),
            nombreEvento: call.getString("nombreEvento") ?? "",
            subiendoAhora: call.getInt("subiendoAhora") ?? 0,
            misLikes: call.getInt("misLikes") ?? 0,
            amigosDentro: call.getInt("amigosDentro") ?? 0
        )
        do {
            // Stale date = 20 min: pasado ese tiempo iOS marca la LA como "stale"
            // (gris) si el backend no la actualiza, para que no se quede eterna.
            let activity = try Activity.request(
                attributes: attrs,
                content: .init(state: state, staleDate: Date().addingTimeInterval(20 * 60)),
                pushType: .token
            )
            activities[eventId] = activity
            streaming.insert(eventId)
            Task {
                for await tokenData in activity.pushTokenUpdates {
                    let token = tokenData.map { String(format: "%02x", $0) }.joined()
                    self.notifyListeners("momentToken", data: [
                        "eventId": eventId, "token": token, "activityId": activity.id,
                    ])
                }
            }
            call.resolve(["started": true, "activityId": activity.id])
        } catch {
            call.resolve(["started": false, "reason": error.localizedDescription])
        }
    }

    @objc func updateMoment(_ call: CAPPluginCall) {
        guard #available(iOS 16.2, *) else { call.resolve(); return }
        let eventId = call.getString("eventId") ?? ""
        guard let activity = findActivity(eventId) else {
            call.resolve(["updated": false]); return
        }
        let state = QuienVaMomentAttributes.ContentState(
            fase: call.getString("fase") ?? "momento",
            deadlineEpoch: call.getDouble("deadlineEpoch"),
            nombreEvento: call.getString("nombreEvento") ?? "",
            subiendoAhora: call.getInt("subiendoAhora") ?? 0,
            misLikes: call.getInt("misLikes") ?? 0,
            amigosDentro: call.getInt("amigosDentro") ?? 0
        )
        Task {
            await activity.update(.init(state: state, staleDate: Date().addingTimeInterval(20 * 60)))
            call.resolve(["updated": true])
        }
    }

    @objc func endMoment(_ call: CAPPluginCall) {
        guard #available(iOS 16.2, *) else { call.resolve(); return }
        let eventId = call.getString("eventId") ?? ""
        guard let activity = findActivity(eventId) else {
            call.resolve(["ended": false]); return
        }
        activities.removeValue(forKey: eventId)
        streaming.remove(eventId)
        Task {
            // Se queda 5 min en el lockscreen tras acabar y luego iOS la quita.
            await activity.end(nil, dismissalPolicy: .after(Date().addingTimeInterval(5 * 60)))
            call.resolve(["ended": true])
        }
    }
}
