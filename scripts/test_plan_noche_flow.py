import requests, sys, json
from datetime import datetime, timedelta, timezone

BASE = "http://localhost:8001/api"
MAD = timezone(timedelta(hours=2))

# 1) admin login
r = requests.post(f"{BASE}/auth/login", json={"email": "admin@quienva.app", "password": "admin123"})
lj = r.json()
tok = lj.get("token") or lj.get("session_token")
H = {"Authorization": f"Bearer {tok}"}
uid = (lj.get("user") or {}).get("user_id") or requests.get(f"{BASE}/auth/me", headers=H).json().get("user_id")
print("admin user_id:", uid)

# 2) pick a MADRID event
ev = requests.get(f"{BASE}/events?city=Madrid").json()[0]
eid = ev["id"]
print("event:", ev["name"], eid)

# 3) create a plan (authenticated) with past target date + past deadline + quorum 1, single option
past_target = (datetime.now(MAD) - timedelta(days=1)).isoformat()
past_deadline = (datetime.now(MAD) - timedelta(hours=1)).isoformat()
body = {
    "ciudad": "Madrid", "titulo": "E2E Noche", "creador_apodo": "Admin",
    "opciones": [{"evento_id": eid}],
    "umbral_personas": 2, "hora_limite": past_deadline, "fecha_objetivo": past_target,
}
r = requests.post(f"{BASE}/plans", json=body, headers=H)
slug = r.json()["slug"]
print("plan slug:", slug, "estado:", r.json()["plan"]["estado"])

# 4) respond as the authenticated admin -> registered participant, intencion dentro
r = requests.post(f"{BASE}/plans/{slug}/respond", json={"apodo": "Admin", "intencion": "dentro"}, headers=H)
print("respond admin ok, intencion:", r.json()["plan"]["mine"]["intencion"])

# 4b) second participant (guest, no account) to meet quorum of 2
r = requests.post(f"{BASE}/plans/{slug}/respond", json={"apodo": "Invitado", "intencion": "dentro"})
print("respond guest ok, total:", r.json()["plan"]["counts"]["total"])

# 5) close expired (admin trigger)
r = requests.post(f"{BASE}/admin/plans/close-expired", headers=H)
print("close-expired:", r.status_code, r.json())

# fetch plan state
p = requests.get(f"{BASE}/plans/{slug}").json()
print("after close -> estado:", p["estado"], "opcion_ganadora:", p["opcion_ganadora"])

# 6) convert to noches (admin trigger)
r = requests.post(f"{BASE}/admin/plans/convert-noches", headers=H)
print("convert-noches:", r.status_code, r.json())

# 7) verify admin now has 'estuve' on the event (Recuerdos source = interests)
import pymongo, os
# check via interests through an admin-only? use mongo directly
from pymongo import MongoClient
cli = MongoClient("mongodb://localhost:27017")
db = cli[os.environ.get("DB_NAME", "quienva")]
it = db.interests.find_one({"user_id": uid, "event_id": eid})
print("interest after conversion:", {k: it.get(k) for k in ("status", "source")} if it else None)
pl = db.plans.find_one({"slug": slug})
print("plan.noche_id:", pl.get("noche_id"), "cierre_motivo:", pl.get("cierre_motivo"))

ok = (p["estado"] == "cerrado" and it and it.get("status") == "estuve" and pl.get("noche_id") == eid)
print("\nRESULT:", "PASS ✅" if ok else "FAIL ❌")
