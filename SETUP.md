# Setup guide — onboarding a new client

Total time: ~15 minutes per client, after the one-time Google Cloud step
below is done once.

## One-time: Google service account (skip if you already have one)

If you've already set this up for a previous client (e.g. the original
APN Lodge instance), **reuse that same service account** — you do not need
a new one per client. A single service account can be granted access to
any number of Google Calendars. Skip to "Per-client setup" below.

Otherwise, do this once:

1. Go to [console.cloud.google.com](https://console.cloud.google.com) and create a project (or use an existing one).
2. Enable the **Google Calendar API** for that project (APIs & Services -> Enable APIs -> search "Google Calendar API" -> Enable).
3. Create a **Service Account** (APIs & Services -> Credentials -> Create Credentials -> Service Account). Any name is fine, e.g. "kipu-notifier".
4. Open the service account -> Keys tab -> Add Key -> Create new key -> JSON. This downloads a `.json` file — keep it somewhere safe. You'll paste its full contents into GitHub Secrets per client (below).
5. Note the service account's email address (looks like `something@your-project.iam.gserviceaccount.com` — it's the `client_email` field in that JSON file). You'll need it every time you create a new client calendar.

## Per-client setup

### 1. Create the repo

- On GitHub, open this template repo and click **"Use this template" -> "Create a new repository"**.
- Name it something like `clientname-schedule`. Can be private.

### 2. Get the client's Kipu portal details

You need three things, all from the client (or whoever manages their Kipu
account):

- Their Kipu **login email and password**.
- Their portal's **base URL** — log into their portal once and look at the
  address bar. It'll look like `https://XXXXX.kipuworks.com/portal/...`.
  The base URL is everything up to `.kipuworks.com`.
- Their **account ID** — after logging in, go to the Appointments page. The
  URL will look like `.../portal/appointments?account_id=123456`. The
  number after `account_id=` is what you need.

### 3. Create the client's Google Calendar

- In a Google account (yours or the client's — your call), create a new
  calendar: Google Calendar -> "+" next to "Other calendars" -> Create new
  calendar. Name it e.g. "Jane's Schedule".
- Open that calendar's **Settings and sharing**.
- Under "Share with specific people", add the **service account's email**
  (from the one-time setup above) with **"Make changes to events"**
  permission.
- Scroll down to "Integrate calendar" and copy the **Calendar ID** (looks
  like `abc123...@group.calendar.google.com`).

### 4. Add GitHub Secrets

In the new repo: **Settings -> Secrets and variables -> Actions -> New
repository secret**. Add these four:

| Secret name | Value |
|---|---|
| `KIPU_USER` | client's Kipu login email |
| `KIPU_PASSWORD` | client's Kipu login password |
| `GCAL_SA_JSON` | paste the **entire contents** of the service account JSON file (same one for every client) |
| `GCAL_CALENDAR_ID` | the Calendar ID you copied in step 3 |

### 5. Edit `config.json`

In the new repo, edit `config.json` directly on GitHub (pencil icon) or
locally. Fill in:

- `client_name` — just a label, doesn't affect behavior.
- `kipu_base_url` and `kipu_account_id` — from step 2.
- `timezone` — an [IANA timezone name](https://en.wikipedia.org/wiki/List_of_tz_database_time_zones) like `America/Denver` or `America/New_York`.
- `standing_events` — the client's fixed daily schedule (meals, gym, etc.). Add, remove, or retime entries freely — each is `{"name": ..., "start": "HH:MM", "end": "HH:MM"}` in 24-hour time.
- The rest (`reminder_minutes`, `skip_reminder_names`, `two_hour_slots`, etc.) are optional tuning — safe to leave as-is for a normal setup. See inline meaning below.

  - `reminder_minutes` — how many minutes before each event the calendar pops up a reminder.
  - `skip_reminder_names` — event titles (partial match) that should get NO reminder at all.
  - `two_hour_slots` — specific start times (like `"08:00 am"`) that should always be treated as 2-hour-long events instead of the default.
  - `default_event_minutes` / `short_event_minutes` / `short_event_hint` — fallback event length, and a shorter length for any event whose title contains `short_event_hint`.

Commit the change.

### 6. Enable Actions and do a test run

- Go to the **Actions** tab in the new repo. GitHub disables Actions by
  default on repos created from a template — click **"I understand my
  workflows, go ahead and enable them"**.
- Click into the **"Kipu Schedule Notifier"** workflow -> **"Run workflow"**
  -> Run workflow. This triggers it immediately instead of waiting for the
  next scheduled time.
- Watch the run. Green check = success. Then open the client's Google
  Calendar and confirm events showed up.
- If it fails, click into the run to see the error log — most failures are
  a typo in `config.json` or a wrong secret value.

### 7. Give the client access to their calendar

- In Google Calendar settings for that calendar, share it with the
  client's own Google account (view access is enough — they don't need to
  edit it), or send them the public iCal/embed link if you'd rather not
  require a Google account.
- Once shared, all reminders/notifications are whatever the client sets up
  natively in their own Google Calendar app (push notifications, email,
  etc.) — nothing further to configure on your end.

That's it — the workflow now runs automatically on the schedule defined in
`.github/workflows/notifier.yml` (every 30 min during the day by default).

## Adjusting the run schedule

The default schedule in `.github/workflows/notifier.yml` runs roughly every
30 minutes from 7am-2:30pm Mountain Time, plus 3pm and 8pm. GitHub Actions
cron is always in UTC, so to change the times for a client in a different
timezone or with different needs, edit the `cron:` lines. A quick way:
search "crontab generator" and convert your desired local time to UTC,
remembering to account for daylight saving if applicable.

## Editing a client's schedule later

No code changes needed — just edit that client's `config.json` on GitHub
(pencil icon, top right of the file view) and commit. The next scheduled
run (or a manual "Run workflow") picks up the change automatically.
