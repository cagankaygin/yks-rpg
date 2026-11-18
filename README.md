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
task kinds support notes, including Paragraph, Problem and general exams. Past
Extra sessions also reuse the note editor and store notes under `extra:<taskKey>`.

Notes are stored as `state.planNotes[date][taskKey]` in the existing
`yks-xp-final-v1` localStorage record and student state JSON. Old saves default to
`planNotes: {}`. JSON export/import and the existing owner/coach state RPCs carry
notes without any Supabase migration, new table, column or RPC. Coach mode is
fully read-only. No separate coach-note API or write permission is used.

Removing a lesson also removes its note after confirmation. Clearing a day/week
preserves Extra-session notes. Notes can be edited independently of completion.

## Editing historical days

Choose a past date in **Günlük**, then use **Seçili günün planını düzenle** to open
that week in the existing planner. Add lessons, reorder/remove slots, and edit
notes there; completion and Extra checkboxes stay on the selected daily screen.
Only the selected day's plan/checks are changed. Today's and future plans retain
their existing completion/Swap/ticket/shield locks. Coach mode can navigate past
plans and view records but cannot edit them.

Legacy days retain their defaults, task IDs, XP and count-based Rank until
explicitly edited. A saved empty plan stays empty rather than restoring default
tasks. No existing checks or time records are migrated on load. Deletion and
day/week clearing require confirmation; removing a swapped slot clears its
completion key and Swap for that day without affecting other slots.

Recorded sessions can be edited from **Seçili günün oturumlarını göster**;
**Süre ekle** records missing main/Extra study time using the same session store.
Editing preserves the session ID and original timestamps. Manual entries carry
an optional `manual: true` marker and are shown as manual records rather than
measured clock times. All sessions remain even when their lesson is removed.
Time changes update daily/weekly totals without changing XP or a running timer.

XP, Rank, streak, Comeback and perfect-week bonuses continue to be derived from
current checks and plans. Previously claimed chests/achievements, purchases and
ticket/shield records are retained; an edit never resets their claim guards.
Local saves, JSON backups and existing Coach Sync transport these records.

Run the backdated-edit regression suite with Python Playwright and Chromium:

```sh
python tests/test_past_plan_editing.py
```

The optional `--supabase-js` argument uses a local TLS-verified browser library.
The suite uses isolated fixtures, mocked cloud RPCs and a 360px viewport.

## Lock-In, breaks and question difficulty (V3.34)

Lock-In has its own tab. Bilim, University and Home share the common rules; the
daily screen shows a small indicator for today's active mode. Existing dated
Lock-In records are retained. The owner can assign daily plan slot IDs to any
number of periods, choose where the 60-minute meal break belongs, and remove a
period after confirmation. The planner itself is never rewritten. Period
completion is derived from the existing daily checkboxes, including Swap and
duplicate lesson slots.

The shared timer supports 5-minute short, 25-minute period and 60-minute meal
breaks, including standalone breaks between finished sessions. Breaks remain
active after the target duration and show silent overrun time until ended.
`studyTimer.breakRunning` and `studyTimer.breaks` retain their own IDs, dates,
types, planned durations, timestamps, elapsed time and overruns. Net work remains
in the existing session records and excludes all paused time. Reload, backups
and Coach Sync preserve both stores; legacy untyped pauses still resume safely.
Neither working nor taking a break changes task completion or grants XP.

Closing Lock-In opens a self-assessment. Four common rules award 10, 10, 15 and
20 XP, at most once per rule/day across all environments and restarts (55 XP).
Home additionally offers “Günlük ders programım tamamlanmadan televizyon
izlemedim.” for 10 XP once per day, bringing the available daily total to 65 XP.
This `tv` rule is absent from Bilim/University checklists and rewards; both the
live ledger and import normalization reject TV claims from those environments.
Old evaluations without a TV field remain unchanged. Each active
Lock-In session has a unique evaluation ID. Repeated submissions or duplicate
imported IDs cannot multiply a reward or penalty. Confirming that the student
abandoned the plan to socialize deducts 1500 XP from the balance. That evaluation
cannot also award the social rule's 20 XP. Emergencies, health issues and forced
schedule changes are explicitly excluded; an unchecked exit has no penalty.

Evaluations live in `lockIn.days[date].evaluations`; periods and the chosen meal
position also stay on that day's record. The daily ledger deduplicates rule
rewards and evaluation IDs. Existing task XP, Rank, skills, Boss, quests,
purchase records and chest claims are unchanged. Lock-In rewards enter earned
XP, penalties enter spent XP, and weekly/long-term XP summaries include the net
change. The Lock-In tab and Statistics show the transaction reason and amount.

Question difficulty is optional metadata: `medium`, `hard` or `brutal`. Normal,
quick, mock-exam and mathematics-analysis entry forms offer the same choices.
Old questions stay unassigned until edited. Cards show a small difficulty badge
and an owner-only selector; a read-only difficulty filter narrows visible ready,
due and source question lists. Difficulty never changes review scheduling,
mastery, XP or the existing due/overdue colors. All new writes are guarded in
coach mode. No new storage key, Supabase table, schema or RPC is introduced.

