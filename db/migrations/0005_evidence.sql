-- migrate:up
-- What the agent saw when it proposed (genealogy, siblings, drift, bench) and which vehicle
-- triggered it. The console reads the former; VIN re-scoping on amend needs the latter.
alter table qgate.containment
    add column evidence    jsonb not null default '{}',
    add column trigger_vin text;

-- migrate:down
alter table qgate.containment drop column evidence, drop column trigger_vin;
