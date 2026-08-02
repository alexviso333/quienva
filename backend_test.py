#!/usr/bin/env python3
"""
Backend API Testing for ¿Quién va? - Chat Photos, Album Multi-upload, Past Events, Scrape Changelog
Test iteration: 2026-08-02g
"""

import requests
import json
import io
from datetime import datetime, timedelta
from PIL import Image

# Base URL from frontend/.env
BASE_URL = "https://04ef964d-e7a3-4272-aa05-db85d0d80903.preview.emergentagent.com/api"

# Admin credentials from /app/memory/test_credentials.md
ADMIN_EMAIL = "admin@quienva.app"
ADMIN_PASSWORD = "admin123"

# Test results
results = {
    "passed": 0,
    "failed": 0,
    "tests": []
}

def log_test(name, passed, details=""):
    """Log test result"""
    status = "✅ PASS" if passed else "❌ FAIL"
    results["tests"].append({"name": name, "passed": passed, "details": details})
    if passed:
        results["passed"] += 1
    else:
        results["failed"] += 1
    print(f"{status}: {name}")
    if details and not passed:
        print(f"  Details: {details}")

def create_test_image(filename="test.jpg"):
    """Create a test image in memory"""
    img = Image.new('RGB', (100, 100), color='red')
    img_bytes = io.BytesIO()
    img.save(img_bytes, format='JPEG')
    img_bytes.seek(0)
    return img_bytes

def create_test_video():
    """Create a fake video file (just bytes with video content-type)"""
    return io.BytesIO(b"fake video content")

# ============================================================================
# SETUP: Login and create test users
# ============================================================================

print("\n" + "="*80)
print("SETUP: Login as admin and create test users")
print("="*80)

# Login as admin
resp = requests.post(f"{BASE_URL}/auth/login", json={
    "email": ADMIN_EMAIL,
    "password": ADMIN_PASSWORD
})
log_test("Admin login", resp.status_code == 200, f"Status: {resp.status_code}")
admin_token = resp.json().get("token") if resp.status_code == 200 else None
admin_headers = {"Authorization": f"Bearer {admin_token}"} if admin_token else {}

# Create test users
test_users = []
for i in range(3):
    username = f"testuser_{datetime.now().timestamp()}_{i}"
    email = f"{username}@test.com"
    resp = requests.post(f"{BASE_URL}/auth/register", json={
        "email": email,
        "password": "Test123!",
        "name": f"Test User {i+1}",
        "username": username,
        "city": "Palma"
    })
    if resp.status_code == 200:
        data = resp.json()
        user_token = data.get("token")
        user_id = data.get("user", {}).get("user_id") if "user" in data else data.get("user_id")
        test_users.append({
            "email": email,
            "token": user_token,
            "user_id": user_id,
            "headers": {"Authorization": f"Bearer {user_token}"}
        })
        log_test(f"Create test user {i+1}", True, f"User ID: {user_id}")
    else:
        log_test(f"Create test user {i+1}", False, f"Status: {resp.status_code}, Response: {resp.text}")

if len(test_users) < 2:
    print("❌ CRITICAL: Failed to create enough test users. Exiting.")
    exit(1)

user1 = test_users[0]
user2 = test_users[1]
user3 = test_users[2] if len(test_users) > 2 else None

# Make user1 and user2 friends
print("\n" + "="*80)
print("SETUP: Make users friends")
print("="*80)

# User1 sends friend request to User2
resp = requests.post(f"{BASE_URL}/friends/request", 
                     json={"user_id": user2["user_id"]},
                     headers=user1["headers"])
log_test("User1 sends friend request to User2", resp.status_code == 200, f"Status: {resp.status_code}")

# User2 gets friend requests to find the request_id
resp = requests.get(f"{BASE_URL}/friends/requests", headers=user2["headers"])
request_id = None
if resp.status_code == 200:
    requests_list = resp.json()
    for req in requests_list:
        if req.get("user", {}).get("user_id") == user1["user_id"]:
            request_id = req.get("request_id")
            break

# User2 accepts friend request from User1
if request_id:
    resp = requests.post(f"{BASE_URL}/friends/respond",
                         json={"request_id": request_id, "accept": True},
                         headers=user2["headers"])
    log_test("User2 accepts friend request", resp.status_code == 200, f"Status: {resp.status_code}")
