-- name: deviation_series(station_id, characteristic_id, start, end)
-- Primary readings for one characteristic in time order, as half-tolerance units.
select measured_at,
       deviation / ((upper_limit - lower_limit) / 2) as dev
from qgate.fact_measurement
where station_id = :station_id
  and characteristic_id = :characteristic_id
  and repeat_no = 1
  and measured_at >= :start and measured_at < :end
order by measured_at, id;

-- name: bench_repeats(bench_id, characteristic_id, start, end)
-- Every reading (primary and repeats) for vehicles that were re-measured on this bench.
select vin, repeat_no, deviation / ((upper_limit - lower_limit) / 2) as dev
from qgate.fact_measurement
where bench_id = :bench_id
  and characteristic_id = :characteristic_id
  and measured_at >= :start and measured_at < :end
  and vin in (select vin from qgate.fact_measurement
              where bench_id = :bench_id and characteristic_id = :characteristic_id
                and repeat_no > 1 and measured_at >= :start and measured_at < :end)
order by vin, repeat_no;

-- name: bench_primary_values(characteristic_id, start, end)
-- Primary readings for one EOL characteristic across all benches, to compare a bench to its peers.
select bench_id, deviation / ((upper_limit - lower_limit) / 2) as dev
from qgate.fact_measurement
where characteristic_id = :characteristic_id
  and repeat_no = 1
  and measured_at >= :start and measured_at < :end;