Run the focused suite with Python Playwright and Chromium:

```sh
python tests/test_lockin_protocol.py
python tests/test_home_tv_rule.py
```

Use `--supabase-js /path/to/supabase-browser.js` to use a local TLS-verified
library. Tests use synthetic records, mocked RPCs, deterministic time and a
360px viewport; no live student data is accessed.

## All-course study timer (V3.33)

The existing timer picker includes the selected day's plan plus **TYT subjects**,
**AYT subjects**, **branch exams**, **general exams** and **analysis tasks**.
Choices reuse the planner/Extra task definitions and question-vault subject list;
an empty daily plan does not limit which subject can be timed. Duplicate and
swapped main-plan slots remain separately selectable.

The shared **Derslere göre süreler** summary shows each subject's selected-day
and weekly net time, including saved sessions and an active timer. It uses saved
lesson labels to retain the actual subject after a plan/Swap changes. Original
session IDs, timestamps and task keys are preserved; there is no data migration.
Existing Extra choices keep `extra:<taskKey>` keys, while vault-only subjects
use their existing subject IDs, such as `aytPhysics`.

Starting, pausing or finishing a timer never adds a planned lesson, checks a task
or grants XP. Completion, Rank, skills, Boss and rewards still follow their
existing rules. The same expanded catalog is available in the existing manual
session editor. Coach mode can view time summaries but cannot change records.

Run the focused browser tests with Python Playwright and Chromium:

```sh
python tests/test_timer_catalog.py
```

Use `--supabase-js /path/to/supabase-browser.js` for a local TLS-verified library.
Tests cover old records, reload, JSON backup, mocked cloud sync, mobile layout
and the absence of plan/completion/XP side effects.

## Extra-work timers

Every Extra-work row uses the existing study timer. Start, pause/resume and finish
are available beside the task, including completed Extras. The same choices also
appear in the main timer picker, even when there is no daily main plan.

There is one shared `studyTimer.running` record. Saved sessions retain the same
`day`, `taskKey`, `label`, `seconds`, `startedAt` and `endedAt` fields; Extra task
keys use the existing `extra:<taskKey>` namespace. Per-task totals, daily totals
and weekly totals sum those sessions, excluding paused time. Reload, JSON backup
and the existing Coach Sync state JSON carry them without a new storage key,
state schema or database change. Coach mode remains read-only.

Finishing a timer saves time only. XP still comes from the existing completion
checkbox once per Extra; timing the same completed Extra again does not grant
more XP. Checking a matching task can finish its timer after confirmation;
checking another task leaves the current timer running. Timer buttons are
outside checkbox labels to prevent accidental completion on mobile.

Run the focused timer tests with Python Playwright and Chromium:

```sh
python tests/test_extra_study_timer.py
```

Use `--supabase-js /path/to/supabase-browser.js` for a local TLS-verified library.
The tests use deterministic time, temporary browser contexts, 360px viewports and
mock cloud RPCs. They never read or write live student data.

## Rename question-vault sources

The pencil button beside a source in the source map opens the name editor. Saving changes only that book's `name`; its ID, subject, progress
and linked question records remain intact. All question references, active
review sessions, filters, quick-add options and teacher-question views resolve
the new name through the existing book ID. Local saves, JSON backups and the
existing Coach Sync state JSON carry the change without new fields or tables.
Coach mode can see renamed sources but has no edit controls or write access.

Both source creation and renaming reject duplicate names across subjects after
Turkish case folding, Unicode normalization and whitespace cleanup. Names must
contain 1–160 characters. Existing duplicate sources are retained on load;
no books or questions are automatically merged or deleted.

Run the focused browser tests with Python Playwright and Chromium:

```sh
python tests/test_vault_book_rename.py
```

The optional `--supabase-js` argument accepts a local TLS-verified browser
library. Tests use synthetic records, mocked cloud RPCs and 360px viewports.

## Fully learned question celebration

The question-vault review schedule stays unchanged: the first independent check
opens after seven days; successful checks then schedule 14- and 28-day reviews.
Only the existing final `mastered` transition shows the congratulations card,
with a trophy and lightweight CSS confetti. It closes after 3.5 seconds, or
immediately with **Kapat** / Escape. Reduced-motion users get a static card.

The optional per-question `masteryCelebratedAt` timestamp is saved with existing
question data before showing the card and survives localStorage, JSON backups and
Coach Sync. Existing mastered questions never replay a celebration on load. This
is presentation metadata only: it awards no XP and does not change stages,
review dates or the stored question IDs. The global learned count appears in the
vault summary and the existing RPG long-term statistics. Batch sessions keep the
next question selected when a newly mastered question leaves the session list.

Run the focused tests with Python Playwright and Chromium:

```sh
python tests/test_vault_mastery_celebration.py
```

The optional `--supabase-js` argument accepts a local TLS-verified browser
library. Tests use isolated fixtures, mocked cloud calls and a 360px viewport;
no real student data is read or modified.

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
