-- All tokens are generated inside the isolated fixture; no real secrets are used.
SET ROLE anon;
DO $tests$
DECLARE
  owner_token text:=current_setting('yks.test_owner');
  coach_token text:=current_setting('yks.test_coach');
  doc jsonb; before_doc jsonb; original_state jsonb; original_time timestamptz;
  saved_at timestamptz; note_stamp text; patch jsonb; count_rows integer;
BEGIN
  SELECT r.state,r.updated_at INTO original_state,original_time FROM public.get_yks_rpg_owner_state(owner_token) r;
  SELECT count(*) INTO count_rows FROM public.get_yks_rpg_coach_notes('invalid');
  IF count_rows<>0 THEN RAISE EXCEPTION 'Invalid token read notes'; END IF;
  SELECT r.coach_notes INTO doc FROM public.get_yks_rpg_coach_notes(owner_token) r;
  IF doc IS DISTINCT FROM '{}'::jsonb THEN RAISE EXCEPTION 'Owner cannot read initial notes'; END IF;
  SELECT r.coach_notes INTO doc FROM public.get_yks_rpg_coach_notes(coach_token) r;
  IF doc IS DISTINCT FROM '{}'::jsonb THEN RAISE EXCEPTION 'Coach cannot read initial notes'; END IF;
  IF has_table_privilege('anon','public.yks_rpg_test_singleton','UPDATE') OR
     has_column_privilege('anon','public.yks_rpg_test_singleton','state','UPDATE') OR
     has_table_privilege('authenticated','public.yks_rpg_test_singleton','UPDATE') THEN
    RAISE EXCEPTION 'Direct student table writes are still granted';
  END IF;
  BEGIN
    UPDATE public.yks_rpg_test_singleton SET state='{}';
    RAISE EXCEPTION 'Direct table UPDATE succeeded';
  EXCEPTION WHEN insufficient_privilege THEN NULL; END;
  BEGIN
    UPDATE public.yks_rpg_test_singleton SET coach_notes='{}';
    RAISE EXCEPTION 'Direct coach_notes UPDATE succeeded';
  EXCEPTION WHEN insufficient_privilege THEN NULL; END;
  patch:='{"daily":{"2026-10-15":{"text":"daily note","expectedUpdatedAt":null}}}';
  BEGIN
    PERFORM public.save_yks_rpg_coach_notes(owner_token,patch);
    RAISE EXCEPTION 'Owner was allowed to save coach notes';
  EXCEPTION WHEN insufficient_privilege THEN NULL; END;
  BEGIN
    PERFORM public.save_yks_rpg_coach_notes('invalid',patch);
    RAISE EXCEPTION 'Invalid token was allowed to save coach notes';
  EXCEPTION WHEN insufficient_privilege THEN NULL; END;
  BEGIN
    PERFORM public.save_yks_rpg_state(coach_token,'{"checks":{}}');
    RAISE EXCEPTION 'Coach was allowed to save student state';
  EXCEPTION WHEN insufficient_privilege THEN NULL; END;
  saved_at:=public.save_yks_rpg_coach_notes(coach_token,patch);
  IF saved_at IS NULL THEN RAISE EXCEPTION 'Save did not return a timestamp'; END IF;
  SELECT r.coach_notes INTO doc FROM public.get_yks_rpg_coach_notes(owner_token) r;
  IF doc#>>'{daily,2026-10-15,text}'<>'daily note' THEN RAISE EXCEPTION 'Note not saved'; END IF;
  IF (SELECT r.state FROM public.get_yks_rpg_owner_state(owner_token) r) IS DISTINCT FROM original_state OR
     (SELECT r.updated_at FROM public.get_yks_rpg_owner_state(owner_token) r) IS DISTINCT FROM original_time THEN
    RAISE EXCEPTION 'Note write changed student state/timestamp';
  END IF;
  before_doc:=doc;
  PERFORM public.save_yks_rpg_state(owner_token,'{"checks":{"2026-10-15|bio":true},"coach_notes":{"forged":true}}');
  IF (SELECT r.coach_notes FROM public.get_yks_rpg_coach_notes(coach_token) r) IS DISTINCT FROM before_doc THEN
    RAISE EXCEPTION 'Student save overwrote separate coach notes';
  END IF;
  -- Both different-path changes survive, without replacing the document.
  PERFORM public.save_yks_rpg_coach_notes(coach_token,'{"lessons":{"2026-10-15":{"geo":{"text":"geometry","expectedUpdatedAt":null}}}}');
  PERFORM public.save_yks_rpg_coach_notes(coach_token,'{"lessons":{"2026-10-15":{"mat":{"text":"math slot","expectedUpdatedAt":null}}}}');
  SELECT r.coach_notes INTO doc FROM public.get_yks_rpg_coach_notes(coach_token) r;
  IF doc#>>'{lessons,2026-10-15,geo,text}'<>'geometry' OR doc#>>'{lessons,2026-10-15,mat,text}'<>'math slot' OR doc#>>'{daily,2026-10-15,text}'<>'daily note' THEN
    RAISE EXCEPTION 'Different-path updates lost notes';
  END IF;
  BEGIN
    PERFORM public.save_yks_rpg_coach_notes(coach_token,patch);
    RAISE EXCEPTION 'Stale note write succeeded';
  EXCEPTION WHEN serialization_failure THEN NULL; END;
  note_stamp:=doc#>>'{daily,2026-10-15,updatedAt}';
  PERFORM public.save_yks_rpg_coach_notes(coach_token,jsonb_build_object('daily',jsonb_build_object('2026-10-15',jsonb_build_object('text','','expectedUpdatedAt',note_stamp))));
  SELECT r.coach_notes INTO doc FROM public.get_yks_rpg_coach_notes(owner_token) r;
  IF doc#>>'{daily,2026-10-15,text}'<>'' OR doc#>>'{daily,2026-10-15,updatedAt}' IS NULL THEN
    RAISE EXCEPTION 'Delete did not clear text and retain version';
  END IF;
  BEGIN
    PERFORM public.save_yks_rpg_coach_notes(coach_token,patch);
    RAISE EXCEPTION 'Stale create resurrected a deleted note';
  EXCEPTION WHEN serialization_failure THEN NULL; END;
  FOREACH patch IN ARRAY ARRAY[
    '{"state":{"checks":{}}}'::jsonb,
    '{"daily":{"2026-10-15":{"text":"x","expectedUpdatedAt":null}},"lessons":{}}'::jsonb,
    '{"lessons":{"2026-10-15":{"extra:geo":{"text":"x","expectedUpdatedAt":null}}}}'::jsonb,
    '{"daily":{"2027-02-30":{"text":"x","expectedUpdatedAt":null}}}'::jsonb,
    '{"daily":{"2026-10-15":{"text":"x","expectedUpdatedAt":null,"updatedAt":"forged"}}}'::jsonb,
    jsonb_build_object('daily',jsonb_build_object('2026-10-16',jsonb_build_object('text',repeat('x',4001),'expectedUpdatedAt',null)))
  ] LOOP
    BEGIN
      PERFORM public.save_yks_rpg_coach_notes(coach_token,patch);
      RAISE EXCEPTION 'Invalid payload accepted';
    EXCEPTION WHEN invalid_parameter_value THEN NULL; END;
  END LOOP;
  RAISE NOTICE 'PASS: token roles, no direct table/column writes, state/notes isolation, atomic patches, version conflicts, safe deletion, input limits.';
END
$tests$;
RESET ROLE;
SET ROLE authenticated;
DO $authenticated_test$
BEGIN
  IF (SELECT count(*) FROM public.get_yks_rpg_coach_notes('invalid'))<>0 THEN RAISE EXCEPTION 'Authenticated role bypassed token checks'; END IF;
  BEGIN
    UPDATE public.yks_rpg_test_singleton SET coach_notes='{}';
    RAISE EXCEPTION 'Authenticated direct write succeeded';
  EXCEPTION WHEN insufficient_privilege THEN NULL; END;
END
$authenticated_test$;
RESET ROLE;
