# Coach notes deployment

Coach notes are stored in a separate `coach_notes jsonb NOT NULL DEFAULT '{}'`
column on the existing singleton table. They never enter the application's
student `state`, its localStorage record, or its JSON exports. No new app table
or token is created. The existing owner and coach state-read RPCs remain the
authority for token verification, including the current hash algorithm.

## Production prerequisite — not yet applied

The repository does not contain the current Supabase table definition or state
RPC definitions, and this cloud workspace has no Supabase administrator or SQL
connection. The publishable application key cannot inspect the schema. Therefore
**this migration has not been run against production**. Do not substitute a table
name guessed from the project name.

1. Confirm the actual existing singleton table, its triggers, and the definitions
   of `get_yks_rpg_owner_state(text)`, `get_yks_rpg_coach_state(text)`, and
   `save_yks_rpg_state(text,jsonb)` in the Supabase SQL editor. Do not share token
   values, token hashes, database passwords or service keys in chat/source.
2. Confirm the read RPCs return a row/object with an object-valued `state` only
   after validating the corresponding token. Both read RPCs and the owner-save
   RPC must be `SECURITY DEFINER`. The owner-save RPC must update only its student
   fields; it must not delete/reinsert the singleton or perform a dynamic
   whole-row replacement. Review existing UPDATE triggers for the same boundary.
3. Set `yks.coach_notes_table` to the verified schema-qualified table name, e.g.
   `SET yks.coach_notes_table = 'public.ACTUAL_EXISTING_TABLE';`, in the same SQL
   editor execution immediately before the migration. Alternatively replace the
   one `public.REPLACE_WITH_SINGLETON_TABLE` placeholder in the migration. Until
   configured, the migration raises an error and rolls back without changes.
4. Run `migrations/202610150001_coach_notes.sql` as the database owner. It verifies
   the state column and exactly one existing row before adding the column,
   enables RLS, removes direct table **and column** privileges from `PUBLIC`,
   `anon`, and `authenticated`, and grants only token-checked RPC execution.
   It leaves the existing owner/coach state functions unchanged.
5. Verify valid owner/coach note reads, invalid-token denial, coach-only note
   writes, owner-save preservation of notes, and unchanged student state after a
   note write in that actual database. Then test the student and coach browsers.
   Local fixture tests are evidence about the migration contract, not proof that
   the production schema meets its prerequisites.

Until the RPCs are deployed, the app keeps student features working and shows an
unavailable-notes message; coach note editors stay disabled. It does not silently
save notes locally as if they had reached Supabase.

## RPC contract

`get_yks_rpg_coach_notes(raw_token text)` returns zero rows for an invalid token;
valid owner and coach tokens receive one row:

```json
{"coach_notes":{"daily":{},"lessons":{},"updatedAt":"server timestamp"},"updated_at":"server timestamp"}
```

`save_yks_rpg_coach_notes(raw_coach_token text, new_notes jsonb)` accepts **one
note patch**, not a replacement of all notes. It accepts only a valid coach token
and explicitly rejects an owner token. For example:

```json
{"daily":{"2026-10-15":{"text":"Daily comment","expectedUpdatedAt":null}}}
```

```json
{"lessons":{"2026-10-15":{"geo":{"text":"Lesson comment","expectedUpdatedAt":"timestamp returned for this note"}}}}
```

The server locks the singleton row, compares this note's version, and updates only
that path in `coach_notes`. Different-path changes survive concurrent editors;
stale same-path edits fail with SQLSTATE `40001`. All `updatedAt` values are
server generated. Delete with `text: ""` and the existing version; a blank
versioned tombstone prevents stale editors from resurrecting deleted content.
Notes for removed plan lessons are retained and reappear if that slot returns.

Only known main-plan task keys are accepted (including fixed and historical
slots); `extra:*` keys are rejected. Notes follow the original plan slot when a
Swap changes its subject. Limits: 4,000 characters per note, 1 MiB per notes
JSON document. Inputs, dates and unexpected fields are checked server-side.

## Browser boundaries

Coach note drafts live in memory outside student state and survive the 30-second
read-only refresh while editing. A conflicting server version is displayed
beside the retained draft; replacement requires an explicit user action.

The student can read notes but cannot use the note-writing UI or function. In
coach mode only scoped note textareas/buttons are enabled. Student-mutating
handlers also reject coach mode directly. The database independently enforces
this boundary; disabled controls are not the authorization mechanism.

Student state and notes load separately. Manual student sync uploads state
and reloads notes, waiting for an in-flight student upload before sending the
latest edits. Notes also refresh periodically. A separate localStorage key,
`yks-rpg-coach-notes-seen-v1`, stores only a last-seen timestamp for the optional
new-note badge; no coach write token is added to student state/exports.

## Isolated database security tests

Run from the repository root with Docker available:

```sh
bash tests/run-coach-notes-db.sh
```

The runner creates a disposable PostgreSQL 17 container with no network, exposed
ports, host mounts or production data; synthetic owner/coach tokens are generated
inside the test database. It checks role boundaries, direct-write denial,
state/notes isolation, patch merging, stale versions, deletion and malformed
payloads. Never run the fixture SQL against a real application database.

## Browser security tests

With Python Playwright and Chromium installed:

```sh
python tests/test_coach_notes_browser.py
```

All RPCs are intercepted with an in-memory backend and synthetic tokens. The
Supabase browser library is downloaded with TLS verification; `--supabase-js`
can supply a local copy instead. No production writes occur. An optional
`--baseline /path/to/previous/index.html` compares historical/current state and
computed metrics against that previous application. Tests use a local loopback
HTTP server, ephemeral browser contexts and a 360px viewport.
