-- Synthetic fixture for tests/run-coach-notes-db.sh ONLY; never run on production.
CREATE EXTENSION IF NOT EXISTS pgcrypto;
CREATE ROLE anon NOLOGIN;
CREATE ROLE authenticated NOLOGIN;
CREATE TABLE public.yks_rpg_test_singleton (
 id integer PRIMARY KEY CHECK(id=1),state jsonb NOT NULL DEFAULT '{}',
 owner_hash bytea NOT NULL,coach_hash bytea NOT NULL,updated_at timestamptz NOT NULL DEFAULT now()
);
DO $test_tokens$ BEGIN
PERFORM set_config('yks.test_owner',encode(gen_random_bytes(32),'hex'),false);
PERFORM set_config('yks.test_coach',rtrim(translate(encode(digest('coach:'||current_setting('yks.test_owner'),'sha256'),'base64'),'+/','-_'),'='),false);
END $test_tokens$;
INSERT INTO public.yks_rpg_test_singleton(id,state,owner_hash,coach_hash)
VALUES(1,'{"checks":{"2026-10-15|geo":true},"morningProtocol":{}}',digest(current_setting('yks.test_owner'),'sha256'),digest(current_setting('yks.test_coach'),'sha256'));
CREATE FUNCTION public.get_yks_rpg_owner_state(raw_owner_token text)
RETURNS TABLE(state jsonb,updated_at timestamptz)
LANGUAGE sql SECURITY DEFINER SET search_path=pg_catalog AS $$
 SELECT t.state,t.updated_at FROM public.yks_rpg_test_singleton t WHERE t.owner_hash=public.digest(raw_owner_token,'sha256')
$$;
CREATE FUNCTION public.get_yks_rpg_coach_state(raw_token text)
RETURNS TABLE(state jsonb,updated_at timestamptz)
LANGUAGE sql SECURITY DEFINER SET search_path=pg_catalog AS $$
 SELECT t.state,t.updated_at FROM public.yks_rpg_test_singleton t WHERE t.coach_hash=public.digest(raw_token,'sha256')
$$;
CREATE FUNCTION public.save_yks_rpg_state(raw_owner_token text,new_state jsonb)
RETURNS timestamptz LANGUAGE plpgsql SECURITY DEFINER SET search_path=pg_catalog AS $$
DECLARE saved timestamptz;
BEGIN
 UPDATE public.yks_rpg_test_singleton SET state=new_state,updated_at=clock_timestamp()
 WHERE owner_hash=public.digest(raw_owner_token,'sha256') RETURNING updated_at INTO saved;
 IF saved IS NULL THEN RAISE EXCEPTION USING ERRCODE='42501',MESSAGE='Invalid owner token'; END IF;
 RETURN saved;
END $$;
GRANT SELECT,INSERT,UPDATE,DELETE ON TABLE public.yks_rpg_test_singleton TO anon,authenticated;
GRANT UPDATE(state) ON TABLE public.yks_rpg_test_singleton TO anon,authenticated;
-- These settings are per test session; values are synthetic and never printed.