else:
    log_test("User2 accepts friend request", False, "Could not find request_id")

# If user3 exists, make user1 and user3 friends too
if user3:
    resp = requests.post(f"{BASE_URL}/friends/request",
                         json={"user_id": user3["user_id"]},
                         headers=user1["headers"])
    
    # Get request_id for user3
    resp = requests.get(f"{BASE_URL}/friends/requests", headers=user3["headers"])
    request_id_3 = None
    if resp.status_code == 200:
        requests_list = resp.json()
        for req in requests_list:
            if req.get("user", {}).get("user_id") == user1["user_id"]:
                request_id_3 = req.get("request_id")
                break
    
    if request_id_3:
        resp = requests.post(f"{BASE_URL}/friends/respond",
                             json={"request_id": request_id_3, "accept": True},
                             headers=user3["headers"])
        log_test("User1 and User3 are friends", resp.status_code == 200)
    else:
        log_test("User1 and User3 are friends", False, "Could not find request_id")

# ============================================================================
# FEATURE 1: CHAT PHOTOS
# ============================================================================

print("\n" + "="*80)
print("FEATURE 1: CHAT PHOTOS")
print("="*80)

# Test 1.1: POST /api/chat/upload with 1 image file
print("\n--- Test 1.1: Upload single image to chat ---")
img1 = create_test_image("test1.jpg")
files = {'files': ('test1.jpg', img1, 'image/jpeg')}
resp = requests.post(f"{BASE_URL}/chat/upload", files=files, headers=user1["headers"])
log_test("POST /chat/upload with 1 image", 
         resp.status_code == 200 and "uploads" in resp.json(),
         f"Status: {resp.status_code}, Response: {resp.json() if resp.status_code == 200 else resp.text}")
chat_image_url = None
if resp.status_code == 200:
    uploads = resp.json().get("uploads", [])
    if uploads and len(uploads) > 0:
        chat_image_url = uploads[0].get("media_url")
        log_test("Upload returns media_url and media_type", 
                 "media_url" in uploads[0] and uploads[0].get("media_type") == "image",
                 f"Upload: {uploads[0]}")

# Test 1.2: POST /api/chat/upload with multiple images (2-3)
print("\n--- Test 1.2: Upload multiple images to chat ---")
img2 = create_test_image("test2.jpg")
img3 = create_test_image("test3.jpg")
files = [
    ('files', ('test2.jpg', img2, 'image/jpeg')),
    ('files', ('test3.jpg', img3, 'image/jpeg'))
]
resp = requests.post(f"{BASE_URL}/chat/upload", files=files, headers=user1["headers"])
log_test("POST /chat/upload with 2 images",
         resp.status_code == 200 and "uploads" in resp.json() and len(resp.json().get("uploads", [])) == 2,
         f"Status: {resp.status_code}, Uploads count: {len(resp.json().get('uploads', [])) if resp.status_code == 200 else 'N/A'}")

# Test 1.3: POST /api/chat/upload with non-image file (should return 400)
print("\n--- Test 1.3: Upload non-image file (should fail) ---")
text_file = io.BytesIO(b"This is a text file")
files = {'files': ('test.txt', text_file, 'text/plain')}
resp = requests.post(f"{BASE_URL}/chat/upload", files=files, headers=user1["headers"])
log_test("POST /chat/upload with non-image returns 400",
         resp.status_code == 400,
         f"Status: {resp.status_code}")

# Test 1.4: POST /api/chat/upload unauthenticated (should return 401)
print("\n--- Test 1.4: Upload without auth (should fail) ---")
img4 = create_test_image("test4.jpg")
files = {'files': ('test4.jpg', img4, 'image/jpeg')}
resp = requests.post(f"{BASE_URL}/chat/upload", files=files)
log_test("POST /chat/upload unauthenticated returns 401",
         resp.status_code == 401,
         f"Status: {resp.status_code}")

