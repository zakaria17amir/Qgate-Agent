-- migrate:up
-- What the agent saw when it proposed (genealogy, siblings, drift, bench) and which vehicle
-- triggered it. The console reads the former; VIN re-scoping on amend needs the latter.
alter table qgate.containment
    add column evidence    jsonb not null default '{}',
    add column trigger_vin text;

-- Re-scoping replaces the held VIN set, so the api may delete from the join table (only there).
grant delete on qgate.containment_vin to api_rw;

-- migrate:down
revoke delete on qgate.containment_vin from api_rw;
alter table qgate.containment drop column evidence, drop column trigger_vin;
