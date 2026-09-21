-- migrate:up
-- Dimensions. Ids are text because they are human-authored in scenarios/line.yaml.

create table qgate.dim_station (
    station_id   text primary key,
    name         text not null,
    sequence_pos int  not null unique,
    takt_s       int  not null,
    fits_lot     boolean not null default false  -- parts lots are fitted (and recorded) here
);

create table qgate.dim_characteristic (
    characteristic_id text primary key,
    station_id        text not null references qgate.dim_station,
    name              text not null,
    unit              text not null,
    nominal           double precision not null,
    lower_limit       double precision not null,
    upper_limit       double precision not null,
    check (lower_limit < nominal and nominal < upper_limit)
);
create index on qgate.dim_characteristic (station_id);

create table qgate.dim_shift (
    shift_id  text primary key,
    label     text not null,
    starts_at time not null,
    ends_at   time not null,
    crew      text not null
);

-- A measurement system (gauge / test bench) with its own repeatability and bias.
create table qgate.dim_bench (
    bench_id            text primary key,
    station_id          text not null references qgate.dim_station,
    repeatability_sigma double precision not null,
    bias                double precision not null,
    calibrated_at       timestamptz
);
create index on qgate.dim_bench (station_id);

-- migrate:down
drop table qgate.dim_bench, qgate.dim_shift, qgate.dim_characteristic, qgate.dim_station;