# Test 1.5: POST /api/dm/send with image_url only (no text) between friends
print("\n--- Test 1.5: Send DM with image_url only (no text) ---")
if chat_image_url:
    resp = requests.post(f"{BASE_URL}/dm/send",
                         json={"to_user_id": user2["user_id"], "image_url": chat_image_url},
                         headers=user1["headers"])
    log_test("POST /dm/send with image_url only succeeds",
             resp.status_code == 200 and resp.json().get("image_url") == chat_image_url,
             f"Status: {resp.status_code}, Response: {resp.json() if resp.status_code == 200 else resp.text}")
    dm_with_image_id = resp.json().get("id") if resp.status_code == 200 else None
else:
    log_test("POST /dm/send with image_url only", False, "No chat_image_url available from previous test")

# Test 1.6: POST /api/dm/send with neither text nor image_url (should return 400)
print("\n--- Test 1.6: Send DM with neither text nor image_url (should fail) ---")
resp = requests.post(f"{BASE_URL}/dm/send",
                     json={"to_user_id": user2["user_id"], "text": "", "image_url": ""},
                     headers=user1["headers"])
log_test("POST /dm/send with neither text nor image_url returns 400",
         resp.status_code == 400,
         f"Status: {resp.status_code}")

# Test 1.7: POST /api/dm/send with text length >1000 (should return 400)
print("\n--- Test 1.7: Send DM with text >1000 chars (should fail) ---")
long_text = "a" * 1001
resp = requests.post(f"{BASE_URL}/dm/send",
                     json={"to_user_id": user2["user_id"], "text": long_text},
                     headers=user1["headers"])
log_test("POST /dm/send with text >1000 chars returns 400",
         resp.status_code == 400,
         f"Status: {resp.status_code}")

# Test 1.8: POST /api/dm/send to non-friend (should return 403)
print("\n--- Test 1.8: Send DM to non-friend (should fail) ---")
# Use admin as non-friend
resp = requests.post(f"{BASE_URL}/dm/send",
                     json={"to_user_id": "admin_user_id_fake", "text": "Hello"},
                     headers=user1["headers"])
log_test("POST /dm/send to non-friend returns 403",
         resp.status_code == 403,
         f"Status: {resp.status_code}")

# Test 1.9: GET /api/dm/{other_user_id}/messages includes image_url
print("\n--- Test 1.9: GET DM messages includes image_url ---")
resp = requests.get(f"{BASE_URL}/dm/{user2['user_id']}/messages", headers=user1["headers"])
log_test("GET /dm/{other_user_id}/messages returns 200",
         resp.status_code == 200,
         f"Status: {resp.status_code}")
if resp.status_code == 200:
    messages = resp.json()
    has_image_url = any(msg.get("image_url") for msg in messages)
    log_test("DM messages include image_url field",
             has_image_url,
             f"Found {len([m for m in messages if m.get('image_url')])} messages with image_url")

# Test 1.10: GET /api/dm/threads shows "📷 Foto" for image-only last message
print("\n--- Test 1.10: GET DM threads shows '📷 Foto' for image-only message ---")
resp = requests.get(f"{BASE_URL}/dm/threads", headers=user1["headers"])
log_test("GET /dm/threads returns 200",
         resp.status_code == 200,
         f"Status: {resp.status_code}")
if resp.status_code == 200:
    threads = resp.json()
    # Find thread with user2
    user2_thread = None
    for thread in threads:
        # Check if thread is with user2 (could be in 'user' or 'other_user' field)
        thread_user = thread.get("user") or thread.get("other_user")
        if thread_user and thread_user.get("user_id") == user2["user_id"]:
            user2_thread = thread
            break
    
    if user2_thread:
        last_message = user2_thread.get("last_message", "")
        log_test("DM thread last_message is '📷 Foto' for image-only",
                 last_message == "📷 Foto",
                 f"Last message: '{last_message}'")
    else:
        log_test("Find thread with user2", False, "Thread not found in response")

# Test 1.11: Create a group for group message tests
print("\n--- Test 1.11: Create group for testing ---")
resp = requests.post(f"{BASE_URL}/groups",
                     json={"name": "Test Group", "member_ids": [user2["user_id"]]},
                     headers=user1["headers"])
log_test("POST /groups creates group",
         resp.status_code == 200,
         f"Status: {resp.status_code}")
group_id = resp.json().get("id") if resp.status_code == 200 else None

