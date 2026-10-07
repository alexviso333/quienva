//  QuienVaWidgets.swift
//  Widget extension bundle: Live Activity (lock screen + Dynamic Island) for a
//  ¿Quién va? plan. Neon night aesthetic: huge live counter, glowing quorum
//  meter, the option that is winning the vote and the closing countdown.

import SwiftUI
import WidgetKit
import ActivityKit

private let qvPink = Color(red: 1.0, green: 0.0, blue: 0.33)
private let qvPinkSoft = Color(red: 1.0, green: 0.24, blue: 0.5)
private let qvCyan = Color(red: 0.0, green: 0.94, blue: 1.0)
private let qvBg = Color(red: 0.035, green: 0.027, blue: 0.055)

private let qvNeon = LinearGradient(colors: [qvPink, qvPinkSoft, qvCyan],
                                    startPoint: .leading, endPoint: .trailing)

// MARK: - helpers

@available(iOS 16.1, *)
private func qvProgress(_ s: QuienVaPlanAttributes.ContentState) -> Double {
    guard s.umbral > 0 else { return s.dentro > 0 ? 1 : 0 }
    return min(1, Double(s.dentro) / Double(s.umbral))
}

@available(iOS 16.1, *)
private func qvMissing(_ s: QuienVaPlanAttributes.ContentState) -> Int {
    guard s.umbral > 0 else { return 0 }
    return max(0, s.umbral - s.dentro)
}

@available(iOS 16.1, *)
private func qvIsOpen(_ s: QuienVaPlanAttributes.ContentState) -> Bool { s.estado == "abierto" }

/// Cuenta atrás nativa (se actualiza sin pushes). Vacía si ya pasó la hora.
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

/// Chip de cuenta atrás con borde cian.
@available(iOS 16.1, *)
private struct QVClosePill: View {
    let epoch: Double?
    var body: some View {
        HStack(spacing: 4) {
            Image(systemName: "timer")
                .font(.system(size: 9, weight: .bold))
            QVCountdown(epoch: epoch)
                .font(.system(size: 12, weight: .heavy))
        }
        .foregroundStyle(qvCyan)
        .padding(.horizontal, 8)
        .padding(.vertical, 4)
        .background(
            Capsule().fill(qvCyan.opacity(0.14))
                .overlay(Capsule().strokeBorder(qvCyan.opacity(0.45), lineWidth: 1))
        )
    }
}

/// Medidor de aforo: puntos cuando el grupo es pequeño (≤ 8), barra si no.
@available(iOS 16.1, *)
private struct QVMeter: View {
    let state: QuienVaPlanAttributes.ContentState
    var height: CGFloat = 9

    var body: some View {
        if state.umbral > 0 && state.umbral <= 8 {
            HStack(spacing: 4) {
                ForEach(0..<state.umbral, id: \.self) { i in
                    Capsule()
                        .fill(i < state.dentro
                              ? AnyShapeStyle(qvNeon)
                              : AnyShapeStyle(Color.white.opacity(0.13)))
                        .frame(height: height)
                        .shadow(color: i < state.dentro ? qvPink.opacity(0.55) : .clear,
                                radius: 4)
                }
            }
        } else {
            GeometryReader { geo in
                ZStack(alignment: .leading) {
                    Capsule().fill(.white.opacity(0.12))
                    Capsule()
                        .fill(qvNeon)
                        .frame(width: max(height, geo.size.width * qvProgress(state)))
                        .shadow(color: qvPink.opacity(0.55), radius: 5)
                }
            }
            .frame(height: height)
        }
    }
}

/// Contador grande "4/6" con el número en degradado neón.
@available(iOS 16.1, *)
private struct QVCounter: View {
    let state: QuienVaPlanAttributes.ContentState
    var size: CGFloat = 40

    var body: some View {
        HStack(alignment: .firstTextBaseline, spacing: 1) {
            Text("\(state.dentro)")
                .font(.system(size: size, weight: .black, design: .rounded))
                .foregroundStyle(qvNeon)
            if state.umbral > 0 {
                Text("/\(state.umbral)")
                    .font(.system(size: size * 0.5, weight: .heavy, design: .rounded))
                    .foregroundStyle(.white.opacity(0.4))
            }
        }
    }
}

/// Chip de la opción que va ganando ("🏆 Fitz · 3").
@available(iOS 16.1, *)
private struct QVLeadingPill: View {
    let name: String
    let votes: Int?
    let locked: Bool

