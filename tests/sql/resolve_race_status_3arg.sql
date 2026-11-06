CREATE OR REPLACE FUNCTION public.resolve_race_status(pf_data jsonb, bm_data jsonb, nitro_data jsonb)
 RETURNS text
 LANGUAGE sql
 IMMUTABLE PARALLEL SAFE
AS $function$
  SELECT CASE
    WHEN (nitro_data->'race_status_override'->>'status') = 'abandoned' THEN 'abandoned'::text
    ELSE public.resolve_race_status(pf_data, bm_data)::text
  END;
$function$