# Test 1.12: POST /api/groups/{id}/messages with image_url only (no text)
print("\n--- Test 1.12: Send group message with image_url only ---")
if group_id and chat_image_url:
    resp = requests.post(f"{BASE_URL}/groups/{group_id}/messages",
                         json={"image_url": chat_image_url},
                         headers=user1["headers"])
    log_test("POST /groups/{id}/messages with image_url only succeeds",
             resp.status_code == 200 and resp.json().get("image_url") == chat_image_url,
             f"Status: {resp.status_code}, Response: {resp.json() if resp.status_code == 200 else resp.text}")
else:
    log_test("POST /groups/{id}/messages with image_url only", False, 
             f"Missing group_id or chat_image_url (group_id: {group_id}, image_url: {chat_image_url})")

# Test 1.13: POST /api/groups/{id}/messages with neither text nor image_url (should return 400)
print("\n--- Test 1.13: Send group message with neither text nor image_url (should fail) ---")
if group_id:
    resp = requests.post(f"{BASE_URL}/groups/{group_id}/messages",
                         json={"text": "", "image_url": ""},
                         headers=user1["headers"])
    log_test("POST /groups/{id}/messages with neither text nor image_url returns 400",
             resp.status_code == 400,
             f"Status: {resp.status_code}")
else:
    log_test("POST /groups/{id}/messages validation", False, "No group_id available")

# Test 1.14: GET /api/groups/{id}/messages includes image_url
print("\n--- Test 1.14: GET group messages includes image_url ---")
if group_id:
    resp = requests.get(f"{BASE_URL}/groups/{group_id}/messages", headers=user1["headers"])
    log_test("GET /groups/{id}/messages returns 200",
             resp.status_code == 200,
             f"Status: {resp.status_code}")
    if resp.status_code == 200:
        messages = resp.json()
        has_image_url = any(msg.get("image_url") for msg in messages)
        log_test("Group messages include image_url field",
                 has_image_url,
                 f"Found {len([m for m in messages if m.get('image_url')])} messages with image_url")
else:
    log_test("GET /groups/{id}/messages", False, "No group_id available")

# ============================================================================
# FEATURE 2: ALBUM MULTI-UPLOAD + SHARE-BATCH
# ============================================================================

print("\n" + "="*80)
print("FEATURE 2: ALBUM MULTI-UPLOAD + SHARE-BATCH")
print("="*80)

# Create a test event (as admin)
print("\n--- Setup: Create test event ---")
future_date = (datetime.now() + timedelta(days=7)).strftime("%Y-%m-%d")
resp = requests.post(f"{BASE_URL}/admin/events",
                     json={
                         "name": "Test Event for Album",
                         "venue": "Test Venue",
                         "date": future_date,
                         "city": "Palma",
                         "genre": "Electrónica"
                     },
                     headers=admin_headers)
log_test("Create test event", resp.status_code == 200, f"Status: {resp.status_code}")
event_id = resp.json().get("id") if resp.status_code == 200 else None

# User1 marks interest (voy) on the event
print("\n--- Setup: User1 marks 'voy' on event ---")
if event_id:
    resp = requests.post(f"{BASE_URL}/events/{event_id}/interest",
                         json={"status": "voy"},
                         headers=user1["headers"])
    log_test("User1 marks 'voy' on event", resp.status_code == 200, f"Status: {resp.status_code}")
else:
    log_test("User1 marks interest", False, "No event_id available")

# Test 2.1: POST /api/events/{id}/album/upload with single file (backwards compat)
print("\n--- Test 2.1: Upload single file to album ---")
if event_id:
    img_single = create_test_image("album1.jpg")
    files = {'files': ('album1.jpg', img_single, 'image/jpeg')}
    resp = requests.post(f"{BASE_URL}/events/{event_id}/album/upload",
                         files=files,
                         headers=user1["headers"])
    log_test("POST /events/{id}/album/upload with single file returns 200",
             resp.status_code == 200,
             f"Status: {resp.status_code}")
    
    single_upload = None
    if resp.status_code == 200:
        data = resp.json()
        # Single file should return single object (backwards compat)
        if "id" in data and "media_url" in data:
            single_upload = data
            log_test("Single file returns single object (not array)",
                     True,
                     f"Response has id and media_url: {data.get('id')}")
        else:
            log_test("Single file returns single object", False, f"Response: {data}")
