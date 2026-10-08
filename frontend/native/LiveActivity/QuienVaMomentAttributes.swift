//  QuienVaMomentAttributes.swift
//  Shared between the app target and the widget extension.
//  Live Activity del "⚡ EL MOMENTO": cuenta atrás on-time + nº de personas
//  capturando ahora + likes acumulados. Se arranca LOCALMENTE desde JS
//  (mismo patrón que QuienVaPlanAttributes) y luego el backend la actualiza
//  por APNs usando el per-activity push token.

import Foundation
import ActivityKit

@available(iOS 16.1, *)
public struct QuienVaMomentAttributes: ActivityAttributes {
    public struct ContentState: Codable, Hashable {
        /// "momento"  = cuenta atrás activa (los 2 min on-time)
        /// "capturing" = el usuario ya está subiendo su foto
        /// "captured"  = el usuario ya subió, mostramos likes
        /// "ended"     = termina y la isla se dismiss
        public var fase: String
        /// Epoch seconds del deadline on-time (+30 pts si entras antes).
        public var deadlineEpoch: Double?
        public var nombreEvento: String
        /// Nº de personas que están subiendo su Momento en vivo.
        public var subiendoAhora: Int
        /// Likes recibidos por mi Momento (fase "captured").
        public var misLikes: Int
        /// Nº de amigos que ya subieron la suya (social proof).
        public var amigosDentro: Int

        public init(
            fase: String = "momento",
            deadlineEpoch: Double? = nil,
            nombreEvento: String = "",
            subiendoAhora: Int = 0,
            misLikes: Int = 0,
            amigosDentro: Int = 0
        ) {
            self.fase = fase
            self.deadlineEpoch = deadlineEpoch
            self.nombreEvento = nombreEvento
            self.subiendoAhora = subiendoAhora
            self.misLikes = misLikes
            self.amigosDentro = amigosDentro
        }
    }

    public var eventId: String
    public var ciudad: String

    public init(eventId: String, ciudad: String = "") {
        self.eventId = eventId
        self.ciudad = ciudad
    }
}
