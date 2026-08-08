import json, sys, os

BASE = "/app/frontend/src/i18n/locales"

# additions[lang] = nested dict to deep-merge
def deep_merge(dst, src):
    for k, v in src.items():
        if isinstance(v, dict) and isinstance(dst.get(k), dict):
            deep_merge(dst[k], v)
        else:
            dst[k] = v

ADD = {
    "es": {
        "offline": {"banner": "Sin conexión — mostrando lo último"},
        "pwa": {
            "title": "Instala ¿Quién va? en tu móvil",
            "body": "Añádela a tu pantalla de inicio y ábrela como una app: más rápida, a pantalla completa y con avisos.",
            "how_install": "Cómo instalar",
            "install_app": "Instalar app",
            "not_now": "Ahora no",
            "close": "Cerrar",
            "ios_title": "En iPhone/iPad (Safari):",
            "ios_step1": "1. Pulsa el botón <strong>Compartir</strong>.",
            "ios_step2": "2. Elige <strong>Añadir a pantalla de inicio</strong>.",
            "ios_step3": "3. Confirma con <strong>Añadir</strong>. ¡Listo! 🎉",
            "android_title": "En Android (Chrome):",
            "android_step1": "1. Abre el menú <strong>(⋮)</strong> arriba a la derecha.",
            "android_step2": "2. Elige <strong>Instalar app</strong> o <strong>Añadir a pantalla de inicio</strong>.",
            "android_step3": "3. Confirma. ¡Listo! 🎉",
        },
        "push": {
            "title": "Activa las notificaciones",
            "body": "Actívalas para no perderte nada: te avisamos cuando salte <strong>El Momento</strong>, cuando un amigo diga que va a una fiesta o cuando salgan entradas nuevas. Puedes cambiarlo cuando quieras en Ajustes.",
            "activate": "Sí, activar",
            "hint": "Pulsa <strong>Sí, activar</strong> y elige <strong>Permitir</strong> o <strong>Bloquear</strong> en tu navegador. Podrás cambiarlo cuando quieras en Ajustes.",
            "blocked": "Tu navegador tiene las notificaciones bloqueadas. Actívalas en los ajustes del navegador para vivir la experiencia completa.",
            "continue_anyway": "Continuar de todas formas",
            "toast_activated": "Notificaciones activadas ⚡",
            "toast_error": "No se pudieron activar",
        },
        "streak": {"days": "días", "weeks": "sem", "cold": "Marca 'Voy' a un plan para empezar tu racha."},
        "nextbadge": {"about_to_unlock": "A punto de desbloquear", "pts": "{{points}} pts"},
        "badgehint": {
            "total_events_one": "Ve a {{count}} fiesta más", "total_events_other": "Ve a {{count}} fiestas más",
            "day_streak_one": "Sal {{count}} día más seguidos", "day_streak_other": "Sal {{count}} días más seguidos",
            "week_streak_one": "{{count}} semana más de fiesta", "week_streak_other": "{{count}} semanas más de fiesta",
            "weekday_count_one": "{{count}} fiesta más entre semana", "weekday_count_other": "{{count}} fiestas más entre semana",
            "sunday_count_one": "{{count}} domingo más de fiesta", "sunday_count_other": "{{count}} domingos más de fiesta",
            "friends_count_one": "Añade {{count}} amigo más", "friends_count_other": "Añade {{count}} amigos más",
            "referrals_count_one": "Invita {{count}} amigo más", "referrals_count_other": "Invita {{count}} amigos más",
            "tickets_count_one": "Compra {{count}} entrada más", "tickets_count_other": "Compra {{count}} entradas más",
            "genres_count_one": "Prueba {{count}} género nuevo", "genres_count_other": "Prueba {{count}} géneros nuevos",
            "venues_count_one": "Ve a {{count}} local nuevo", "venues_count_other": "Ve a {{count}} locales nuevos",
            "captures_count_one": "Sube {{count}} momento más", "captures_count_other": "Sube {{count}} momentos más",
            "stories_count_one": "Sube {{count}} historia más", "stories_count_other": "Sube {{count}} historias más",
            "album_uploads_one": "Sube {{count}} foto más al álbum", "album_uploads_other": "Sube {{count}} fotos más al álbum",
            "fallback_one": "{{count}} más para desbloquear", "fallback_other": "{{count}} más para desbloquear",
        },
        "teaser": {
            "going_one": "va", "going_other": "van", "see_who": "ver quién",
            "persons_one": "persona va", "persons_other": "personas van",
            "register_to_see": "Regístrate para ver quién va",
        },
        "venuestonight": {
            "title": "Otros planes esta noche",
            "subtitle": "Pubs y sitios de entrada libre abiertos hoy",
            "locales": "Locales", "free": "Gratis",
        },
        "feedextras": {
            "your_friends": "Tus amigos", "now": "ahora",
            "going": "va", "has_ticket": "tiene entrada",
            "suffix": "a <1>{{event}}</1>",
            "your_week": "Tu semana", "plans": "planes", "photos": "fotos", "friends": "amigos",
            "group_plans_one": "Tu grupo tiene <1>{{count}}</1> plan apuntado · no te quedes fuera 👀",
            "group_plans_other": "Tu grupo tiene <1>{{count}}</1> planes apuntados · no te quedes fuera 👀",
        },
    },
    "en": {
        "offline": {"banner": "Offline — showing the latest"},
        "pwa": {
            "title": "Install ¿Quién va? on your phone",
            "body": "Add it to your home screen and open it like an app: faster, full-screen and with alerts.",
            "how_install": "How to install",
            "install_app": "Install app",
            "not_now": "Not now",
            "close": "Close",
            "ios_title": "On iPhone/iPad (Safari):",
            "ios_step1": "1. Tap the <strong>Share</strong> button.",
            "ios_step2": "2. Choose <strong>Add to Home Screen</strong>.",
            "ios_step3": "3. Confirm with <strong>Add</strong>. Done! 🎉",
            "android_title": "On Android (Chrome):",
            "android_step1": "1. Open the menu <strong>(⋮)</strong> at the top right.",
            "android_step2": "2. Choose <strong>Install app</strong> or <strong>Add to Home screen</strong>.",
            "android_step3": "3. Confirm. Done! 🎉",
        },
        "push": {
            "title": "Turn on notifications",
            "body": "Turn them on so you don't miss a thing: we'll alert you when <strong>The Moment</strong> drops, when a friend says they're going to a party, or when new tickets go on sale. You can change it anytime in Settings.",
            "activate": "Yes, turn on",
            "hint": "Tap <strong>Yes, turn on</strong> and choose <strong>Allow</strong> or <strong>Block</strong> in your browser. You can change it anytime in Settings.",
            "blocked": "Your browser has notifications blocked. Turn them on in your browser settings for the full experience.",
            "continue_anyway": "Continue anyway",
            "toast_activated": "Notifications turned on ⚡",
            "toast_error": "Couldn't turn them on",
        },
        "streak": {"days": "days", "weeks": "wk", "cold": "Tap 'Going' on a plan to start your streak."},
        "nextbadge": {"about_to_unlock": "About to unlock", "pts": "{{points}} pts"},
        "badgehint": {
            "total_events_one": "Go to {{count}} more party", "total_events_other": "Go to {{count}} more parties",
            "day_streak_one": "Go out {{count}} more day in a row", "day_streak_other": "Go out {{count}} more days in a row",
            "week_streak_one": "{{count}} more week of partying", "week_streak_other": "{{count}} more weeks of partying",
            "weekday_count_one": "{{count}} more weekday party", "weekday_count_other": "{{count}} more weekday parties",
            "sunday_count_one": "{{count}} more Sunday of partying", "sunday_count_other": "{{count}} more Sundays of partying",
            "friends_count_one": "Add {{count}} more friend", "friends_count_other": "Add {{count}} more friends",
            "referrals_count_one": "Invite {{count}} more friend", "referrals_count_other": "Invite {{count}} more friends",
            "tickets_count_one": "Buy {{count}} more ticket", "tickets_count_other": "Buy {{count}} more tickets",
            "genres_count_one": "Try {{count}} new genre", "genres_count_other": "Try {{count}} new genres",
            "venues_count_one": "Go to {{count}} new venue", "venues_count_other": "Go to {{count}} new venues",
            "captures_count_one": "Upload {{count}} more moment", "captures_count_other": "Upload {{count}} more moments",
            "stories_count_one": "Upload {{count}} more story", "stories_count_other": "Upload {{count}} more stories",
            "album_uploads_one": "Upload {{count}} more photo to the album", "album_uploads_other": "Upload {{count}} more photos to the album",
            "fallback_one": "{{count}} more to unlock", "fallback_other": "{{count}} more to unlock",
        },
        "teaser": {
            "going_one": "going", "going_other": "going", "see_who": "see who",
            "persons_one": "person going", "persons_other": "people going",
            "register_to_see": "Sign up to see who's going",
        },
        "venuestonight": {
            "title": "Other plans tonight",
            "subtitle": "Pubs and free-entry spots open today",
            "locales": "Venues", "free": "Free",
        },
        "feedextras": {
            "your_friends": "Your friends", "now": "now",
            "going": "is going", "has_ticket": "has a ticket",
            "suffix": "to <1>{{event}}</1>",
            "your_week": "Your week", "plans": "plans", "photos": "photos", "friends": "friends",
            "group_plans_one": "Your group has <1>{{count}}</1> plan lined up · don't miss out 👀",
            "group_plans_other": "Your group has <1>{{count}}</1> plans lined up · don't miss out 👀",
        },
    },
    "de": {
        "offline": {"banner": "Offline — zeige das Neueste"},
        "pwa": {
            "title": "Installiere ¿Quién va? auf deinem Handy",
            "body": "Füge sie zum Startbildschirm hinzu und öffne sie wie eine App: schneller, im Vollbild und mit Hinweisen.",
            "how_install": "So installierst du",
            "install_app": "App installieren",
            "not_now": "Jetzt nicht",
            "close": "Schließen",
            "ios_title": "Auf iPhone/iPad (Safari):",
            "ios_step1": "1. Tippe auf die Schaltfläche <strong>Teilen</strong>.",
            "ios_step2": "2. Wähle <strong>Zum Home-Bildschirm</strong>.",
            "ios_step3": "3. Bestätige mit <strong>Hinzufügen</strong>. Fertig! 🎉",
            "android_title": "Auf Android (Chrome):",
            "android_step1": "1. Öffne das Menü <strong>(⋮)</strong> oben rechts.",
            "android_step2": "2. Wähle <strong>App installieren</strong> oder <strong>Zum Startbildschirm hinzufügen</strong>.",
            "android_step3": "3. Bestätige. Fertig! 🎉",
        },
        "push": {
            "title": "Benachrichtigungen aktivieren",
            "body": "Aktiviere sie, um nichts zu verpassen: Wir informieren dich, wenn <strong>Der Moment</strong> startet, wenn ein Freund zu einer Party geht oder wenn neue Tickets erscheinen. Du kannst es jederzeit in den Einstellungen ändern.",
            "activate": "Ja, aktivieren",
            "hint": "Tippe auf <strong>Ja, aktivieren</strong> und wähle <strong>Zulassen</strong> oder <strong>Blockieren</strong> in deinem Browser. Du kannst es jederzeit in den Einstellungen ändern.",
            "blocked": "Dein Browser blockiert Benachrichtigungen. Aktiviere sie in den Browsereinstellungen für das volle Erlebnis.",
            "continue_anyway": "Trotzdem fortfahren",
            "toast_activated": "Benachrichtigungen aktiviert ⚡",
            "toast_error": "Konnten nicht aktiviert werden",
        },
        "streak": {"days": "Tage", "weeks": "Wo", "cold": "Tippe bei einem Plan auf 'Ich gehe', um deine Serie zu starten."},
        "nextbadge": {"about_to_unlock": "Kurz vor dem Freischalten", "pts": "{{points}} Pkt"},
        "badgehint": {
            "total_events_one": "Geh zu {{count}} weiteren Party", "total_events_other": "Geh zu {{count}} weiteren Partys",
            "day_streak_one": "Geh {{count}} weiteren Tag in Folge aus", "day_streak_other": "Geh {{count}} weitere Tage in Folge aus",
            "week_streak_one": "{{count}} weitere Woche feiern", "week_streak_other": "{{count}} weitere Wochen feiern",
            "weekday_count_one": "{{count}} weitere Party unter der Woche", "weekday_count_other": "{{count}} weitere Partys unter der Woche",
            "sunday_count_one": "{{count}} weiteren Sonntag feiern", "sunday_count_other": "{{count}} weitere Sonntage feiern",
            "friends_count_one": "Füge {{count}} weiteren Freund hinzu", "friends_count_other": "Füge {{count}} weitere Freunde hinzu",
            "referrals_count_one": "Lade {{count}} weiteren Freund ein", "referrals_count_other": "Lade {{count}} weitere Freunde ein",
            "tickets_count_one": "Kaufe {{count}} weiteres Ticket", "tickets_count_other": "Kaufe {{count}} weitere Tickets",
            "genres_count_one": "Probiere {{count}} neues Genre", "genres_count_other": "Probiere {{count}} neue Genres",
            "venues_count_one": "Geh zu {{count}} neuen Location", "venues_count_other": "Geh zu {{count}} neuen Locations",
            "captures_count_one": "Lade {{count}} weiteren Moment hoch", "captures_count_other": "Lade {{count}} weitere Momente hoch",
            "stories_count_one": "Lade {{count}} weitere Story hoch", "stories_count_other": "Lade {{count}} weitere Storys hoch",
            "album_uploads_one": "Lade {{count}} weiteres Foto ins Album hoch", "album_uploads_other": "Lade {{count}} weitere Fotos ins Album hoch",
            "fallback_one": "Noch {{count}} zum Freischalten", "fallback_other": "Noch {{count}} zum Freischalten",
        },
        "teaser": {
            "going_one": "geht", "going_other": "gehen", "see_who": "wer geht",
            "persons_one": "Person geht", "persons_other": "Personen gehen",
            "register_to_see": "Registriere dich, um zu sehen, wer geht",
        },
        "venuestonight": {
            "title": "Weitere Pläne heute Nacht",
            "subtitle": "Pubs und Orte mit freiem Eintritt, heute geöffnet",
            "locales": "Locations", "free": "Gratis",
        },
        "feedextras": {
            "your_friends": "Deine Freunde", "now": "jetzt",
            "going": "geht", "has_ticket": "hat ein Ticket",
            "suffix": "zu <1>{{event}}</1>",
            "your_week": "Deine Woche", "plans": "Pläne", "photos": "Fotos", "friends": "Freunde",
            "group_plans_one": "Deine Gruppe hat <1>{{count}}</1> Plan eingetragen · sei dabei 👀",
            "group_plans_other": "Deine Gruppe hat <1>{{count}}</1> Pläne eingetragen · sei dabei 👀",
        },
    },
}

for lang, add in ADD.items():
    path = os.path.join(BASE, f"{lang}.json")
    data = json.load(open(path, encoding="utf-8"))
    deep_merge(data, add)
    json.dump(data, open(path, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    print(lang, "-> keys now", len(data))
print("done batch1")