else:
    log_test("Upload single file to album", False, "No event_id available")

# Test 2.2: POST /api/events/{id}/album/upload with multiple files
print("\n--- Test 2.2: Upload multiple files to album ---")
if event_id:
    img_multi1 = create_test_image("album2.jpg")
    img_multi2 = create_test_image("album3.jpg")
    img_multi3 = create_test_image("album4.jpg")
    files = [
        ('files', ('album2.jpg', img_multi1, 'image/jpeg')),
        ('files', ('album3.jpg', img_multi2, 'image/jpeg')),
        ('files', ('album4.jpg', img_multi3, 'image/jpeg'))
    ]
    resp = requests.post(f"{BASE_URL}/events/{event_id}/album/upload",
                         files=files,
                         headers=user1["headers"])
    log_test("POST /events/{id}/album/upload with multiple files returns 200",
             resp.status_code == 200,
             f"Status: {resp.status_code}")
    
    user1_upload_ids = []
    if resp.status_code == 200:
        data = resp.json()
        if "uploads" in data and "count" in data:
            uploads = data.get("uploads", [])
            count = data.get("count", 0)
            log_test("Multiple files return {uploads, count}",
                     len(uploads) == 3 and count == 3,
                     f"Uploads: {len(uploads)}, Count: {count}")
            user1_upload_ids = [u.get("id") for u in uploads if u.get("id")]
        else:
            log_test("Multiple files return correct structure", False, f"Response: {data}")
else:
    log_test("Upload multiple files to album", False, "No event_id available")

# Test 2.3: Upload without interest (should return 403)
print("\n--- Test 2.3: Upload without interest (should fail) ---")
if event_id and user3:
    # User3 has no interest on this event
    img_no_interest = create_test_image("album_fail.jpg")
    files = {'files': ('album_fail.jpg', img_no_interest, 'image/jpeg')}
    resp = requests.post(f"{BASE_URL}/events/{event_id}/album/upload",
                         files=files,
                         headers=user3["headers"])
    log_test("POST /events/{id}/album/upload without interest returns 403",
             resp.status_code == 403,
             f"Status: {resp.status_code}")
else:
    log_test("Upload without interest", False, "Missing event_id or user3")

# Test 2.4: Upload non-image/video content (should return 400)
print("\n--- Test 2.4: Upload non-image/video content (should fail) ---")
if event_id:
    text_file = io.BytesIO(b"This is a text file")
    files = {'files': ('album.txt', text_file, 'text/plain')}
    resp = requests.post(f"{BASE_URL}/events/{event_id}/album/upload",
                         files=files,
                         headers=user1["headers"])
    log_test("POST /events/{id}/album/upload with non-image/video returns 400",
             resp.status_code == 400,
             f"Status: {resp.status_code}")
else:
    log_test("Upload non-image/video", False, "No event_id available")

# Test 2.5: User2 marks interest and uploads (for share-batch test)
print("\n--- Setup: User2 marks 'voy' and uploads ---")
if event_id:
    resp = requests.post(f"{BASE_URL}/events/{event_id}/interest",
                         json={"status": "voy"},
                         headers=user2["headers"])
    log_test("User2 marks 'voy' on event", resp.status_code == 200)
    
    # User2 uploads a photo
    img_user2 = create_test_image("user2_album.jpg")
    files = {'files': ('user2_album.jpg', img_user2, 'image/jpeg')}
    resp = requests.post(f"{BASE_URL}/events/{event_id}/album/upload",
                         files=files,
                         headers=user2["headers"])
    user2_upload_id = resp.json().get("id") if resp.status_code == 200 else None
    log_test("User2 uploads photo", resp.status_code == 200)

# Test 2.6: POST /api/events/{id}/album/share-batch with empty upload_ids (should return 400)
print("\n--- Test 2.6: Share-batch with empty upload_ids (should fail) ---")
if event_id:
    resp = requests.post(f"{BASE_URL}/events/{event_id}/album/share-batch",
                         json={"upload_ids": [], "all_friends": True},
                         headers=user1["headers"])
    log_test("POST /events/{id}/album/share-batch with empty upload_ids returns 400",
             resp.status_code == 400,
             f"Status: {resp.status_code}")
