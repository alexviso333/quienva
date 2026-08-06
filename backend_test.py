#!/usr/bin/env python3
"""
Wrapped Verification Test
Tests the Wrapped feature with specific seeding and verification requirements.
System current month: 2026-08, previous month: 2026-07
"""

import requests
import os
from io import BytesIO
from PIL import Image

# Backend URL from environment
BACKEND_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://204b173e-f0b3-4059-a373-e97cae5b5cd7.preview.emergentagent.com")
BASE_URL = f"{BACKEND_URL}/api"

def create_test_image():
    """Create a small test image in memory"""
    img = Image.new('RGB', (100, 100), color='red')
    img_bytes = BytesIO()
    img.save(img_bytes, format='JPEG')
    img_bytes.seek(0)
    return img_bytes

def test_wrapped_verification():
    """
    Test Wrapped verification in FRESH LOCAL environment (empty MongoDB; NO FourVenues token).
    
    SEED:
    1. Login admin. Create events via POST /api/admin/events:
       - evJul1: date 2026-07-12, venue "Sala J", genre "Reggaeton"
       - evJul2: date 2026-07-20, venue "Sala K", genre "Techno"
       - evAug: date 2026-08-05, venue "Sala A", genre "House"
    2. Register/login user U1. POST /api/events/{id}/interest {"status":"estuve"} for all three.
    3. As U1, POST /api/events/{evJul1}/album with multipart field name "files" (send one small image) -> expect 200.
    4. As admin POST /api/admin/events/{evJul1}/moment/trigger. As U1 POST /api/events/{evJul1}/moment/upload with multipart field name "file" (one small image) -> expect 200.
    
    VERIFY:
    5. As U1: GET /api/me/wrapped (NO month param) -> month=="2026-07"; has_data==true; parties==2 (only July events, NOT August); photos>=1; moments>=1; `gallery` is a list length>=2; every item has non-empty "url" and "kind" in ["photo","moment"]; at least one kind=="photo" AND at least one kind=="moment".
    6. As U1: GET /api/me/wrapped?month=2026-08 -> parties==1.
    7. As U1: GET /api/me/wrapped/year?year=2026 -> parties==3; `gallery` present (list).
    """
    
    print("=" * 80)
    print("WRAPPED VERIFICATION TEST")
    print("=" * 80)
    
    # Step 1: Admin login
    print("\n[STEP 1] Admin login...")
    admin_resp = requests.post(f"{BASE_URL}/auth/login", json={
        "email": "admin@quienva.app",
        "password": "admin123"
    })
    assert admin_resp.status_code == 200, f"Admin login failed: {admin_resp.status_code} {admin_resp.text}"
    admin_token = admin_resp.json()["token"]
    admin_headers = {"Authorization": f"Bearer {admin_token}"}
    print(f"✅ Admin login successful")
    
    # Step 2: Create 3 events
    print("\n[STEP 2] Creating 3 events...")
    
    # evJul1: 2026-07-12, Sala J, Reggaeton
    evJul1_resp = requests.post(f"{BASE_URL}/admin/events", headers=admin_headers, json={
        "name": "Fiesta Reggaeton Julio 1",
        "venue": "Sala J",
        "city": "Palma de Mallorca",
        "date": "2026-07-12",
        "time": "23:00",
        "genre": "Reggaeton",
        "image_url": "https://example.com/image1.jpg"
    })
    assert evJul1_resp.status_code == 200, f"Failed to create evJul1: {evJul1_resp.status_code} {evJul1_resp.text}"
    evJul1_id = evJul1_resp.json()["id"]
    print(f"✅ Created evJul1 (id={evJul1_id}): 2026-07-12, Sala J, Reggaeton")
    
    # evJul2: 2026-07-20, Sala K, Techno
    evJul2_resp = requests.post(f"{BASE_URL}/admin/events", headers=admin_headers, json={
        "name": "Fiesta Techno Julio 2",
        "venue": "Sala K",
        "city": "Palma de Mallorca",
        "date": "2026-07-20",
        "time": "23:00",
        "genre": "Techno",
        "image_url": "https://example.com/image2.jpg"
    })
    assert evJul2_resp.status_code == 200, f"Failed to create evJul2: {evJul2_resp.status_code} {evJul2_resp.text}"
    evJul2_id = evJul2_resp.json()["id"]
    print(f"✅ Created evJul2 (id={evJul2_id}): 2026-07-20, Sala K, Techno")
    
    # evAug: 2026-08-05, Sala A, House
    evAug_resp = requests.post(f"{BASE_URL}/admin/events", headers=admin_headers, json={
        "name": "Fiesta House Agosto",
        "venue": "Sala A",
        "city": "Palma de Mallorca",
        "date": "2026-08-05",
        "time": "23:00",
        "genre": "House",
        "image_url": "https://example.com/image3.jpg"
    })
    assert evAug_resp.status_code == 200, f"Failed to create evAug: {evAug_resp.status_code} {evAug_resp.text}"
    evAug_id = evAug_resp.json()["id"]
    print(f"✅ Created evAug (id={evAug_id}): 2026-08-05, Sala A, House")
    
    # Step 3: Register user U1
    print("\n[STEP 3] Registering user U1...")
    import time
    ts = int(time.time())
    u1_email = f"u1test{ts}@test.com"
    u1_username = f"u1test{ts}"
    
    u1_reg_resp = requests.post(f"{BASE_URL}/auth/register", json={
        "email": u1_email,
        "password": "password123",
        "username": u1_username,
        "name": "User One Test",
        "birthdate": "1995-01-01",
        "city": "Palma de Mallorca"
    })
    assert u1_reg_resp.status_code == 200, f"Failed to register U1: {u1_reg_resp.status_code} {u1_reg_resp.text}"
    u1_token = u1_reg_resp.json()["token"]
    u1_headers = {"Authorization": f"Bearer {u1_token}"}
    print(f"✅ Registered U1: {u1_email}")
    
    # Step 4: U1 marks "estuve" on all three events
    print("\n[STEP 4] U1 marking 'estuve' on all three events...")
    
    for event_id, event_name in [(evJul1_id, "evJul1"), (evJul2_id, "evJul2"), (evAug_id, "evAug")]:
        interest_resp = requests.post(f"{BASE_URL}/events/{event_id}/interest", 
                                     headers=u1_headers, 
                                     json={"status": "estuve"})
        assert interest_resp.status_code == 200, f"Failed to mark estuve on {event_name}: {interest_resp.status_code} {interest_resp.text}"
        print(f"✅ U1 marked 'estuve' on {event_name}")
    
    # Step 5: U1 uploads album photo to evJul1 (field name "files" PLURAL)
    print("\n[STEP 5] U1 uploading album photo to evJul1 (field name 'files')...")
    
    img_bytes = create_test_image()
    files = {'files': ('test_album.jpg', img_bytes, 'image/jpeg')}
    
    album_resp = requests.post(f"{BASE_URL}/events/{evJul1_id}/album/upload", 
                               headers=u1_headers, 
                               files=files)
    assert album_resp.status_code == 200, f"Failed to upload album photo: {album_resp.status_code} {album_resp.text}"
    album_data = album_resp.json()
    print(f"✅ U1 uploaded album photo to evJul1")
    print(f"   Album response: {album_data}")
    
    # Step 6: Admin triggers moment for evJul1
    print("\n[STEP 6] Admin triggering moment for evJul1...")
    
    moment_trigger_resp = requests.post(f"{BASE_URL}/admin/events/{evJul1_id}/moment/trigger", 
                                       headers=admin_headers)
    assert moment_trigger_resp.status_code == 200, f"Failed to trigger moment: {moment_trigger_resp.status_code} {moment_trigger_resp.text}"
    print(f"✅ Admin triggered moment for evJul1")
    
    # Step 7: U1 uploads moment capture (field name "file" SINGULAR)
    print("\n[STEP 7] U1 uploading moment capture to evJul1 (field name 'file')...")
    
    # Need to mark 'voy' first to upload moment
    voy_resp = requests.post(f"{BASE_URL}/events/{evJul1_id}/interest", 
                            headers=u1_headers, 
                            json={"status": "voy"})
    assert voy_resp.status_code == 200, f"Failed to mark voy: {voy_resp.status_code} {voy_resp.text}"
    
    img_bytes2 = create_test_image()
    files2 = {'file': ('test_moment.jpg', img_bytes2, 'image/jpeg')}
    
    moment_resp = requests.post(f"{BASE_URL}/events/{evJul1_id}/moment/upload", 
                               headers=u1_headers, 
                               files=files2)
    assert moment_resp.status_code == 200, f"Failed to upload moment: {moment_resp.status_code} {moment_resp.text}"
    moment_data = moment_resp.json()
    print(f"✅ U1 uploaded moment capture to evJul1")
    print(f"   Moment response: {moment_data}")
    
    # VERIFICATION PHASE
    print("\n" + "=" * 80)
    print("VERIFICATION PHASE")
    print("=" * 80)
    
    # Step 8: GET /api/me/wrapped (no month param) - should default to 2026-07
    print("\n[VERIFY 1] GET /api/me/wrapped (no month param)...")
    
    wrapped_resp = requests.get(f"{BASE_URL}/me/wrapped", headers=u1_headers)
    assert wrapped_resp.status_code == 200, f"Failed to get wrapped: {wrapped_resp.status_code} {wrapped_resp.text}"
    wrapped_data = wrapped_resp.json()
    
    print(f"\nWrapped data (default month):")
    print(f"  month: {wrapped_data.get('month')}")
    print(f"  has_data: {wrapped_data.get('has_data')}")
    print(f"  parties: {wrapped_data.get('parties')}")
    print(f"  photos: {wrapped_data.get('photos')}")
    print(f"  moments: {wrapped_data.get('moments')}")
    print(f"  gallery length: {len(wrapped_data.get('gallery', []))}")
    
    # Verify month == "2026-07"
    assert wrapped_data.get("month") == "2026-07", f"Expected month='2026-07', got '{wrapped_data.get('month')}'"
    print(f"✅ month == '2026-07'")
    
    # Verify has_data == true
    assert wrapped_data.get("has_data") == True, f"Expected has_data=true, got {wrapped_data.get('has_data')}"
    print(f"✅ has_data == true")
    
    # Verify parties == 2 (only July events, NOT August)
    assert wrapped_data.get("parties") == 2, f"Expected parties=2 (July events only), got {wrapped_data.get('parties')}"
    print(f"✅ parties == 2 (only July events, NOT August)")
    
    # Verify photos >= 1
    assert wrapped_data.get("photos", 0) >= 1, f"Expected photos>=1, got {wrapped_data.get('photos')}"
    print(f"✅ photos >= 1 (actual: {wrapped_data.get('photos')})")
    
    # Verify moments >= 1
    assert wrapped_data.get("moments", 0) >= 1, f"Expected moments>=1, got {wrapped_data.get('moments')}"
    print(f"✅ moments >= 1 (actual: {wrapped_data.get('moments')})")
    
    # Verify gallery is a list with length >= 2
    gallery = wrapped_data.get("gallery", [])
    assert isinstance(gallery, list), f"Expected gallery to be a list, got {type(gallery)}"
    assert len(gallery) >= 2, f"Expected gallery length>=2, got {len(gallery)}"
    print(f"✅ gallery is a list with length >= 2 (actual: {len(gallery)})")
    
    # Verify every item has non-empty "url" and "kind" in ["photo","moment"]
    has_photo = False
    has_moment = False
    for i, item in enumerate(gallery):
        assert "url" in item and item["url"], f"Gallery item {i} missing or empty 'url': {item}"
        assert "kind" in item and item["kind"] in ["photo", "moment"], f"Gallery item {i} has invalid 'kind': {item}"
        if item["kind"] == "photo":
            has_photo = True
        if item["kind"] == "moment":
            has_moment = True
    print(f"✅ Every gallery item has non-empty 'url' and 'kind' in ['photo','moment']")
    
    # Verify at least one kind=="photo" AND at least one kind=="moment"
    assert has_photo, "Gallery must have at least one item with kind='photo'"
    assert has_moment, "Gallery must have at least one item with kind='moment'"
    print(f"✅ Gallery has at least one kind='photo' AND at least one kind='moment'")
    
    print(f"\nGallery items:")
    for i, item in enumerate(gallery):
        print(f"  [{i}] kind={item['kind']}, url={item['url'][:60]}...")
    
    # Step 9: GET /api/me/wrapped?month=2026-08 - should have parties==1
    print("\n[VERIFY 2] GET /api/me/wrapped?month=2026-08...")
    
    wrapped_aug_resp = requests.get(f"{BASE_URL}/me/wrapped?month=2026-08", headers=u1_headers)
    assert wrapped_aug_resp.status_code == 200, f"Failed to get wrapped for Aug: {wrapped_aug_resp.status_code} {wrapped_aug_resp.text}"
    wrapped_aug_data = wrapped_aug_resp.json()
    
    print(f"\nWrapped data (2026-08):")
    print(f"  month: {wrapped_aug_data.get('month')}")
    print(f"  parties: {wrapped_aug_data.get('parties')}")
    
    # Verify parties == 1
    assert wrapped_aug_data.get("parties") == 1, f"Expected parties=1 for August, got {wrapped_aug_data.get('parties')}"
    print(f"✅ parties == 1 for August")
    
    # Step 10: GET /api/me/wrapped/year?year=2026 - should have parties==3
    print("\n[VERIFY 3] GET /api/me/wrapped/year?year=2026...")
    
    wrapped_year_resp = requests.get(f"{BASE_URL}/me/wrapped/year?year=2026", headers=u1_headers)
    assert wrapped_year_resp.status_code == 200, f"Failed to get wrapped year: {wrapped_year_resp.status_code} {wrapped_year_resp.text}"
    wrapped_year_data = wrapped_year_resp.json()
    
    print(f"\nWrapped year data (2026):")
    print(f"  year: {wrapped_year_data.get('year')}")
    print(f"  parties: {wrapped_year_data.get('parties')}")
    print(f"  gallery present: {'gallery' in wrapped_year_data}")
    print(f"  gallery length: {len(wrapped_year_data.get('gallery', []))}")
    
    # Verify parties == 3
    assert wrapped_year_data.get("parties") == 3, f"Expected parties=3 for year 2026, got {wrapped_year_data.get('parties')}"
    print(f"✅ parties == 3 for year 2026")
    
    # Verify gallery is present (list)
    year_gallery = wrapped_year_data.get("gallery")
    assert year_gallery is not None, "Expected 'gallery' field to be present in year wrapped"
    assert isinstance(year_gallery, list), f"Expected gallery to be a list, got {type(year_gallery)}"
    print(f"✅ gallery is present and is a list (length: {len(year_gallery)})")
    
    print("\n" + "=" * 80)
    print("✅ ALL WRAPPED VERIFICATION TESTS PASSED")
    print("=" * 80)
    
    return {
        "evJul1_id": evJul1_id,
        "evJul2_id": evJul2_id,
        "evAug_id": evAug_id,
        "u1_email": u1_email,
        "wrapped_july": wrapped_data,
        "wrapped_august": wrapped_aug_data,
        "wrapped_year": wrapped_year_data
    }

if __name__ == "__main__":
    try:
        result = test_wrapped_verification()
        print("\n✅ Test completed successfully!")
        print(f"\nTest summary:")
        print(f"  - Created 3 events (2 in July, 1 in August)")
        print(f"  - User marked 'estuve' on all 3 events")
        print(f"  - Uploaded 1 album photo and 1 moment capture to July event")
        print(f"  - Verified Wrapped for July (default): 2 parties, photos>=1, moments>=1, gallery>=2 items")
        print(f"  - Verified Wrapped for August: 1 party")
        print(f"  - Verified Wrapped for year 2026: 3 parties, gallery present")
    except AssertionError as e:
        print(f"\n❌ Test failed: {e}")
        exit(1)
    except Exception as e:
        print(f"\n❌ Unexpected error: {e}")
        import traceback
        traceback.print_exc()
        exit(1)
