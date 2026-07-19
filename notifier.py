#!/usr/bin/env python3
"""
Kipu Schedule Notifier — GitHub Actions edition, Google Calendar sync.

Runs on GH Actions cron. On each run:
  1. Scrapes ALL events on both Future and Past tabs of the client's Kipu portal.
  2. Syncs those events into the client's Google Calendar via a Service Account.
     - Insert new, update changed, delete Kipu-owned events no longer on Kipu.
     - Each managed event carries extendedProperties.private.kipu_key so we
       never touch events created by the user manually.
  3. On the FIRST run, also inserts the recurring daily "standing events"
     (meals, gym, etc. — see config.json) as ours-forever events.

No SMS/text/email notifications are sent — calendar sync is the sole output.

Reminders are handled natively by Google Calendar per-event:
  * Kipu events: popup reminder (minutes set by "reminder_minutes" in
    config.json), except any name listed in "skip_reminder_names" -> no reminder.
  * Standing events (meals, gym, ...): no reminder.

All client-specific settings (portal URL, timezone, meal/gym times, etc.)
live in config.json next to this script — see SETUP.md. Nothing below this
line should need to change between clients.

Env vars (all from GitHub Secrets):
  KIPU_USER, KIPU_PASSWORD
  GCAL_SA_JSON        (full JSON contents of the service account key)
  GCAL_CALENDAR_ID    (this client's Google Calendar ID)
"""
import hashlib
import json
import logging
import os
import re
import sys
from datetime import datetime, timedelta
from pathlib import Path
try:
    from zoneinfo import ZoneInfo
except ImportError:
    from backports.zoneinfo import ZoneInfo

from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

# -----------------------------------------------------------------------------
# Config: secrets from env, everything else from config.json
# -----------------------------------------------------------------------------
def env(key, required=True, default=None):
    v = os.environ.get(key, default)
    if required and not v:
        sys.exit(f"missing required env var {key}")
    return v


CWD = Path.cwd()
CONFIG_PATH = CWD / "config.json"


def load_config():
    if not CONFIG_PATH.exists():
        sys.exit(f"missing {CONFIG_PATH} — see SETUP.md")
    try:
        raw = json.loads(CONFIG_PATH.read_text())
    except json.JSONDecodeError as e:
        sys.exit(f"config.json is not valid JSON: {e}")

    required_fields = ["kipu_base_url", "kipu_account_id"]
    missing = [f for f in required_fields if not raw.get(f) or "CHANGE" in str(raw.get(f))]
    if missing:
        # Not configured yet (e.g. the template repo itself, or a fresh copy
        # before setup is finished) — exit cleanly rather than failing the
        # scheduled run, since this is an expected state, not an error.
        print(f"config.json still has placeholder values for: {missing} — "
              f"skipping run until configured (see SETUP.md).")
        sys.exit(0)

    base_url = raw["kipu_base_url"].rstrip("/")
    return {
        "kipu_url": f"{base_url}/portal/sign_in",
        "kipu_appointments_url": f"{base_url}/portal/appointments?account_id={raw['kipu_account_id']}",
        "kipu_user": env("KIPU_USER"),
        "kipu_password": env("KIPU_PASSWORD"),
        "gcal_sa_json": env("GCAL_SA_JSON"),
        "gcal_calendar_id": env("GCAL_CALENDAR_ID"),
        "timezone": raw.get("timezone", "America/Denver"),
        "skip_reminder_names": raw.get("skip_reminder_names", []),
        "reminder_minutes": raw.get("reminder_minutes", 30),
        "default_event_minutes": raw.get("default_event_minutes", 60),
        "short_event_minutes": raw.get("short_event_minutes", 15),
        "short_event_hint": raw.get("short_event_hint", ""),
        "two_hour_slots": set(raw.get("two_hour_slots", [])),
        "standing_events": [
            (e["name"], e["start"], e["end"]) for e in raw.get("standing_events", [])
        ],
    }


CFG = load_config()

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("kipu-notifier")


