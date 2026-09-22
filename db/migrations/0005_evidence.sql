-- migrate:up
-- What the agent saw when it proposed: genealogy, siblings, drift, bench. Read by the console.
alter table qgate.containment add column evidence jsonb not null default '{}';

-- migrate:down
alter table qgate.containment drop column evidence;
