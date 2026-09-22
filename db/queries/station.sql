-- name: station_spec(station_id)^
-- One station's position and takt.
select station_id, name, sequence_pos, takt_s, fits_lot
from qgate.dim_station
where station_id = :station_id;

-- name: station_characteristics(station_id)
-- The characteristics a station measures, with nominal and limits.
select characteristic_id, name, unit, nominal, lower_limit, upper_limit
from qgate.dim_characteristic
where station_id = :station_id
order by characteristic_id;

-- name: eol_of(vin)^
-- The latest end-of-line verdict for a vehicle with its fault codes as an array.
select r.tested_at, r.bench_id, r.result,
       coalesce(array_agg(f.fault_code order by f.fault_code)
                filter (where f.fault_code is not null), '{}') as fault_codes
from qgate.fact_eol_result r
left join qgate.fact_eol_fault f on f.vin = r.vin and f.tested_at = r.tested_at
where r.vin = :vin
group by r.tested_at, r.bench_id, r.result
order by r.tested_at desc
limit 1;