    var body: some View {
        HStack(spacing: 5) {
            Image(systemName: locked ? "flame.fill" : "crown.fill")
                .font(.system(size: 9, weight: .bold))
                .foregroundStyle(locked ? qvPink : qvCyan)
            Text(name)
                .font(.system(size: 12, weight: .heavy))
                .foregroundStyle(.white)
                .lineLimit(1)
            if let votes, votes > 0 {
                Text("\(votes)")
                    .font(.system(size: 10, weight: .black))
                    .foregroundStyle(.white.opacity(0.55))
            }
        }
        .padding(.horizontal, 9)
        .padding(.vertical, 5)
        .background(
            Capsule().fill(.white.opacity(0.08))
                .overlay(Capsule().strokeBorder(.white.opacity(0.14), lineWidth: 1))
        )
    }
}

// MARK: - Lock screen / banner

@available(iOS 16.1, *)
struct QuienVaPlanLockScreen: View {
    let attrs: QuienVaPlanAttributes
    let state: QuienVaPlanAttributes.ContentState

    private var title: String { attrs.titulo.isEmpty ? "Tu plan" : attrs.titulo }

    private var statusLine: String {
        if state.estado == "cancelado" { return "Plan cancelado" }
        if state.estado == "cerrado" {
            return state.ganadora.map { "Cerrado · \($0)" } ?? "Cerrado sin aforo"
        }
        if state.umbral > 0 {
            let miss = qvMissing(state)
            return miss == 0 ? "¡Aforo completo, la noche va!" : (miss == 1 ? "Falta 1 para cerrarlo" : "Faltan \(miss) para cerrarlo")
        }
        return state.dentro == 1 ? "1 persona dentro" : "\(state.dentro) dentro"
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 10) {
            // Cabecera: marca + título + cuenta atrás
            HStack(spacing: 7) {
                Circle().fill(qvPink)
                    .frame(width: 7, height: 7)
                    .shadow(color: qvPink, radius: 5)
                Text(title)
                    .font(.system(size: 15, weight: .black))
                    .foregroundStyle(.white)
                    .lineLimit(1)
                Spacer(minLength: 6)
                if qvIsOpen(state), state.cierraEpoch != nil {
                    QVClosePill(epoch: state.cierraEpoch)
                }
            }

            if qvIsOpen(state) {
                HStack(alignment: .bottom, spacing: 10) {
                    VStack(alignment: .leading, spacing: -2) {
                        QVCounter(state: state, size: 42)
                        Text("DENTRO")
                            .font(.system(size: 9, weight: .black))
                            .tracking(1.8)
                            .foregroundStyle(.white.opacity(0.42))
                    }
                    Spacer(minLength: 4)
                    if let lugar = state.lugar, !lugar.isEmpty {
                        VStack(alignment: .trailing, spacing: 3) {
                            Text((state.numOpciones ?? 1) > 1 ? "VA GANANDO" : "DÓNDE")
                                .font(.system(size: 8, weight: .black))
                                .tracking(1.4)
                                .foregroundStyle(.white.opacity(0.35))
                            QVLeadingPill(name: lugar,
                                          votes: (state.numOpciones ?? 1) > 1 ? state.lugarVotos : nil,
                                          locked: false)
                        }
                    }
                }

                QVMeter(state: state, height: 9)

                HStack(spacing: 6) {
                    Text(statusLine)
                        .font(.system(size: 12, weight: .bold))
                        .foregroundStyle(qvMissing(state) == 0 && state.umbral > 0 ? qvCyan : .white.opacity(0.72))
                        .lineLimit(1)
                    Spacer(minLength: 4)
                    Text("Toca para votar")
                        .font(.system(size: 10, weight: .heavy))
                        .foregroundStyle(qvPink)
                }
            } else {
                HStack(alignment: .center, spacing: 10) {
                    Image(systemName: state.estado == "cerrado" ? "flame.fill" : "moon.zzz.fill")
                        .font(.system(size: 22, weight: .bold))
                        .foregroundStyle(state.estado == "cerrado" ? AnyShapeStyle(qvNeon) : AnyShapeStyle(Color.white.opacity(0.35)))
                    VStack(alignment: .leading, spacing: 2) {
                        Text(statusLine)
                            .font(.system(size: 15, weight: .black))
                            .foregroundStyle(.white)
                            .lineLimit(1)
                        Text(state.dentro == 1 ? "1 persona dentro · \(attrs.ciudad)" : "\(state.dentro) dentro · \(attrs.ciudad)")
                            .font(.system(size: 11, weight: .semibold))
                            .foregroundStyle(.white.opacity(0.45))
                            .lineLimit(1)
                    }
                    Spacer(minLength: 0)
                }
                .padding(.vertical, 2)
            }
        }
        .padding(.horizontal, 15)
        .padding(.vertical, 13)
        // Glow ambiental detrás del contenido (no afecta al alto del banner).
        .background(
            ZStack(alignment: .topLeading) {
                qvPink.opacity(0.28).blur(radius: 44)
                    .frame(width: 150, height: 150)
                    .offset(x: -56, y: -58)
                qvCyan.opacity(0.20).blur(radius: 44)
                    .frame(width: 140, height: 140)
                    .offset(x: 236, y: -34)
            }
        )
        .activityBackgroundTint(qvBg)
        .activitySystemActionForegroundColor(.white)
    }
}

