-- migrate:up
-- Least-privilege roles, one per service (design §7.2). Passwords are set separately by
-- db/set_role_passwords.sql so no secret lives in a migration.
-- The agent's tools connect as agent_ro: they physically cannot write.

do $$
begin
    if not exists (select 1 from pg_roles where rolname = 'ingest_rw')     then create role ingest_rw     login; end if;
    if not exists (select 1 from pg_roles where rolname = 'api_rw')        then create role api_rw        login; end if;
    if not exists (select 1 from pg_roles where rolname = 'agent_ro')      then create role agent_ro      login; end if;
    if not exists (select 1 from pg_roles where rolname = 'detect_ro')     then create role detect_ro     login; end if;
    if not exists (select 1 from pg_roles where rolname = 'checkpoint_rw') then create role checkpoint_rw login; end if;
end $$;

grant usage on schema qgate to ingest_rw, api_rw, agent_ro, detect_ro;
alter role ingest_rw     set search_path = qgate, public;
alter role api_rw        set search_path = qgate, public;
alter role agent_ro      set search_path = qgate, public;
alter role detect_ro     set search_path = qgate, public;

-- ingest: writes facts, reads dims (and may seed dims at start-up)
grant select, insert, update on qgate.dim_station, qgate.dim_characteristic, qgate.dim_shift, qgate.dim_bench to ingest_rw;
grant select, insert on qgate.fact_build_event, qgate.fact_measurement, qgate.fact_eol_result, qgate.fact_eol_fault to ingest_rw;
grant usage on all sequences in schema qgate to ingest_rw;

-- api: owns decisions, reads everything else
grant select, insert, update on qgate.containment, qgate.containment_vin, qgate.containment_audit to api_rw;
grant select on all tables in schema qgate to api_rw;
grant usage on all sequences in schema qgate to api_rw;

-- agent tools and detect: read only
grant select on all tables in schema qgate to agent_ro;
grant select on qgate.dim_station, qgate.dim_characteristic, qgate.dim_bench, qgate.fact_measurement to detect_ro;

-- LangGraph checkpointer: its own schema, nothing in qgate
create schema if not exists checkpoint authorization checkpoint_rw;
alter role checkpoint_rw set search_path = checkpoint;

-- migrate:down
drop schema if exists checkpoint cascade;
revoke all on all tables in schema qgate from ingest_rw, api_rw, agent_ro, detect_ro;
revoke all on all sequences in schema qgate from ingest_rw, api_rw;
revoke usage on schema qgate from ingest_rw, api_rw, agent_ro, detect_ro;
drop role if exists ingest_rw, api_rw, agent_ro, detect_ro, checkpoint_rw;
