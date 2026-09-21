-- migrate:up
-- Facts keyed by natural keys so ingest can `insert ... on conflict do nothing`:
-- Kafka delivers at least once; the primary keys make replay idempotent.

-- The spine of genealogy: one row per vehicle per station.
create table qgate.fact_build_event (
    vin         text not null,
    station_id  text not null references qgate.dim_station,
    sequence_no bigint not null,
    entered_at  timestamptz not null,
    shift_id    text not null references qgate.dim_shift,
    operator_id text not null,
    parts_lots  text[] not null default '{}',
    primary key (vin, station_id)
);
create index on qgate.fact_build_event (station_id, entered_at);  -- window containment
create index on qgate.fact_build_event using gin (parts_lots);    -- lot containment
create index on qgate.fact_build_event (shift_id);

-- The large table. Limits are copied onto the row so deviation and out-of-tolerance are
-- computed once, at write time, and never drift from the dimension.
create table qgate.fact_measurement (
    id                bigint generated always as identity primary key,
    vin               text not null,
    station_id        text not null,
    characteristic_id text not null references qgate.dim_characteristic,
    bench_id          text not null references qgate.dim_bench,
    measured_at       timestamptz not null,
    value             double precision not null,
    nominal           double precision not null,
    lower_limit       double precision not null,
    upper_limit       double precision not null,
    repeat_no         int not null default 1,   -- >1: gauge repeat for %GRR
    deviation         double precision generated always as (value - nominal) stored,
    out_of_tolerance  boolean generated always as (value < lower_limit or value > upper_limit) stored,
    unique (vin, characteristic_id, repeat_no)
);
create index on qgate.fact_measurement (station_id, characteristic_id, measured_at);  -- SPC series
create index on qgate.fact_measurement (bench_id, measured_at) where repeat_no > 1;   -- %GRR

create table qgate.fact_eol_result (
    vin       text not null,
    tested_at timestamptz not null,
    bench_id  text not null references qgate.dim_bench,
    result    text not null check (result in ('PASS', 'FAIL')),
    primary key (vin, tested_at)
);
create index on qgate.fact_eol_result (bench_id, tested_at);

-- Fault codes as rows, not a delimited string.
create table qgate.fact_eol_fault (
    vin        text not null,
    tested_at  timestamptz not null,
    fault_code text not null,
    primary key (vin, tested_at, fault_code),
    foreign key (vin, tested_at) references qgate.fact_eol_result
);
create index on qgate.fact_eol_fault (fault_code, tested_at);  -- sibling search

-- migrate:down
drop table qgate.fact_eol_fault, qgate.fact_eol_result, qgate.fact_measurement, qgate.fact_build_event;
