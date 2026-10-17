# YKS RPG

Single-file study tracker in `index.html`. Serve it from the repository root:

```sh
python3 -m http.server 8000 --bind 127.0.0.1
```

## Tasks and dated XP

Paragraph and Problem are never automatically added to the modern plan. They can
be planned explicitly (and then count toward Rank) or checked as Extra sessions
(with no Rank weight). The planner offers grouped General, Daily Study and Branch
Exam tasks with XP shown for the selected date. Exact duplicates are prevented;
normal Mathematics/Turkish study and their branch exams can coexist.

Historical IDs keep their meaning: `mat` is the Mathematics branch exam, `tr` is
the Turkish branch exam, and `tyt` is the old general TYT analysis. New tasks use
`mathStudy`, `turkishStudy`, `generalExam` and `generalExamAnalysis`.

`xpFor(date, taskKey)` applies the final economy from **17 October 2026**:

| Task | XP |
| --- | ---: |
| Paragraph | 60 |
| Problem / Mathematics study | 100 |
| Geometry | 125 |
| Physics | 115 |
| Chemistry | 100 |
| Biology | 90 |
| Turkish study | 85 |
| Grammar | 75 |
| TYT Geography / History | 65 |
| Mathematics branch exam | 120 |
| Turkish branch exam | 90 |
| General exam | 220 |
| General exam analysis | 160 |

The original base XP table remains intact for earlier dates. Original plans,
checks, swaps, balances, skills and histories are read without data migration.
Former mandatory Paragraph/Problem checks retain their study XP; when explicitly
planned they are counted once. Shop prices and existing bonuses are unchanged.

Plan and Swap use separate task pools. Swaps support normal/branch subject tasks
and retain the original slot's dated Rank weight while paying the incoming task's
dated XP. Paragraph, Problem and general exams are outside the Swap pool.

Extra sessions include all 15 planner choices, remain independent of main task
completion and display beside completed tasks with the EK badge. Mathematics and
Turkish Skills/Radar aggregate normal and branch work; general exams contribute
general XP, Boss and study statistics without awarding a subject Skill XP.

## Plan lesson notes

Students can add an optional note when adding a lesson in **Plan**, or edit/delete
notes below existing lessons. The daily task shows the same note, including after
completion. Swap labels identify the original planned lesson. All 15 planned
task kinds support notes, including Paragraph, Problem and general exams. Extra
sessions do not have plan notes.

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
XP/balance/spending, Rank, history, skills and statistics through 16 October with
the previous app. Separate 17 October checks exercise all new task kinds, dated
XP, grouped options, notes, weighted Rank, Swap, Extras and normal/branch Skills. Checks include note CRUD, task/Swap display,
lesson removal, resets, JSON round trips, reload, existing state sync, second
student device, coach read-only behavior, XSS safety and mobile overflow.
