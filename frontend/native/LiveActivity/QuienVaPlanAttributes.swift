//  QuienVaPlanAttributes.swift
//  Shared between the app target and the widget extension.
//  Live Activity for a shareable plan: "4/6 dentro · gana Fitz · cierra 21:00".
//
//  The ContentState keys MUST match the JSON sent by the backend in
//  aps["content-state"] (see _plan_live_state in backend/server.py).
//  New keys are OPTIONAL on purpose: an older payload (without them) still
//  decodes, so an app build never breaks while the backend rolls out.

import Foundation
import ActivityKit

@available(iOS 16.1, *)
public struct QuienVaPlanAttributes: ActivityAttributes {
    public struct ContentState: Codable, Hashable {
        public var dentro: Int
        public var umbral: Int
        public var cierraEpoch: Double?
        public var ganadora: String?
        public var estado: String   // "abierto" | "cerrado" | "cancelado"
        /// Opción que va ganando la votación (nombre corto del sitio/fiesta).
        public var lugar: String?
        /// Votos que tiene esa opción.
        public var lugarVotos: Int?
        /// Nº total de opciones a votar (1 = no hay votación, solo asistencia).
        public var numOpciones: Int?

        public init(dentro: Int, umbral: Int, cierraEpoch: Double? = nil,
                    ganadora: String? = nil, estado: String = "abierto",
                    lugar: String? = nil, lugarVotos: Int? = nil,
                    numOpciones: Int? = nil) {
            self.dentro = dentro
            self.umbral = umbral
            self.cierraEpoch = cierraEpoch
            self.ganadora = ganadora
            self.estado = estado
            self.lugar = lugar
            self.lugarVotos = lugarVotos
            self.numOpciones = numOpciones
        }
    }

    public var titulo: String
    public var ciudad: String
    public var slug: String

    public init(titulo: String, ciudad: String, slug: String) {
        self.titulo = titulo
        self.ciudad = ciudad
        self.slug = slug
    }
}
