//  QuienVaLiveActivityPlugin.swift
//  Capacitor plugin (APP target) that starts / updates / ends the plan Live
//  Activity and streams each activity's APNs push token back to JS so the
//  backend can update the Dynamic Island remotely.

import Foundation
import Capacitor
import ActivityKit

@objc(QuienVaLiveActivityPlugin)
public class QuienVaLiveActivityPlugin: CAPPlugin {

    private var activities: [String: Any] = [:]   // slug -> Activity<QuienVaPlanAttributes>

    @objc func isSupported(_ call: CAPPluginCall) {
        if #available(iOS 16.2, *) {
            call.resolve(["supported": ActivityAuthorizationInfo().areActivitiesEnabled])
        } else {
            call.resolve(["supported": false])
        }
    }

    @objc func startPlan(_ call: CAPPluginCall) {
        guard #available(iOS 16.2, *) else { call.resolve(["started": false]); return }
        guard ActivityAuthorizationInfo().areActivitiesEnabled else {
            call.resolve(["started": false, "reason": "disabled"]); return
        }
        let slug = call.getString("slug") ?? ""
        if slug.isEmpty { call.reject("slug required"); return }
        if activities[slug] != nil { call.resolve(["started": true, "already": true]); return }

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
            estado: call.getString("estado") ?? "abierto"
        )
        do {
            let activity = try Activity.request(
                attributes: attrs,
                content: .init(state: state, staleDate: Date().addingTimeInterval(4 * 3600)),
                pushType: .token
            )
            activities[slug] = activity
            // Stream the per-activity push token to JS (listener "planToken").
            Task {
                for await tokenData in activity.pushTokenUpdates {
                    let token = tokenData.map { String(format: "%02x", $0) }.joined()
                    self.notifyListeners("planToken", data: ["slug": slug, "token": token])
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
        guard let activity = activities[slug] as? Activity<QuienVaPlanAttributes> else {
            call.resolve(["updated": false]); return
        }
        let state = QuienVaPlanAttributes.ContentState(
            dentro: call.getInt("dentro") ?? 0,
            umbral: call.getInt("umbral") ?? 0,
            cierraEpoch: call.getDouble("cierraEpoch"),
            ganadora: call.getString("ganadora"),
            estado: call.getString("estado") ?? "abierto"
        )
        Task {
            await activity.update(.init(state: state, staleDate: Date().addingTimeInterval(4 * 3600)))
            call.resolve(["updated": true])
        }
    }

    @objc func endPlan(_ call: CAPPluginCall) {
        guard #available(iOS 16.2, *) else { call.resolve(); return }
        let slug = call.getString("slug") ?? ""
        guard let activity = activities[slug] as? Activity<QuienVaPlanAttributes> else {
            call.resolve(["ended": false]); return
        }
        activities.removeValue(forKey: slug)
        Task {
            await activity.end(nil, dismissalPolicy: .after(Date().addingTimeInterval(900)))
            call.resolve(["ended": true])
        }
    }
}
