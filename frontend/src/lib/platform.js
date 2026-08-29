// Small helpers to tell the NATIVE app (Capacitor iOS/Android, the App Store
// build) apart from the web (quienva.me). Used to hide web-only UI (PWA install
// banner, weekly recap) inside the native app without changing the website.
import { Capacitor } from "@capacitor/core";

export function isNativeApp() {
  try {
    return Capacitor.isNativePlatform();
  } catch {
    return false;
  }
}

export function isIOSApp() {
  try {
    return Capacitor.getPlatform() === "ios";
  } catch {
    return false;
  }
}
