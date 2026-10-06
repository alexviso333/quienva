//  QuienVaWidgets.swift
//  Widget extension bundle: Live Activity (lock screen + Dynamic Island) for a
//  ¿Quién va? plan. Shows the live vote: progress bar, "4/6 dentro" and the
//  countdown to the closing time.

import SwiftUI
import WidgetKit
import ActivityKit

private let qvPink = Color(red: 1.0, green: 0.0, blue: 0.33)
private let qvCyan = Color(red: 0.0, green: 0.94, blue: 1.0)
private let qvBg = Color(red: 0.04, green: 0.04, blue: 0.047)

@available(iOS 16.1, *)
private func qvProgress(_ s: QuienVaPlanAttributes.ContentState) -> Double {
    guard s.umbral > 0 else { return s.dentro > 0 ? 1 : 0 }
    return min(1, Double(s.dentro) / Double(s.umbral))
}

@available(iOS 16.1, *)
private struct QVCountdown: View {
    let epoch: Double?
    var body: some View {
        if let epoch, epoch > Date().timeIntervalSince1970 {
            Text(timerInterval: Date()...Date(timeIntervalSince1970: epoch), countsDown: true)
                .monospacedDigit()
        } else {
            Text("")
        }
    }
}

@available(iOS 16.1, *)
struct QuienVaPlanLockScreen: View {
    let attrs: QuienVaPlanAttributes
    let state: QuienVaPlanAttributes.ContentState

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            HStack(spacing: 6) {
                Text(attrs.titulo.isEmpty ? "Tu plan" : attrs.titulo)
                    .font(.system(size: 15, weight: .heavy))
                    .lineLimit(1)
                Spacer()
                if state.estado == "abierto", state.cierraEpoch != nil {
                    HStack(spacing: 3) {
                        Text("cierra en").font(.system(size: 11)).foregroundStyle(.secondary)
                        QVCountdown(epoch: state.cierraEpoch)
                            .font(.system(size: 12, weight: .bold))
                            .foregroundStyle(qvCyan)
                    }
                }
            }

            if state.estado == "abierto" {
                GeometryReader { geo in
                    ZStack(alignment: .leading) {
                        Capsule().fill(.white.opacity(0.14))
                        Capsule()
                            .fill(LinearGradient(colors: [qvPink, qvCyan], startPoint: .leading, endPoint: .trailing))
                            .frame(width: max(6, geo.size.width * qvProgress(state)))
                    }
                }
                .frame(height: 8)

                HStack {
                    Text(state.umbral > 0 ? "\(state.dentro)/\(state.umbral) dentro" : "\(state.dentro) dentro")
                        .font(.system(size: 13, weight: .bold))
                    Spacer()
                    Text(attrs.ciudad).font(.system(size: 11)).foregroundStyle(.secondary)
                }
            } else if state.estado == "cerrado" {
                Text(state.ganadora.map { "🔥 Cerrado · \($0)" } ?? "Cerrado sin suficiente gente")
                    .font(.system(size: 13, weight: .bold))
                    .foregroundStyle(qvCyan)
                Text("\(state.dentro) dentro").font(.system(size: 11)).foregroundStyle(.secondary)
            } else {
                Text("Plan cancelado").font(.system(size: 13, weight: .bold)).foregroundStyle(.secondary)
            }
        }
        .padding(14)
        .activityBackgroundTint(qvBg)
        .activitySystemActionForegroundColor(.white)
    }
}

@available(iOS 16.1, *)
struct QuienVaPlanActivityWidget: Widget {
    var body: some WidgetConfiguration {
        ActivityConfiguration(for: QuienVaPlanAttributes.self) { context in
            QuienVaPlanLockScreen(attrs: context.attributes, state: context.state)
        } dynamicIsland: { context in
            DynamicIsland {
                DynamicIslandExpandedRegion(.leading) {
                    Text(context.state.umbral > 0
                         ? "\(context.state.dentro)/\(context.state.umbral)"
                         : "\(context.state.dentro)")
                        .font(.system(size: 17, weight: .heavy))
                        .foregroundStyle(qvPink)
                }
                DynamicIslandExpandedRegion(.trailing) {
                    if context.state.estado == "abierto", context.state.cierraEpoch != nil {
                        QVCountdown(epoch: context.state.cierraEpoch)
                            .font(.system(size: 15, weight: .bold))
                            .foregroundStyle(qvCyan)
                    } else {
                        Text(context.state.estado == "cerrado" ? "Cerrado" : "—")
                            .font(.system(size: 13, weight: .bold))
                    }
                }
                DynamicIslandExpandedRegion(.center) {
                    Text(context.attributes.titulo.isEmpty ? "Tu plan" : context.attributes.titulo)
                        .font(.system(size: 13, weight: .semibold))
                        .lineLimit(1)
                }
                DynamicIslandExpandedRegion(.bottom) {
                    GeometryReader { geo in
                        ZStack(alignment: .leading) {
                            Capsule().fill(.white.opacity(0.16))
                            Capsule()
                                .fill(LinearGradient(colors: [qvPink, qvCyan], startPoint: .leading, endPoint: .trailing))
                                .frame(width: max(6, geo.size.width * qvProgress(context.state)))
                        }
                    }
                    .frame(height: 7)
                }
            } compactLeading: {
                Text(context.state.umbral > 0
                     ? "\(context.state.dentro)/\(context.state.umbral)"
                     : "\(context.state.dentro)")
                    .font(.system(size: 13, weight: .heavy))
                    .foregroundStyle(qvPink)
            } compactTrailing: {
                if context.state.estado == "abierto", context.state.cierraEpoch != nil {
                    QVCountdown(epoch: context.state.cierraEpoch)
                        .font(.system(size: 12, weight: .bold))
                        .foregroundStyle(qvCyan)
                } else {
                    Image(systemName: context.state.estado == "cerrado" ? "checkmark.circle.fill" : "moon.fill")
                        .foregroundStyle(qvCyan)
                }
            } minimal: {
                Text("\(context.state.dentro)")
                    .font(.system(size: 12, weight: .heavy))
                    .foregroundStyle(qvPink)
            }
            .widgetURL(URL(string: "quienva://plan/\(context.attributes.slug)"))
            .keylineTint(qvPink)
        }
    }
}

@main
struct QuienVaWidgetBundle: WidgetBundle {
    // La extensión solo se instala en iOS 16.2+ (IPHONEOS_DEPLOYMENT_TARGET),
    // así que no hace falta comprobar disponibilidad aquí.
    var body: some Widget {
        QuienVaPlanActivityWidget()
    }
}
