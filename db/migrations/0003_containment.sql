-- migrate:up
-- Decisions. Written only by the api service; the agent reads them, never writes (ADR-008).

create table qgate.containment (
    containment_id  uuid primary key,
    thread_id       uuid not null,               -- LangGraph thread that produced the proposal
    state           text not null check (state in
                    ('PROPOSED','APPROVED','AMENDED','REJECTED','EXPIRED','COMMIT_PENDING','COMMITTED','ESCALATED')),
    kind            text not null check (kind in ('WINDOW','LOT','SINGLE','NONE')),
    station_id      text references qgate.dim_station,
    window_start    timestamptz,
    window_end      timestamptz,
    lot_ids         text[] not null default '{}',
    vin_count       int not null default 0,
    confidence      numeric(3,2),
    reason          text not null,
    draft_order     text,
    proposed_at     timestamptz not null default now(),
    expires_at      timestamptz,                 -- gate timeout; sweeper turns PROPOSED into EXPIRED
    decided_at      timestamptz,
    decided_by      text,
    mes_ref         text,
    idempotency_key uuid not null unique         -- sent to the plant system on commit
);
create index on qgate.containment (state, proposed_at);
create index on qgate.containment (station_id);

create table qgate.containment_vin (
    containment_id uuid not null references qgate.containment,
    vin            text not null,
    primary key (containment_id, vin)
);

-- The metrics table: one row per proposal whether or not it was approved.
create table qgate.containment_audit (
    audit_id           bigint generated always as identity primary key,
    containment_id     uuid not null references qgate.containment,
    thread_id          uuid not null,
    golden_id          text,                     -- set by the eval harness only
    proposed           jsonb not null,           -- what the agent proposed
    decided            jsonb not null,           -- what the human did
    diff               jsonb not null,           -- computed delta between the two
    decision           text not null,
    actor              text not null,
    latency_total_ms   int,
    latency_llm_ms     int,
    latency_non_llm_ms int,
    prompt_tokens      int,
    completion_tokens  int,
    cost_usd           numeric(8,5),
    created_at         timestamptz not null default now()
);
create index on qgate.containment_audit (containment_id);
create index on qgate.containment_audit (created_at);

-- migrate:down
drop table qgate.containment_audit, qgate.containment_vin, qgate.containment;
