"""In-process test for the event-link stability fix (no more 404 churn).

Reproduces the root cause: the SAME real party returning with a DIFFERENT
external_id (FourVenues new code / provider flip) must reuse the SAME event id
instead of creating a duplicate (which the reconcile step then deletes -> 404 on
old links). Also checks a genuinely different party on the same night is NOT
merged.

Run:  python3 event_link_stability_test.py   (requires backend/.env local Mongo)
"""
import asyncio
import sys

sys.path.insert(0, "/app/backend")
import server  # noqa: E402
from scrapers import ScrapedEvent  # noqa: E402

VENUE = {"id": "venue-test-fitz", "name": "Fitz Madrid", "city": "Madrid"}
DATE = "2099-09-10"

# Keep the test hermetic/fast: no ClubTickets network lookups.
server._affiliate_ct_slug_for_name = lambda *_a, **_k: None


def se(external_id, name):
    return ScrapedEvent(external_id=external_id, name=name, venue="Fitz Madrid",
                        date=DATE, time="23:00", genre="techno")


async def n_events():
    return await server.db.events.count_documents(
        {"scraper_venue_id": VENUE["id"], "date": DATE})


async def main():
    passed, failed = [], []

    def check(name, cond):
        (passed if cond else failed).append(name)
        print(("PASS" if cond else "FAIL"), "-", name)

    await server.db.events.delete_many({"scraper_venue_id": VENUE["id"]})

    # Run 1: party first seen with external_id FV-AAA -> CREATE
    r1 = await server._apply_scraped_event(VENUE, se("FV-AAA", "Jueves FITZ"), "batch1")
    check("run1 creates the party", r1 == "created")
    ev1 = await server.db.events.find_one(
        {"scraper_venue_id": VENUE["id"], "date": DATE}, {"_id": 0})
    id1 = ev1["id"] if ev1 else None
    check("run1 stored one event", await n_events() == 1)

    # Run 2: SAME party but DIFFERENT external_id (provider flip) -> must REUSE id
    r2 = await server._apply_scraped_event(VENUE, se("CT-BBB", "Jueves FITZ"), "batch2")
    check("run2 does NOT create a duplicate", r2 != "created")
    check("still exactly ONE event (no duplicate)", await n_events() == 1)
    ev2 = await server.db.events.find_one(
        {"scraper_venue_id": VENUE["id"], "date": DATE}, {"_id": 0})
    id2 = ev2["id"] if ev2 else None
    check("event id is STABLE across runs (link never breaks)", id1 and id1 == id2)
    check("external_id updated to current run (reconcile keeps it)",
          ev2 and ev2.get("external_id") == "CT-BBB")

    # Run 3: a genuinely DIFFERENT party same night -> must NOT merge (new event)
    r3 = await server._apply_scraped_event(
        VENUE, se("CT-CCC", "Fiesta Reggaeton Totalmente Distinta"), "batch3")
    check("different party same night creates a separate event", r3 == "created")
    check("now two distinct events for that night", await n_events() == 2)

    # Run 4: re-run the different party with yet another external_id -> still reuses
    r4 = await server._apply_scraped_event(
        VENUE, se("CT-DDD", "Fiesta Reggaeton Totalmente Distinta"), "batch4")
    check("different party re-scrape reuses its id (no churn)", r4 != "created")
    check("still two events total (no duplicates)", await n_events() == 2)

    await server.db.events.delete_many({"scraper_venue_id": VENUE["id"]})

    print(f"\nRESULT: {len(passed)} passed, {len(failed)} failed")
    if failed:
        print("FAILED:", failed)
        sys.exit(1)
    print("ALL EVENT-LINK-STABILITY TESTS PASSED")


if __name__ == "__main__":
    asyncio.run(main())
