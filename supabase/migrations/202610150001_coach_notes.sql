-- Run in the Supabase SQL editor as the database owner, after confirming the
-- singleton table and reviewing save_yks_rpg_state (see supabase/README.md).
-- Set the EXISTING table below. This migration fails closed until configured.
BEGIN;
SELECT set_config('yks.coach_notes_table',
  coalesce(nullif(current_setting('yks.coach_notes_table', true), ''),
           'public.REPLACE_WITH_SINGLETON_TABLE'), true);

DO $migration$
DECLARE
  target regclass := to_regclass(current_setting('yks.coach_notes_table'));
  qualified text;
  rows_count bigint;
  routine regprocedure;
BEGIN
  IF target IS NULL THEN
    RAISE EXCEPTION 'Set yks.coach_notes_table to the verified existing singleton table; no changes applied.';
  END IF;
  SELECT format('%I.%I', n.nspname, c.relname) INTO qualified
  FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
  WHERE c.oid=target AND c.relkind='r' AND n.nspname NOT IN ('pg_catalog','information_schema');
  IF qualified IS NULL THEN RAISE EXCEPTION 'Expected a regular application table'; END IF;
  IF NOT EXISTS(SELECT 1 FROM pg_attribute WHERE attrelid=target AND attname='state' AND atttypid='jsonb'::regtype AND NOT attisdropped) THEN
    RAISE EXCEPTION 'The selected table must contain the existing student state jsonb column';
  END IF;
  EXECUTE format('SELECT count(*) FROM %s',qualified) INTO rows_count;
  IF rows_count<>1 THEN RAISE EXCEPTION 'Expected exactly one existing singleton row'; END IF;
  FOREACH routine IN ARRAY ARRAY[
    to_regprocedure('public.get_yks_rpg_owner_state(text)'),
    to_regprocedure('public.get_yks_rpg_coach_state(text)'),
    to_regprocedure('public.save_yks_rpg_state(text,jsonb)')
  ] LOOP
    IF routine IS NULL OR NOT EXISTS(SELECT 1 FROM pg_proc WHERE oid=routine AND prosecdef) THEN
      RAISE EXCEPTION 'Existing owner/coach state RPCs must exist and use SECURITY DEFINER before direct table privileges can be removed';
    END IF;
  END LOOP;
  -- Keep the existing token verification and hash implementation in its current
  -- read RPCs. No token values or newly invented hash scheme belong here.
  EXECUTE format('ALTER TABLE %s ADD COLUMN IF NOT EXISTS coach_notes jsonb NOT NULL DEFAULT ''{}''::jsonb',qualified);
  IF NOT EXISTS(SELECT 1 FROM pg_attribute WHERE attrelid=target AND attname='coach_notes' AND atttypid='jsonb'::regtype AND attnotnull AND NOT attisdropped) THEN
    RAISE EXCEPTION 'coach_notes must be jsonb NOT NULL; no data was converted';
  END IF;
  EXECUTE format('ALTER TABLE %s ENABLE ROW LEVEL SECURITY',qualified);
  EXECUTE format('REVOKE ALL PRIVILEGES ON TABLE %s FROM PUBLIC, anon, authenticated',qualified);
  -- Column ACLs are independent of table ACLs; remove any old column grants too.
  FOR qualified IN SELECT format('%I.%I',n.nspname,c.relname) FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace WHERE c.oid=target LOOP
    FOR rows_count IN SELECT attnum FROM pg_attribute WHERE attrelid=target AND attnum>0 AND NOT attisdropped LOOP
      EXECUTE format('REVOKE ALL PRIVILEGES (%I) ON TABLE %s FROM PUBLIC, anon, authenticated',
        (SELECT attname FROM pg_attribute WHERE attrelid=target AND attnum=rows_count), qualified);
    END LOOP;
  END LOOP;

  EXECUTE format($ddl$
CREATE OR REPLACE FUNCTION public.get_yks_rpg_coach_notes(raw_token text)
RETURNS TABLE(coach_notes jsonb, updated_at timestamptz)
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog
AS $body$
DECLARE allowed boolean:=false; doc jsonb;
BEGIN
  IF raw_token IS NULL OR length(raw_token)<1 OR length(raw_token)>512 THEN RETURN; END IF;
  BEGIN
    SELECT coalesce(bool_or(jsonb_typeof(to_jsonb(r)->'state')='object'),false)
      INTO allowed FROM public.get_yks_rpg_owner_state(raw_token) r;
  EXCEPTION WHEN OTHERS THEN allowed:=false; END;
  IF NOT allowed THEN
    BEGIN
      SELECT coalesce(bool_or(jsonb_typeof(to_jsonb(r)->'state')='object'),false)
        INTO allowed FROM public.get_yks_rpg_coach_state(raw_token) r;
    EXCEPTION WHEN OTHERS THEN allowed:=false; END;
  END IF;
  IF NOT allowed THEN RETURN; END IF;
  SELECT t.coach_notes INTO STRICT doc FROM %s t;
  RETURN QUERY SELECT doc, nullif(doc->>'updatedAt','')::timestamptz;
END
$body$;
$ddl$,qualified);

  EXECUTE format($ddl$
CREATE OR REPLACE FUNCTION public.save_yks_rpg_coach_notes(raw_coach_token text,new_notes jsonb)
RETURNS timestamptz
LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog
AS $body$
DECLARE
  allowed boolean:=false; is_owner boolean:=false; kind text; day_key text; task_key text;
  entry jsonb; container jsonb; doc jsonb; note_path text[]; row_locator tid;
  expected text; current_stamp text; content text; changed_at timestamptz;
BEGIN
  IF raw_coach_token IS NULL OR length(raw_coach_token)<1 OR length(raw_coach_token)>512 THEN
    RAISE EXCEPTION USING ERRCODE='42501',MESSAGE='Invalid coach token';
  END IF;
  BEGIN
    SELECT coalesce(bool_or(jsonb_typeof(to_jsonb(r)->'state')='object'),false)
      INTO is_owner FROM public.get_yks_rpg_owner_state(raw_coach_token) r;
  EXCEPTION WHEN OTHERS THEN is_owner:=false; END;
  IF NOT is_owner THEN
    BEGIN
      SELECT coalesce(bool_or(jsonb_typeof(to_jsonb(r)->'state')='object'),false)
        INTO allowed FROM public.get_yks_rpg_coach_state(raw_coach_token) r;
    EXCEPTION WHEN OTHERS THEN allowed:=false; END;
  END IF;
  IF is_owner OR NOT allowed THEN
    RAISE EXCEPTION USING ERRCODE='42501',MESSAGE='Invalid coach token';
  END IF;
  -- Accept exactly one note patch, never a replacement document/student state.
  IF jsonb_typeof(new_notes) IS DISTINCT FROM 'object' THEN
    RAISE EXCEPTION USING ERRCODE='22023',MESSAGE='Expected a single-note object';
  END IF;
  IF (SELECT count(*) FROM jsonb_object_keys(new_notes))<>1 THEN
    RAISE EXCEPTION USING ERRCODE='22023',MESSAGE='Expected exactly one note patch';
  END IF;
  SELECT key,value INTO kind,container FROM jsonb_each(new_notes);
  IF kind NOT IN ('daily','lessons') OR jsonb_typeof(container) IS DISTINCT FROM 'object' THEN
    RAISE EXCEPTION USING ERRCODE='22023',MESSAGE='Invalid note scope';
  END IF;
  IF (SELECT count(*) FROM jsonb_object_keys(container))<>1 THEN
    RAISE EXCEPTION USING ERRCODE='22023',MESSAGE='Expected exactly one date';
  END IF;
  SELECT key,value INTO day_key,entry FROM jsonb_each(container);
  IF day_key !~ '^[0-9]{4}-[0-9]{2}-[0-9]{2}$' OR day_key<'2026-09-28' THEN
    RAISE EXCEPTION USING ERRCODE='22023',MESSAGE='Invalid note date';
  END IF;
  BEGIN
    IF to_char(day_key::date,'YYYY-MM-DD')<>day_key THEN RAISE EXCEPTION 'Invalid date'; END IF;
  EXCEPTION WHEN OTHERS THEN RAISE EXCEPTION USING ERRCODE='22023',MESSAGE='Invalid note date'; END;
  IF kind='lessons' THEN
    IF jsonb_typeof(entry) IS DISTINCT FROM 'object' THEN
      RAISE EXCEPTION USING ERRCODE='22023',MESSAGE='Expected a lesson object';
    END IF;
    IF (SELECT count(*) FROM jsonb_object_keys(entry))<>1 THEN
      RAISE EXCEPTION USING ERRCODE='22023',MESSAGE='Expected exactly one lesson';
    END IF;
    SELECT key,value INTO task_key,entry FROM jsonb_each(entry);
    IF task_key NOT IN ('paragraph','problem','mat','geo','physics','chem','bio','tr','grammar','geoTYT','hist',
      'tyt','r1','r2','anGeo','anPhysics','anChem','anBio','anProblem','anMath','anGeoTYT','anHist','anGrammar') THEN
      RAISE EXCEPTION USING ERRCODE='22023',MESSAGE='Invalid main-plan lesson';
    END IF;
    note_path:=ARRAY['lessons',day_key,task_key];
  ELSE note_path:=ARRAY['daily',day_key]; END IF;
  IF jsonb_typeof(entry) IS DISTINCT FROM 'object' THEN
    RAISE EXCEPTION USING ERRCODE='22023',MESSAGE='Expected note text and version';
  END IF;
  IF NOT (entry ? 'text' AND entry ? 'expectedUpdatedAt') OR
      EXISTS(SELECT 1 FROM jsonb_object_keys(entry) k WHERE k NOT IN ('text','expectedUpdatedAt')) OR
      jsonb_typeof(entry->'text') IS DISTINCT FROM 'string' OR
      jsonb_typeof(entry->'expectedUpdatedAt') NOT IN ('string','null') THEN
    RAISE EXCEPTION USING ERRCODE='22023',MESSAGE='Invalid note fields';
  END IF;
  content:=btrim(entry->>'text',E' \n\r\t');
  IF length(content)>4000 THEN RAISE EXCEPTION USING ERRCODE='22023',MESSAGE='Note is too long'; END IF;
  expected:=entry->>'expectedUpdatedAt';
  SELECT t.ctid,t.coach_notes INTO STRICT row_locator,doc FROM %s t FOR UPDATE;
  IF jsonb_typeof(doc) IS DISTINCT FROM 'object' THEN RAISE EXCEPTION 'Invalid coach notes document'; END IF;
  current_stamp:=doc#>>(note_path||ARRAY['updatedAt']);
  IF current_stamp IS DISTINCT FROM expected THEN
    RAISE EXCEPTION USING ERRCODE='40001',MESSAGE='Note changed; reload before retrying';
  END IF;
  IF doc->'daily' IS NULL THEN doc:=jsonb_set(doc,'{daily}','{}'); END IF;
  IF doc->'lessons' IS NULL THEN doc:=jsonb_set(doc,'{lessons}','{}'); END IF;
  IF kind='lessons' AND doc#>ARRAY['lessons',day_key] IS NULL THEN
    doc:=jsonb_set(doc,ARRAY['lessons',day_key],'{}');
  END IF;
  changed_at:=clock_timestamp();
  -- Keep a blank tombstone on deletion, so stale editors cannot resurrect a note.
  doc:=jsonb_set(doc,note_path,jsonb_build_object('text',content,'updatedAt',changed_at),true);
  doc:=jsonb_set(doc,'{updatedAt}',to_jsonb(changed_at),true);
  IF pg_column_size(doc)>1048576 THEN RAISE EXCEPTION USING ERRCODE='22023',MESSAGE='Coach notes document is too large'; END IF;
  UPDATE %s SET coach_notes=doc WHERE ctid=row_locator;
  RETURN changed_at;
END
$body$;
$ddl$,qualified,qualified);
END
$migration$;

REVOKE ALL ON FUNCTION public.get_yks_rpg_coach_notes(text) FROM PUBLIC;
REVOKE ALL ON FUNCTION public.save_yks_rpg_coach_notes(text,jsonb) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION public.get_yks_rpg_coach_notes(text) TO anon,authenticated;
GRANT EXECUTE ON FUNCTION public.save_yks_rpg_coach_notes(text,jsonb) TO anon,authenticated;
NOTIFY pgrst,'reload schema';
COMMIT;
