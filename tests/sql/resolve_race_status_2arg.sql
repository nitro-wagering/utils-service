CREATE OR REPLACE FUNCTION public.resolve_race_status(pf_data jsonb, bm_data jsonb)
 RETURNS text
 LANGUAGE sql
 IMMUTABLE PARALLEL SAFE
AS $function$
  SELECT CASE
    WHEN (bm_data->>'race_status') = 'resulted' OR (pf_data->>'race_status') = 'resulted'
    THEN 'resulted'

    WHEN (bm_data->>'race_status') = 'abandoned' OR (pf_data->>'race_status') = 'abandoned'
    THEN 'abandoned'

    WHEN (bm_data->>'race_status') = 'interim' OR (pf_data->>'race_status') = 'interim'
    THEN 'interim'

    WHEN (bm_data->>'race_status') = 'final' OR (pf_data->>'race_status') = 'final'
    THEN 'final'

    WHEN (bm_data->>'race_status') = 'closed' OR (pf_data->>'race_status') = 'closed'
    THEN 'closed'

    WHEN (bm_data->>'race_status') = 'open' OR (pf_data->>'race_status') = 'open'
    THEN 'open'

    WHEN (bm_data->>'race_status') IS NOT NULL
    THEN (bm_data->>'race_status')

    WHEN (pf_data->>'race_status') IS NOT NULL
    THEN (pf_data->>'race_status')

    ELSE NULL
  END;
$function$
