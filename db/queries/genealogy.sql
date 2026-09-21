-- name: genealogy_by_vin(vin)
-- The one query the agent cannot work without: every station a vehicle passed, in build order,
-- with that station's measurements folded into a JSON array. Both fact tables are hit by their
-- vin index; the measurement aggregate is a single ordered pass per station.
select b.station_id,
       b.entered_at,
       b.shift_id,
       b.operator_id,
       b.parts_lots,
       coalesce(m.measurements, '[]'::jsonb) as measurements
from qgate.fact_build_event b
join qgate.dim_station s on s.station_id = b.station_id
left join lateral (
    select jsonb_agg(jsonb_build_object(
               'characteristic_id', fm.characteristic_id,
               'bench_id',          fm.bench_id,
               'value',             fm.value,
               'deviation',         fm.deviation,
               'out_of_tolerance',  fm.out_of_tolerance,
               'repeat_no',         fm.repeat_no)
           order by fm.characteristic_id, fm.repeat_no) as measurements
    from qgate.fact_measurement fm
    where fm.vin = b.vin and fm.station_id = b.station_id
) m on true
where b.vin = :vin
order by s.sequence_pos;
