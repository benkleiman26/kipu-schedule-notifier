# Setup guide

No coding needed — just following steps and clicking buttons. Budget about
20-30 minutes. Every account you create in this guide is **your own** —
nothing is shared with anyone else, including whoever gave you this link.

## Before you start

You'll need:

- An email address you can access right now (for creating accounts).
- A Google account (Gmail) — the one whose calendar you want your schedule to show up on. If you don't have one, go create a free one first at [accounts.google.com/signup](https://accounts.google.com/signup).
- Your Kipu portal login (the username/email and password you use to log into your appointments portal).

You'll create a free GitHub account along the way if you don't have one —
GitHub is where the "robot" that checks your schedule actually lives and
runs, on a timer, even while your phone is off.

---

## Step 1 — Get your own copy of this tool

1. If you don't already have one, create a free GitHub account at [github.com/signup](https://github.com/signup).
2. Go to this repository's page and click the green **"Use this template"** button near the top right, then **"Create a new repository."**
3. Give it any name (e.g. "my-schedule"). Under "Visibility," choose **Private** — this keeps your schedule details just between you and your two accounts. Click **Create repository**.

You now have your own private copy. Everything from here happens inside
*your* copy, not the original.

---

## Step 2 — Create a "robot helper" account for Google Calendar

Google Calendar won't let a script add events to your calendar using your
real password (that's a good thing — it's more secure). Instead, it uses a
"service account": a special robot account that can only touch calendars
you specifically choose to share with it, and nothing else on your Google
account.

1. Go to [console.cloud.google.com](https://console.cloud.google.com) and sign in with your Google account. Accept any terms if prompted.
2. At the top, click the project dropdown and **"New Project."** Name it anything (e.g. "my-schedule"). Click **Create**, then make sure it's selected in the dropdown.
3. In the search bar at the top, type **"Google Calendar API"**, click it, then click **Enable**.
4. In the left menu, go to **APIs & Services -> Credentials**. Click **Create Credentials -> Service account**. Give it any name (e.g. "schedule-robot"), click **Create and Continue**, then click **Done** (you can skip the optional steps).
5. Click on the service account you just created. Go to the **Keys** tab -> **Add Key -> Create new key -> JSON** -> **Create**. A `.json` file downloads to your computer — this is a password, treat it like one. You'll paste its contents in Step 4.
6. On that same service account page, copy its **email address** (looks like `something@your-project.iam.gserviceaccount.com`) — you'll need it in the next step.

---

## Step 3 — Create your calendar and connect the robot to it

1. Open [Google Calendar](https://calendar.google.com) in your Google account.
2. On the left, next to "Other calendars," click **+ -> Create new calendar**. Name it something like "My Schedule." Click **Create calendar**.
3. Go back to the calendar list, hover over your new calendar, click the **3-dot menu -> Settings and sharing**.
4. Scroll to **"Share with specific people or groups" -> Add people**. Paste in the robot's email address from Step 2, set permission to **"Make changes to events,"** and send/save.
5. Scroll down further to **"Integrate calendar"** and copy the **Calendar ID** (looks like a long string ending in `@group.calendar.google.com`). You'll need this in Step 4.

---

## Step 4 — Give your copy of the tool your logins

Back in your GitHub repo from Step 1:

1. Click **Settings** (top tab of the repo) -> **Secrets and variables -> Actions** -> **New repository secret**.
2. Add these four, one at a time (exact names matter, values are just pasted in):

| Name | Value |
|---|---|
| `KIPU_USER` | your Kipu portal login email |
| `KIPU_PASSWORD` | your Kipu portal password |
| `GCAL_SA_JSON` | open the `.json` file from Step 2 in a text editor, select all, copy, and paste the whole thing here |
| `GCAL_CALENDAR_ID` | the Calendar ID from Step 3 |

These are stored encrypted by GitHub — nobody can read them back, including
you, once saved (which is why it's worth double-checking each one before
saving).

---

## Step 5 — Tell it your portal address and daily schedule

1. In your repo, click on `config.json`, then the pencil (edit) icon.
2. Fill in:
   - `kipu_base_url` — log into your Kipu portal in a browser and look at the address bar. It'll look like `https://XXXXX.kipuworks.com/...` — copy everything up through `.kipuworks.com` (no trailing slash).
   - `kipu_account_id` — after logging in, go to your Appointments page. The address bar will show `...account_id=123456` at the end — copy just that number.
   - `timezone` — your local timezone, e.g. `America/Denver` or `America/New_York`. ([Full list here](https://en.wikipedia.org/wiki/List_of_tz_database_time_zones) if you're unsure of the exact name.)
   - `standing_events` — any daily fixed times you want on your calendar automatically (meals, gym, etc.), in 24-hour time. Add, remove, or edit these freely — each one is `{"name": "...", "start": "HH:MM", "end": "HH:MM"}`.
3. Everything else in the file can be left as-is. Scroll down and click **Commit changes**.

---

## Step 6 — Turn it on

1. Click the **Actions** tab. GitHub shows a message about workflows being disabled — click **"I understand my workflows, go ahead and enable them."**
2. Click into **"Kipu Schedule Notifier"** on the left, then **"Run workflow"** (top right) -> **Run workflow**. This runs it right now instead of waiting.
3. Wait about a minute, then refresh. A green checkmark means it worked — open your Google Calendar and your schedule should be there.
4. A red X means something's wrong — click into the run to read the error, and check the Troubleshooting section below.

From here it runs automatically, roughly every 30 minutes during the day,
with no further action needed.

---

## Step 7 — See it on your phone

Your new calendar already lives inside your Google account, so it should
show up automatically in the Google Calendar app on your phone (make sure
you're signed into the same Google account). Reminders will pop up as
regular phone notifications, exactly like any other calendar event.

---

## Troubleshooting

- **Red X on the Actions run, mentions `config.json`:** usually a typo — reopen `config.json` and check `kipu_base_url` and `kipu_account_id` match exactly what you saw in your browser.
- **Red X, mentions sign-in or login failing:** double check the `KIPU_USER` / `KIPU_PASSWORD` secrets — re-add them if unsure, since you can't view a saved secret's value to check it.
- **Red X, mentions "calendar" or "403"/"404":** the robot account probably isn't shared on your calendar yet, or the Calendar ID is wrong — redo Step 3.
- **It ran successfully but nothing shows up on my calendar:** confirm you're looking at the *new* calendar you created in Step 3 (not your main personal calendar) — it appears as a separate line under "My calendars" in the Google Calendar sidebar.
- **Still stuck:** the Actions run log (Step 6) shows the exact error text — that's the most reliable clue for what's wrong.

## Changing your schedule later

Edit `config.json` again anytime (pencil icon, commit changes) — no need to
touch anything else. The next scheduled run (or a manual "Run workflow")
picks up the change automatically.