else:
    log_test("Share-batch with empty upload_ids", False, "No event_id available")

# Test 2.7: POST /api/events/{id}/album/share-batch with no audience (should return 400)
print("\n--- Test 2.7: Share-batch with no audience (should fail) ---")
if event_id and user1_upload_ids:
    resp = requests.post(f"{BASE_URL}/events/{event_id}/album/share-batch",
                         json={"upload_ids": user1_upload_ids[:1]},
                         headers=user1["headers"])
    log_test("POST /events/{id}/album/share-batch with no audience returns 400",
             resp.status_code == 400,
             f"Status: {resp.status_code}")
else:
    log_test("Share-batch with no audience", False, "Missing event_id or upload_ids")

# Test 2.8: POST /api/events/{id}/album/share-batch with valid upload_ids and all_friends
print("\n--- Test 2.8: Share-batch with valid upload_ids and all_friends ---")
if event_id and user1_upload_ids:
    resp = requests.post(f"{BASE_URL}/events/{event_id}/album/share-batch",
                         json={"upload_ids": user1_upload_ids, "all_friends": True},
                         headers=user1["headers"])
    log_test("POST /events/{id}/album/share-batch succeeds",
             resp.status_code == 200 and resp.json().get("ok") == True,
             f"Status: {resp.status_code}, Response: {resp.json() if resp.status_code == 200 else resp.text}")
    
    if resp.status_code == 200:
        shared_count = resp.json().get("shared_count", 0)
        log_test("Share-batch returns shared_count",
                 shared_count == len(user1_upload_ids),
                 f"Shared count: {shared_count}, Expected: {len(user1_upload_ids)}")
else:
    log_test("Share-batch with valid data", False, "Missing event_id or upload_ids")

# Test 2.9: Verify GET /api/events/{id}/album shows uploads in "shared" bucket for friend
print("\n--- Test 2.9: Verify shared uploads visible to friend ---")
if event_id:
    resp = requests.get(f"{BASE_URL}/events/{event_id}/album", headers=user2["headers"])
    log_test("GET /events/{id}/album as friend returns 200",
             resp.status_code == 200,
             f"Status: {resp.status_code}")
    
    if resp.status_code == 200:
        data = resp.json()
        shared_bucket = data.get("shared", [])
        # Should see user1's shared uploads in the shared bucket
        user1_shared = [u for u in shared_bucket if u.get("user_id") == user1["user_id"]]
        log_test("Friend sees shared uploads in 'shared' bucket",
                 len(user1_shared) > 0,
                 f"Found {len(user1_shared)} shared uploads from user1")
else:
    log_test("Verify shared uploads", False, "No event_id available")

# Test 2.10: Try to share another user's upload_id (should be ignored)
print("\n--- Test 2.10: Try to share another user's upload (should be ignored) ---")
if event_id and user2_upload_id:
    # User1 tries to share user2's upload
    resp = requests.post(f"{BASE_URL}/events/{event_id}/album/share-batch",
                         json={"upload_ids": [user2_upload_id], "all_friends": True},
                         headers=user1["headers"])
    # Should return 404 because no uploads belong to user1
    log_test("Share-batch with another user's upload_id returns 404",
             resp.status_code == 404,
             f"Status: {resp.status_code}, Response: {resp.text}")
else:
    log_test("Share another user's upload", False, "Missing event_id or user2_upload_id")

# ============================================================================
# FEATURE 3: PAST EVENTS + ACTIVITY FUTURE-ONLY
# ============================================================================

print("\n" + "="*80)
print("FEATURE 3: PAST EVENTS + ACTIVITY FUTURE-ONLY")
print("="*80)

# Create a past event (as admin)
print("\n--- Setup: Create past event ---")
past_date = (datetime.now() - timedelta(days=7)).strftime("%Y-%m-%d")
resp = requests.post(f"{BASE_URL}/admin/events",
                     json={
                         "name": "Past Event Test",
                         "venue": "Past Venue",
                         "date": past_date,
                         "city": "Palma",
                         "genre": "Reggaeton"
                     },
                     headers=admin_headers)