# -----------------------------------------------------------------------------
# Scrape (full history)
# -----------------------------------------------------------------------------
def _strip_instructor(title, provider):
    if not provider:
        return title
    first_seg = provider.split(",", 1)[0].strip()
    parts = first_seg.split()
    for n in range(min(len(parts), 3), 0, -1):
        prefix = " ".join(parts[:n])
        if title.startswith(prefix + " "):
            return title[len(prefix):].strip()
        if title == prefix:
            return "(private)"
    return title


def _parse_location(title):
    m = re.search(r"\bin the (.+?)(?:\s*\(|$)", title, re.IGNORECASE)
    if m:
        return m.group(1).strip()
    m = re.search(r"\(Location\s*:\s*([^)]+)\)", title, re.IGNORECASE)
    if m:
        return m.group(1).strip()
    m = re.search(r"\bin (?!the\b)([A-Z][^,]+)$", title)
    if m:
        return m.group(1).strip()
    return ""


def _parse_row(cells):
    if len(cells) < 6:
        return None
    date_idx = None
    for i, c in enumerate(cells):
        if re.fullmatch(r"\d{2}/\d{2}/\d{4}", c):
            date_idx = i
            break
    if date_idx is None:
        return None
    try:
        date_str = cells[date_idx]
        time_str = cells[date_idx + 1]
        provider = cells[date_idx + 3] if len(cells) > date_idx + 3 else ""
        title = cells[date_idx + 4] if len(cells) > date_idx + 4 else ""
        if not title:
            title = cells[date_idx + 5] if len(cells) > date_idx + 5 else ""
    except IndexError:
        return None
    if not (date_str and time_str and title):
        return None
    clean = _strip_instructor(title.strip(), provider.strip())
    return {
        "date": date_str,
        "time": time_str.strip(),
        "title": clean,
        "location": _parse_location(clean),
    }


def scrape_all_events():
    from playwright.sync_api import sync_playwright
    events = []
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        try:
            context = browser.new_context()
            page = context.new_page()
            page.set_default_timeout(60000)

            log.info("navigating to sign-in")
            page.goto(CFG["kipu_url"], wait_until="networkidle")
            page.get_by_label("Email").fill(CFG["kipu_user"])
            page.get_by_label("Password").fill(CFG["kipu_password"])
            page.get_by_role("button", name="Sign In").click()
            page.wait_for_url("**/portal", timeout=60000)
            log.info("logged in")

            page.goto(CFG["kipu_appointments_url"], wait_until="networkidle")

            def get_visible_rows():
                """Return tbody rows from the visible (active tab) table only.
                Vuetify keeps both Future and Past tables in the DOM; we must
                filter to only the visible one to avoid double-scraping and
                to hit the correct pagination buttons."""
                tables = page.query_selector_all("table")
                for t in tables:
                    if t.is_visible():
                        return t.query_selector_all("tbody tr")
                return []

            def get_visible_button(aria_label):
                """Return the visible :not([disabled]) button matching aria_label,
                or None. Filters to visible ones so we don't try to click a
                hidden button in the inactive tab (which times out)."""
                btns = page.query_selector_all(f"button[aria-label='{aria_label}']:not([disabled])")
                for b in btns:
                    if b.is_visible():
                        return b
                return None

            def wait_for_data_rows(label, timeout=30000):
                deadline = datetime.now().timestamp() + (timeout / 1000)
                while datetime.now().timestamp() < deadline:
                    rows = get_visible_rows()
                    if rows:
                        return len(rows)
                    page.wait_for_timeout(500)
                log.warning("wait_for_data_rows(%s) timed out", label)
                return 0

            def scrape_visible_page(label):
                rows = get_visible_rows()
                added = 0
                for row in rows:
                    cells = [c.inner_text().strip() for c in row.query_selector_all("td")]
                    parsed = _parse_row(cells)
                    if parsed:
                        events.append(parsed)
                        added += 1
                log.info("  %s: %d rows -> %d events", label, len(rows), added)
                return len(rows)

            def paginate_and_scrape(label):
                page_num = 1
                while True:
                    scrape_visible_page(f"{label} page {page_num}")
                    next_btn = get_visible_button("Next page")
                    if not next_btn:
                        break
                    try:
                        next_btn.click(timeout=8000)
                        page.wait_for_timeout(1200)
                    except Exception as e:
                        log.warning("next page click failed on %s p%d: %s", label, page_num, e)
                        break
                    page_num += 1
                    if page_num > 60:
                        break
                log.info("%s: scraped %d pages", label, page_num)

            # ---------- FUTURE tab (default when we land on appointments page) ----------
            log.info("scraping Future tab")
            page.goto(CFG["kipu_appointments_url"], wait_until="networkidle")
            wait_for_data_rows("Future initial")
            paginate_and_scrape("Future")

            # ---------- PAST tab ----------
            log.info("scraping Past tab")
            # Click Past; verify aria-selected becomes true so we know the swap happened.
            switched = False
            for attempt in range(4):
                try:
                    past_tab = page.get_by_role("tab", name="Past")
                    past_tab.wait_for(state="visible", timeout=8000)
                    past_tab.click()
                except Exception as e:
                    log.warning("Past tab click attempt %d: %s", attempt, e)
                    page.wait_for_timeout(1500)
                    continue
                page.wait_for_timeout(2500)
                try:
                    aria = past_tab.get_attribute("aria-selected")
                    if aria == "true":
                        switched = True
                        break
                except Exception:
                    pass
            if not switched:
                log.warning("could not confirm Past tab active; scraping whatever is visible")

            n_rows = wait_for_data_rows("Past initial")
            if n_rows == 0:
                log.error("no rows in Past tab; skipping backfill")
            else:
                # Walk forward through all Past pages. Past is ascending oldest→newest.
                # We do NOT use Last-page-jump + backward walk because Vuetify keeps
                # both tab tables in the DOM and the hidden Future pagination buttons
                # intercept clicks.
                paginate_and_scrape("Past")
        finally:
            browser.close()

    # Dedup on (date, time, title) — keeps first occurrence
    seen = set()
    unique = []
    for ev in events:
        k = (ev["date"], ev["time"], ev["title"])
        if k in seen:
            continue
        seen.add(k)
        unique.append(ev)
    return unique


