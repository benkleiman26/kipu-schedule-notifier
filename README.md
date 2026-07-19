# Kipu Schedule Notifier

Scrapes a client's Kipu portal appointment schedule and syncs it into a
Google Calendar, on autopilot via GitHub Actions. No text/email
notifications — the calendar itself (with its native popup reminders) is
the only output.

- **First time setting this up for a new client?** Follow [SETUP.md](SETUP.md) start to finish — it's the only doc you need.
- **Just tweaking an existing client's schedule** (meal times, gym times, timezone, which events skip reminders)? Edit `config.json` in that client's repo directly — see the "Editing a client's schedule later" section at the bottom of SETUP.md.
- `notifier.py` should not need to change per client — all client differences live in `config.json`.
