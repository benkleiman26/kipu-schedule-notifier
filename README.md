# Kipu Schedule Notifier

Automatically syncs your appointments from a Kipu patient portal into your
own Google Calendar — so your schedule shows up on your phone with normal
calendar reminders, instead of you having to check the portal yourself.

- Runs on a timer in the background (every ~30 minutes during the day) and keeps your calendar up to date on its own.
- Nobody else can see your schedule or your portal login — everything lives in **your own** GitHub account and **your own** Google account. This tool's author never has access to your credentials or your calendar.
- No coding required, but it does take about 20-30 minutes the first time, working through Google and GitHub's setup screens.

**New here? Start with [SETUP.md](SETUP.md)** — it walks through everything
step by step, written for someone who's never used GitHub or Google Cloud
before.

## Why does this need my portal password at all?

Kipu portals don't offer a way to "connect" to another app the safe way
(like the "Sign in with Google" buttons you may have seen elsewhere) — the
only way to read your schedule is to actually log in and look at the page,
the same way you would in a browser. That's what this tool automates. Your
login is stored as an encrypted secret in your own private GitHub repo,
used only to log in and read your own schedule, and is never sent anywhere
else or visible to anyone (including the person who shared this tool with
you).

## If something's not working

Open your repo's **Actions** tab and click into the most recent run — it
shows a log of exactly what happened, including any error message. Most
problems trace back to a typo in `config.json` or a secret value that got
copied wrong. SETUP.md has a troubleshooting section with the most common
fixes.
