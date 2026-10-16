# YKS RPG

Single-file study tracker in `index.html`. Serve it from the repository root:

```sh
python3 -m http.server 8000 --bind 127.0.0.1
```

## Optional Paragraph and Problem sessions

From 14 October 2026, default and custom main plans contain only basic lessons.
Paragraph (+40 XP) and Problem (+60 XP) remain optional Extra sessions: they
contribute to XP, Skill Tree, Boss, Weekly Quest and study statistics, with no
Rank or plan-compliance weight and no Morning Protocol connection. Existing
former main-task checks remain intact and retain their earned study XP; they
are not migrated into extra sessions. Plans before 14 October remain unchanged.

## Plan lesson notes

Students can add an optional note when adding a lesson in **Plan**, or edit/delete
notes below existing lessons. The daily task shows the same note, including after
completion. Swap labels identify the original planned lesson. Extra sessions,
Paragraph and Problem do not have plan notes.

Notes are stored as `state.planNotes[date][taskKey]` in the existing
`yks-xp-final-v1` localStorage record and student state JSON. Old saves default to
`planNotes: {}`. JSON export/import and the existing owner/coach state RPCs carry
notes without any Supabase migration, new table, column or RPC. Coach mode is
fully read-only. No separate coach-note API or write permission is used.

Removing a lesson also removes its note. Day/week resets remove notes for lessons
that leave the plan and retain notes for lessons still present. Existing plan
locks remain; notes can be edited independently of task completion.

## Browser tests

Requires Python Playwright and Chromium. Run from the repository root:

```sh
python tests/test_plan_notes_browser.py
```

Tests start a temporary loopback server, use ephemeral 360px browser contexts and
mock all Supabase RPCs with synthetic tokens and an in-memory student state.
No live Supabase writes occur. The browser library is downloaded with TLS
verification; `--supabase-js /path/to/supabase-browser.js` can use a local copy.
`--baseline /path/to/previous/index.html` also compares preserved state, earned
task XP and pre-14-October Rank/plan metrics with the previous app. Modern Rank
and plan-compliance changes are tested against the new lesson-only plan. Checks include note CRUD, task/Swap display,
lesson removal, resets, JSON round trips, reload, existing state sync, second
student device, coach read-only behavior, XSS safety and mobile overflow.
