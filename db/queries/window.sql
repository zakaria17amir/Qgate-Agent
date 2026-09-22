-- name: vins_in_window(station_id, start, end)
-- Vehicles that entered a station in [start, end): a time-window containment.
select vin
from qgate.fact_build_event
where station_id = :station_id
  and entered_at >= :start and entered_at < :end
order by entered_at;

-- name: vins_by_lot(station_id, lot_id)
-- Vehicles that received a given parts lot at a station: a lot containment (GIN on parts_lots).
select vin
from qgate.fact_build_event
where station_id = :station_id
  and parts_lots @> array[:lot_id]::text[]
order by entered_at;