// MARK: - Widget

@available(iOS 16.1, *)
struct QuienVaPlanActivityWidget: Widget {
    var body: some WidgetConfiguration {
        ActivityConfiguration(for: QuienVaPlanAttributes.self) { context in
            QuienVaPlanLockScreen(attrs: context.attributes, state: context.state)
        } dynamicIsland: { context in
            let s = context.state
            return DynamicIsland {
                DynamicIslandExpandedRegion(.leading) {
                    VStack(alignment: .leading, spacing: -1) {
                        QVCounter(state: s, size: 26)
                        Text("DENTRO")
                            .font(.system(size: 8, weight: .black))
                            .tracking(1.2)
                            .foregroundStyle(.white.opacity(0.4))
                    }
                    .padding(.leading, 2)
                }
                DynamicIslandExpandedRegion(.trailing) {
                    VStack(alignment: .trailing, spacing: 2) {
                        if qvIsOpen(s), s.cierraEpoch != nil {
                            QVCountdown(epoch: s.cierraEpoch)
                                .font(.system(size: 17, weight: .black))
                                .foregroundStyle(qvCyan)
                            Text("CIERRA")
                                .font(.system(size: 8, weight: .black))
                                .tracking(1.2)
                                .foregroundStyle(.white.opacity(0.4))
                        } else {
                            Image(systemName: s.estado == "cerrado" ? "flame.fill" : "moon.zzz.fill")
                                .font(.system(size: 18, weight: .bold))
                                .foregroundStyle(s.estado == "cerrado" ? qvPink : .white.opacity(0.4))
                        }
                    }
                    .padding(.trailing, 2)
                }
                DynamicIslandExpandedRegion(.center) {
                    VStack(spacing: 1) {
                        Text(context.attributes.titulo.isEmpty ? "Tu plan" : context.attributes.titulo)
                            .font(.system(size: 13, weight: .black))
                            .foregroundStyle(.white)
                            .lineLimit(1)
                        if let lugar = s.lugar, !lugar.isEmpty {
                            HStack(spacing: 3) {
                                Image(systemName: (s.numOpciones ?? 1) > 1 ? "crown.fill" : "mappin.and.ellipse")
                                    .font(.system(size: 8, weight: .bold))
                                    .foregroundStyle(qvCyan)
                                Text((s.numOpciones ?? 1) > 1 && (s.lugarVotos ?? 0) > 0
                                     ? "\(lugar) · \(s.lugarVotos ?? 0)"
                                     : lugar)
                                    .font(.system(size: 10, weight: .bold))
                                    .foregroundStyle(.white.opacity(0.62))
                                    .lineLimit(1)
                            }
                        }
                    }
                }
                DynamicIslandExpandedRegion(.bottom) {
                    VStack(spacing: 5) {
                        QVMeter(state: s, height: 7)
                        HStack {
                            Text(qvIsOpen(s)
                                 ? (s.umbral > 0
                                    ? (qvMissing(s) == 0 ? "¡Aforo completo!" : "Faltan \(qvMissing(s))")
                                    : "Votación abierta")
                                 : (s.ganadora ?? "Plan cerrado"))
                                .font(.system(size: 10, weight: .heavy))
                                .foregroundStyle(.white.opacity(0.55))
                                .lineLimit(1)
                            Spacer()
                            Text((s.numOpciones ?? 1) > 1 ? "\(s.numOpciones ?? 1) opciones" : context.attributes.ciudad)
                                .font(.system(size: 10, weight: .heavy))
                                .foregroundStyle(qvPink)
                                .lineLimit(1)
                        }
                    }
                    .padding(.top, 1)
                }
            } compactLeading: {
                HStack(spacing: 3) {
                    Image(systemName: "bolt.fill")
                        .font(.system(size: 10, weight: .black))
                        .foregroundStyle(qvPink)
                    Text(s.umbral > 0 ? "\(s.dentro)/\(s.umbral)" : "\(s.dentro)")
                        .font(.system(size: 13, weight: .black, design: .rounded))
                        .foregroundStyle(.white)
                }
            } compactTrailing: {
                if qvIsOpen(s), s.cierraEpoch != nil {
                    QVCountdown(epoch: s.cierraEpoch)
                        .font(.system(size: 12, weight: .black))
                        .foregroundStyle(qvCyan)
                        .frame(maxWidth: 48)
                } else {
                    Image(systemName: s.estado == "cerrado" ? "flame.fill" : "moon.zzz.fill")
                        .font(.system(size: 13, weight: .bold))
                        .foregroundStyle(s.estado == "cerrado" ? qvPink : qvCyan)
                }
            } minimal: {
                Text("\(s.dentro)")
                    .font(.system(size: 13, weight: .black, design: .rounded))
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