log_test("Create past event", resp.status_code == 200, f"Status: {resp.status_code}")
past_event_id = resp.json().get("id") if resp.status_code == 200 else None

# User1 marks 'estuve' on past event
print("\n--- Setup: User1 marks 'estuve' on past event ---")
if past_event_id:
    resp = requests.post(f"{BASE_URL}/events/{past_event_id}/interest",
                         json={"status": "estuve"},
                         headers=user1["headers"])
    log_test("User1 marks 'estuve' on past event", resp.status_code == 200)

# User1 uploads a photo to past event
if past_event_id:
    img_past = create_test_image("past_event.jpg")
    files = {'files': ('past_event.jpg', img_past, 'image/jpeg')}
    resp = requests.post(f"{BASE_URL}/events/{past_event_id}/album/upload",
                         files=files,
                         headers=user1["headers"])
    log_test("User1 uploads photo to past event", resp.status_code == 200)

# Test 3.1: GET /api/me/past-events returns only past events with voy/estuve status
print("\n--- Test 3.1: GET /me/past-events ---")
resp = requests.get(f"{BASE_URL}/me/past-events", headers=user1["headers"])
log_test("GET /me/past-events returns 200",
         resp.status_code == 200,
         f"Status: {resp.status_code}")

if resp.status_code == 200:
    data = resp.json()
    items = data.get("items", [])
    log_test("Past-events returns items array",
             isinstance(items, list),
             f"Items count: {len(items)}")
    
    # Check if past event is in the list (note: response uses 'id' not 'event_id')
    past_event_found = any(item.get("id") == past_event_id for item in items)
    log_test("Past event with 'estuve' status is in list",
             past_event_found,
             f"Found: {past_event_found}")
    
    # Check if future event is NOT in the list
    future_event_found = any(item.get("id") == event_id for item in items)
    log_test("Future event is NOT in past-events list",
             not future_event_found,
             f"Future event found: {future_event_found}")
    
    # Check structure of items (note: response uses 'id' not 'event_id')
    if items:
        first_item = items[0]
        has_required_fields = all(k in first_item for k in ["id", "my_status", "my_photos"])
        log_test("Past-events items have required fields (id, my_status, my_photos)",
                 has_required_fields,
                 f"First item keys: {list(first_item.keys())}")

# Test 3.2: GET /api/me/activity excludes past events
print("\n--- Test 3.2: GET /me/activity excludes past events ---")
resp = requests.get(f"{BASE_URL}/me/activity", headers=user1["headers"])
log_test("GET /me/activity returns 200",
         resp.status_code == 200,
         f"Status: {resp.status_code}")

if resp.status_code == 200:
    data = resp.json()
    items = data.get("items", [])
    log_test("Activity returns items array",
             isinstance(items, list),
             f"Items count: {len(items)}")
    
    # Check that no past events are in activity
    has_past_events = any(item.get("event_id") == past_event_id for item in items)
    log_test("Activity does NOT include past events",
             not has_past_events,
             f"Past event found in activity: {has_past_events}")
    
    # All events in activity should be future events (date >= today)
    today = datetime.now().strftime("%Y-%m-%d")
    all_future = all(item.get("date", "") >= today for item in items if "date" in item)
    log_test("All activity items are for future events (date >= today)",
             all_future,
             f"All future: {all_future}, Items with dates: {len([i for i in items if 'date' in i])}")

# ============================================================================
# FEATURE 4: ADMIN SCRAPE CHANGELOG
# ============================================================================

print("\n" + "="*80)
print("FEATURE 4: ADMIN SCRAPE CHANGELOG")
print("="*80)

# Test 4.1: GET /api/admin/scrape-changelog as admin
print("\n--- Test 4.1: GET /admin/scrape-changelog as admin ---")
resp = requests.get(f"{BASE_URL}/admin/scrape-changelog?limit=60", headers=admin_headers)
log_test("GET /admin/scrape-changelog as admin returns 200",
         resp.status_code == 200,
         f"Status: {resp.status_code}")