# -----------------------------------------------------------------------------
# Calendar helpers
# -----------------------------------------------------------------------------
def calendar_service():
    """Build the Google Calendar service from the SA JSON in the env."""
    info = json.loads(CFG["gcal_sa_json"])
    creds = service_account.Credentials.from_service_account_info(
        info, scopes=["https://www.googleapis.com/auth/calendar"]
    )
    return build("calendar", "v3", credentials=creds, cache_discovery=False)


def parse_time_to_minutes(t):
    try:
        dt = datetime.strptime(t.strip().lower(), "%I:%M %p")
        return dt.hour * 60 + dt.minute
    except ValueError:
        return 0


def parse_date_mmddyyyy(s):
    try:
        return datetime.strptime(s, "%m/%d/%Y").date()
    except ValueError:
        return None


def kipu_key(ev):
    """Stable ID for a Kipu event — used to match calendar events on subsequent runs."""
    raw = f"{ev['date']}|{ev['time']}|{ev['title']}"
    return hashlib.sha1(raw.encode()).hexdigest()[:16]


def event_duration_minutes(title, time_str=""):
    if CFG["short_event_hint"] and CFG["short_event_hint"].lower() in title.lower():
        return CFG["short_event_minutes"]
    if time_str.strip().lower() in CFG["two_hour_slots"]:
        return 120
    return CFG["default_event_minutes"]


def event_should_remind(title):
    return not any(s in title for s in CFG["skip_reminder_names"])


