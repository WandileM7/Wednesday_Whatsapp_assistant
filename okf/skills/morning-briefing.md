---
name: morning-briefing
description: Compose the user's morning briefing from calendar, email and reminders
---

When asked for a morning briefing (or "what's my day look like"):

1. Call `get_time` for today's date.
2. Call the calendar tool for today's events; note the first meeting time.
3. Call the email tool for unread messages; mention only ones that look
   important (people the user knows, deadlines, questions) — never bulk mail.
4. Call `list_reminders` for anything due today.
5. Deliver it as 3–5 spoken-style sentences: schedule first, then email,
   then reminders. Lead with the thing that happens soonest. No markdown,
   no lists — this is read aloud.

Pitfalls: don't invent events when the calendar is empty — say it's clear;
don't read out email addresses or URLs.