if resp.status_code == 200:
    data = resp.json()
    required_keys = ["last_run", "counts", "total", "entries"]
    has_all_keys = all(k in data for k in required_keys)
    log_test("Scrape-changelog response has required keys (last_run, counts, total, entries)",
             has_all_keys,
             f"Keys: {list(data.keys())}")
    
    if "counts" in data:
        counts = data["counts"]
        expected_count_keys = ["new", "price_up", "price_down", "state", "sold_out", "on_sale"]
        has_count_keys = all(k in counts for k in expected_count_keys)
        log_test("Counts object has expected keys",
                 has_count_keys,
                 f"Count keys: {list(counts.keys())}")

# Test 4.2: GET /api/admin/scrape-changelog as non-admin (should return 403)
print("\n--- Test 4.2: GET /admin/scrape-changelog as non-admin (should fail) ---")
resp = requests.get(f"{BASE_URL}/admin/scrape-changelog?limit=60", headers=user1["headers"])
log_test("GET /admin/scrape-changelog as non-admin returns 403",
         resp.status_code == 403,
         f"Status: {resp.status_code}")

# Test 4.3: GET /api/admin/scrape-changelog unauthenticated (should return 401)
print("\n--- Test 4.3: GET /admin/scrape-changelog unauthenticated (should fail) ---")
resp = requests.get(f"{BASE_URL}/admin/scrape-changelog?limit=60")
log_test("GET /admin/scrape-changelog unauthenticated returns 401",
         resp.status_code == 401,
         f"Status: {resp.status_code}")

# ============================================================================
# LIGHT REGRESSION TESTS
# ============================================================================

print("\n" + "="*80)
print("LIGHT REGRESSION TESTS")
print("="*80)

# Test R1: POST /api/auth/login
print("\n--- Regression: POST /auth/login ---")
resp = requests.post(f"{BASE_URL}/auth/login", json={
    "email": ADMIN_EMAIL,
    "password": ADMIN_PASSWORD
})
log_test("POST /auth/login works",
         resp.status_code == 200 and "token" in resp.json(),
         f"Status: {resp.status_code}")

# Test R2: GET /api/auth/me
print("\n--- Regression: GET /auth/me ---")
resp = requests.get(f"{BASE_URL}/auth/me", headers=admin_headers)
log_test("GET /auth/me works",
         resp.status_code == 200 and "user_id" in resp.json(),
         f"Status: {resp.status_code}")

# Test R3: GET /api/events
print("\n--- Regression: GET /events ---")
resp = requests.get(f"{BASE_URL}/events", headers=user1["headers"])
log_test("GET /events works",
         resp.status_code == 200,
         f"Status: {resp.status_code}")

# Test R4: POST /api/events/{id}/interest
print("\n--- Regression: POST /events/{id}/interest ---")
if event_id:
    resp = requests.post(f"{BASE_URL}/events/{event_id}/interest",
                         json={"status": "me_interesa"},
                         headers=user1["headers"])
    log_test("POST /events/{id}/interest works",
             resp.status_code == 200,
             f"Status: {resp.status_code}")

# Test R5: GET /api/dm/threads
print("\n--- Regression: GET /dm/threads ---")
resp = requests.get(f"{BASE_URL}/dm/threads", headers=user1["headers"])
log_test("GET /dm/threads works",
         resp.status_code == 200,
         f"Status: {resp.status_code}")

# Test R6: GET /api/groups
print("\n--- Regression: GET /groups ---")
resp = requests.get(f"{BASE_URL}/groups", headers=user1["headers"])
log_test("GET /groups works",
         resp.status_code == 200,
         f"Status: {resp.status_code}")

# ============================================================================
# SUMMARY
# ============================================================================

print("\n" + "="*80)
print("TEST SUMMARY")
print("="*80)
print(f"Total tests: {results['passed'] + results['failed']}")
print(f"✅ Passed: {results['passed']}")
print(f"❌ Failed: {results['failed']}")
print(f"Pass rate: {results['passed'] / (results['passed'] + results['failed']) * 100:.1f}%")

if results['failed'] > 0:
    print("\n" + "="*80)
    print("FAILED TESTS:")
    print("="*80)
    for test in results['tests']:
        if not test['passed']:
            print(f"❌ {test['name']}")
            if test['details']:
                print(f"   {test['details']}")

print("\n" + "="*80)
print("TEST COMPLETE")
print("="*80)
