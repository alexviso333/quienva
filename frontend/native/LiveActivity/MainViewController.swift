//  MainViewController.swift
//  Capacitor 7 ya no descubre solos los plugins que viven dentro del target App.
//  Este controlador sustituye al CAPBridgeViewController por defecto (Codemagic
//  cambia el Main.storyboard) y registra a mano el plugin de la Live Activity.

import UIKit
import Capacitor

class MainViewController: CAPBridgeViewController {
    override open func capacitorDidLoad() {
        bridge?.registerPluginInstance(QuienVaLiveActivityPlugin())
        bridge?.registerPluginInstance(QuienVaMomentLiveActivityPlugin())
    }
}