def build_calendar_body(ev, tz_name):
    start_date = parse_date_mmddyyyy(ev["date"])
    if not start_date:
        return None
    mins = parse_time_to_minutes(ev["time"])
    start_dt = datetime(start_date.year, start_date.month, start_date.day, mins // 60, mins % 60)
    dur = event_duration_minutes(ev["title"], ev["time"])
    end_dt = start_dt + timedelta(minutes=dur)
    body = {
        "summary": ev["title"],
        "start": {"dateTime": start_dt.isoformat(timespec="seconds"), "timeZone": tz_name},
        "end":   {"dateTime": end_dt.isoformat(timespec="seconds"),   "timeZone": tz_name},
        "extendedProperties": {"private": {"kipu": "1", "kipu_key": kipu_key(ev)}},
    }
    loc = ev.get("location") or ""
    if loc:
        body["location"] = loc
    if event_should_remind(ev["title"]):
        body["reminders"] = {"useDefault": False, "overrides": [{"method": "popup", "minutes": CFG["reminder_minutes"]}]}
    else:
        body["reminders"] = {"useDefault": False, "overrides": []}
    return body


def list_managed_events(service, calendar_id):
    """Fetch all events flagged as ours (kipu=1) from the calendar."""
    out = {}
    page_token = None
    while True:
        resp = service.events().list(
            calendarId=calendar_id,
            privateExtendedProperty="kipu=1",
            maxResults=2500,
            pageToken=page_token,
            singleEvents=False,
            showDeleted=False,
        ).execute()
        for e in resp.get("items", []):
            props = e.get("extendedProperties", {}).get("private", {})
            k = props.get("kipu_key")
            if k:
                out[k] = e
        page_token = resp.get("nextPageToken")
        if not page_token:
            break
    return out


def needs_update(existing, desired):
    """Cheap comparison — did summary/start/end/location/reminders change?"""
    def norm_dt(x):
        return (x.get("dateTime") or x.get("date") or "").split("+")[0]
    if existing.get("summary") != desired.get("summary"):
        return True
    if norm_dt(existing.get("start", {})) != norm_dt(desired["start"]):
        return True
    if norm_dt(existing.get("end", {})) != norm_dt(desired["end"]):
        return True
    if (existing.get("location") or "") != (desired.get("location") or ""):
        return True
    ex_rem = existing.get("reminders", {}).get("overrides") or []
    de_rem = desired.get("reminders", {}).get("overrides") or []
    if [(r.get("method"), r.get("minutes")) for r in ex_rem] != \
       [(r.get("method"), r.get("minutes")) for r in de_rem]:
        return True
    return False


# -----------------------------------------------------------------------------
# Standing events (meals, gym, etc.) — recurring daily, no reminders. Idempotent.
# Defined per-client in config.json under "standing_events".
# -----------------------------------------------------------------------------
def _standing_key(name, start):
    """Stable key for a standing event, distinct per (name, start)."""
    slug = f"{name}-{start.replace(':', '')}".lower()
    return f"standing-{slug}"


def sync_standing_events(service, calendar_id, tz_name):
    """Create any standing events that aren't already on the calendar.

    Dedup logic is by (summary, start hour:min) instead of by kipu_key, so
    that any pre-existing standing events (including ones created under an
    older key format) are recognized. Never modifies existing events.
    """
    existing = list_managed_events(service, calendar_id)
    existing_by_sig = {}
    dup_ids = []
    standing_names = {name for (name, _, _) in CFG["standing_events"]}
    for k, e in existing.items():
        props = e.get("extendedProperties", {}).get("private", {}) or {}
        is_standing = (
            props.get("standing") == "1"
            or props.get("meal") == "1"
            or bool(e.get("recurrence"))
            or (e.get("summary", "").strip() in standing_names and bool(e.get("recurrence")))
        )
        if not is_standing:
            continue
        summ = (e.get("summary") or "").strip()
        st = e.get("start", {}).get("dateTime", "")
        hhmm = ""
        if "T" in st:
            hhmm = st.split("T", 1)[1][:5]
        sig = (summ, hhmm)
        if not summ or not hhmm:
            continue
        if sig in existing_by_sig:
            dup_ids.append(e["id"])
        else:
            existing_by_sig[sig] = e

    # Safety: never delete more than 10 events in one run.
    if len(dup_ids) > 10:
        log.error("REFUSING to delete %d 'duplicate' events — safety cap. Log: %s",
                  len(dup_ids), dup_ids[:5])
        dup_ids = []

    for eid in dup_ids:
        try:
            service.events().delete(calendarId=calendar_id, eventId=eid).execute()
            log.info("deleted duplicate standing event id=%s", eid)
        except HttpError as e:
            log.warning("dup cleanup delete failed: %s", e)

    today = datetime.now(ZoneInfo(tz_name)).date()
    for name, start, end in CFG["standing_events"]:
        sig = (name, start)
        if sig in existing_by_sig:
            continue
        sh, sm = [int(x) for x in start.split(":")]
        eh, em = [int(x) for x in end.split(":")]
        start_dt = datetime(today.year, today.month, today.day, sh, sm)
        end_dt   = datetime(today.year, today.month, today.day, eh, em)
        body = {
            "summary": name,
            "start": {"dateTime": start_dt.isoformat(timespec="seconds"), "timeZone": tz_name},
            "end":   {"dateTime": end_dt.isoformat(timespec="seconds"),   "timeZone": tz_name},
            "recurrence": ["RRULE:FREQ=DAILY"],
            "reminders": {"useDefault": False, "overrides": []},
            "extendedProperties": {"private": {"kipu": "1", "standing": "1", "kipu_key": _standing_key(name, start)}},
        }
        try:
            service.events().insert(calendarId=calendar_id, body=body).execute()
            log.info("created standing event: %s @ %s", name, start)
        except HttpError as e:
            log.error("failed to create standing event %s @ %s: %s", name, start, e)


# -----------------------------------------------------------------------------
# Main
# -----------------------------------------------------------------------------
def sync_kipu_events(service, calendar_id, events, tz_name):
    """Insert/update/delete Kipu-managed events (non-standing) to match `events`."""
    existing = list_managed_events(service, calendar_id)
    # Filter out standing events (meals, gym) — never delete/update those from Kipu sync.
    existing = {k: e for k, e in existing.items()
                if not e.get("extendedProperties", {}).get("private", {}).get("standing")
                and not e.get("extendedProperties", {}).get("private", {}).get("meal")}

    desired_keys = set()
    inserted = updated = 0
    for ev in events:
        key = kipu_key(ev)
        desired_keys.add(key)
        body = build_calendar_body(ev, tz_name)
        if not body:
            continue
        if key in existing:
            if needs_update(existing[key], body):
                try:
                    service.events().update(
                        calendarId=calendar_id, eventId=existing[key]["id"], body=body
                    ).execute()
                    updated += 1
                except HttpError as e:
                    log.error("update failed for %s: %s", ev["title"], e)
        else:
            try:
                service.events().insert(calendarId=calendar_id, body=body).execute()
                inserted += 1
            except HttpError as e:
                log.error("insert failed for %s: %s", ev["title"], e)

    deleted = 0
    today = datetime.now(ZoneInfo(tz_name)).date()
    for key, e in existing.items():
        if key in desired_keys:
            continue
        # Only delete events dated TODAY or later. Never touch historical events
        # — the client's calendar is meant to be a persistent record of what they
        # attended, and Kipu prunes its Past tab over time.
        start_str = e.get("start", {}).get("dateTime") or e.get("start", {}).get("date") or ""
        try:
            ev_date = datetime.fromisoformat(start_str.split("T")[0]).date()
        except ValueError:
            continue
        if ev_date < today:
            continue
        try:
            service.events().delete(calendarId=calendar_id, eventId=e["id"]).execute()
            deleted += 1
        except HttpError as err:
            log.error("delete failed: %s", err)

    log.info("sync: %d inserted, %d updated, %d deleted (%d desired)",
             inserted, updated, deleted, len(desired_keys))
    return inserted, updated, deleted


def main():
    tz_name = CFG["timezone"]
    tz = ZoneInfo(tz_name)
    now = datetime.now(tz)
    log.info("=== run at %s ===", now.isoformat(timespec="seconds"))

    # 1) Scrape
    try:
        events = scrape_all_events()
    except Exception as e:
        log.exception("scrape failed: %s", e)
        sys.exit(1)
    log.info("scraped %d unique events", len(events))

    # 2) Calendar sync
    service = calendar_service()
    calendar_id = CFG["gcal_calendar_id"]

    # Idempotently ensure standing events (meals, gym, ...) exist. Never
    # touches existing ones — only inserts missing.
    sync_standing_events(service, calendar_id, tz_name)

    ins, upd, dele = sync_kipu_events(service, calendar_id, events, tz_name)

    log.info("done: sync %d/%d/%d", ins, upd, dele)


if __name__ == "__main__":
    main()
