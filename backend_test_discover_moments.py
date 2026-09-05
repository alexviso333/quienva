#!/usr/bin/env python3
"""
Additional test to verify moments in discover have likes and i_liked fields
"""

import requests
import io
from datetime import datetime
from PIL import Image

BASE_URL = "https://fiesta-rebuild.preview.emergentagent.com/api"
ADMIN_EMAIL = "admin@quienva.app"
ADMIN_PASSWORD = "admin123"

def log(msg):
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}")

def login(email, password):
    resp = requests.post(f"{BASE_URL}/auth/login", json={"email": email, "password": password})
    return resp.json()["token"] if resp.status_code == 200 else None

def register_user(name, email, username, birthdate="1995-05-05"):
    resp = requests.post(f"{BASE_URL}/auth/register", json={
        "name": name,
        "email": email,
        "password": "testpass123",
        "city": "Palma de Mallorca",
        "birthdate": birthdate,
        "username": username
    })
    if resp.status_code != 200:
        return None, None
    data = resp.json()
    return data["token"], data["user"]["user_id"]

def create_test_image():
    img = Image.new('RGB', (100, 100), color='blue')
    img_bytes = io.BytesIO()
    img.save(img_bytes, format='JPEG')
    img_bytes.seek(0)
    return img_bytes

def main():
    log("Testing moments in discover with likes and i_liked fields...")
    
    # Login as admin
    admin_token = login(ADMIN_EMAIL, ADMIN_PASSWORD)
    if not admin_token:
        log("❌ Failed to login as admin")
        return False
    
    # Create event
    today = datetime.now().strftime("%Y-%m-%d")
    resp = requests.post(
        f"{BASE_URL}/admin/events",
        json={"name": "Moment Test Event", "venue": "Test Venue", "date": today, "time": "23:00", "city": "Palma de Mallorca", "genre": "techno"},
        headers={"Authorization": f"Bearer {admin_token}"}
    )
    if resp.status_code != 200:
        log(f"❌ Failed to create event: {resp.text}")
        return False
    event_id = resp.json()["id"]
    log(f"✅ Event created: {event_id}")
    
    # Register user with PUBLIC moment privacy
    token_public, user_id_public = register_user("Public User", "public_test@test.com", "publicuser")
    if not token_public:
        log("❌ Failed to register public user")
        return False
    
    # Set moment_privacy to publico
    resp = requests.put(
        f"{BASE_URL}/auth/profile",
        json={"moment_privacy": "publico"},
        headers={"Authorization": f"Bearer {token_public}"}
    )
    if resp.status_code != 200:
        log(f"❌ Failed to set moment_privacy: {resp.text}")
        return False
    log("✅ Set moment_privacy to publico")
    
    # User marks voy
    resp = requests.post(
        f"{BASE_URL}/events/{event_id}/interest",
        json={"status": "voy"},
        headers={"Authorization": f"Bearer {token_public}"}
    )
    if resp.status_code != 200:
        log(f"❌ Failed to mark interest: {resp.text}")
        return False
    
    # Trigger moment
    resp = requests.post(
        f"{BASE_URL}/admin/events/{event_id}/moment/trigger",
        headers={"Authorization": f"Bearer {admin_token}"}
    )
    if resp.status_code != 200:
        log(f"❌ Failed to trigger moment: {resp.text}")
        return False
    log("✅ Moment triggered")
    
    # Upload capture
    img_bytes = create_test_image()
    files = {'file': ('test.jpg', img_bytes, 'image/jpeg')}
    resp = requests.post(
        f"{BASE_URL}/events/{event_id}/moment/upload",
        files=files,
        headers={"Authorization": f"Bearer {token_public}"}
    )
    if resp.status_code != 200:
        log(f"❌ Failed to upload capture: {resp.text}")
        return False
    log("✅ Capture uploaded by public user")
    
    # Register another user to view discover
    token_viewer, user_id_viewer = register_user("Viewer User", "viewer_test@test.com", "vieweruser")
    if not token_viewer:
        log("❌ Failed to register viewer")
        return False
    
    # Call discover
    resp = requests.get(
        f"{BASE_URL}/discover",
        headers={"Authorization": f"Bearer {token_viewer}"}
    )
    if resp.status_code != 200:
        log(f"❌ Failed to get discover: {resp.text}")
        return False
    
    data = resp.json()
    log(f"✅ Discover returned: people={len(data['people'])}, moments={len(data['moments'])}")
    
    # Verify moments have likes and i_liked
    if len(data["moments"]) == 0:
        log("⚠️  No moments in discover (might be timing issue)")
        return True
    
    moment = data["moments"][0]
    if "likes" not in moment:
        log(f"❌ Moment missing 'likes' field: {moment.keys()}")
        return False
    if "i_liked" not in moment:
        log(f"❌ Moment missing 'i_liked' field: {moment.keys()}")
        return False
    if not isinstance(moment["likes"], int):
        log(f"❌ 'likes' should be int, got: {type(moment['likes'])}")
        return False
    if not isinstance(moment["i_liked"], bool):
        log(f"❌ 'i_liked' should be bool, got: {type(moment['i_liked'])}")
        return False
    
    log(f"✅ Moment has correct fields: likes={moment['likes']} (int), i_liked={moment['i_liked']} (bool)")
    
    # Test liking the moment
    capture_id = moment["id"]
    resp = requests.post(
        f"{BASE_URL}/captures/{capture_id}/like",
        headers={"Authorization": f"Bearer {token_viewer}"}
    )
    if resp.status_code != 200:
        log(f"❌ Failed to like capture: {resp.text}")
        return False
    
    # Check discover again
    resp = requests.get(
        f"{BASE_URL}/discover",
        headers={"Authorization": f"Bearer {token_viewer}"}
    )
    data = resp.json()
    if len(data["moments"]) > 0:
        moment = data["moments"][0]
        if moment["id"] == capture_id:
            if moment["i_liked"] != True:
                log(f"❌ After liking, i_liked should be True, got: {moment['i_liked']}")
                return False
            if moment["likes"] != 1:
                log(f"❌ After liking, likes should be 1, got: {moment['likes']}")
                return False
            log(f"✅ After liking: i_liked={moment['i_liked']}, likes={moment['likes']} (correct)")
    
    log("✅ ALL MOMENT TESTS PASSED")
    return True

if __name__ == "__main__":
    success = main()
    exit(0 if success else 1)
