#!/usr/bin/env bash
set -euo pipefail
repo_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
test_container="yks-notes-tests-$$"
trap 'docker rm -f "$test_container" >/dev/null 2>&1 || true' EXIT
# No ports, host mounts, real app data or real credentials are used.
docker run --rm --network none --name "$test_container" \
  -e POSTGRES_PASSWORD=isolated-test-only -d postgres:17-alpine >/dev/null
for attempt in {1..30}; do
  if docker exec "$test_container" pg_isready -U postgres >/dev/null 2>&1; then break; fi
  if [[ "$attempt" == 30 ]]; then echo 'Test PostgreSQL did not become ready' >&2; exit 1; fi
  sleep 1
done
{
  printf 'BEGIN;\n'
  cat "$repo_dir/tests/sql/coach_notes_fixture.sql"
  printf '\nCOMMIT;\nSET yks.coach_notes_table = '\''public.yks_rpg_test_singleton'\'';\n'
  cat "$repo_dir/supabase/migrations/202610150001_coach_notes.sql"
  cat "$repo_dir/tests/sql/coach_notes_assertions.sql"
} | docker exec -i "$test_container" psql -U postgres -v ON_ERROR_STOP=1 -q
