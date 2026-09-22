-- name: correlated_failures(fault_code, station_id, start, end, exclude_vin)
-- Other vehicles that raised the same fault code and passed the suspect station, with the shift
-- and parts lots they had *at that station* (not at EOL) so the breakdown points at a cause.
select b.vin, b.shift_id, b.parts_lots, b.entered_at, f.tested_at
from qgate.fact_eol_fault f
join qgate.fact_build_event b on b.vin = f.vin and b.station_id = :station_id
where f.fault_code = :fault_code
  and f.tested_at >= :start and f.tested_at < :end
  and f.vin <> coalesce(:exclude_vin, '')
order by f.tested_at;
