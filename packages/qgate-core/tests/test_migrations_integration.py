from collections.abc import Callable

import psycopg
import pytest

pytestmark = pytest.mark.integration

TABLES = {
    "dim_station",
    "dim_characteristic",
    "dim_shift",
    "dim_bench",
    "fact_build_event",
    "fact_measurement",
    "fact_eol_result",
    "fact_eol_fault",
    "containment",
    "containment_vin",
    "containment_audit",
}


def test_all_tables_exist(pg_url: str) -> None:
    with psycopg.connect(pg_url) as conn:
        rows = conn.execute(
            "select table_name from information_schema.tables where table_schema = 'qgate'"
        ).fetchall()
    assert {r[0] for r in rows} == TABLES


def test_generated_columns_derive_from_value(pg_url: str) -> None:
    with psycopg.connect(pg_url) as conn:
        conn.execute("insert into qgate.dim_station values ('ST-01','x',1,60,false)")
        conn.execute(
            "insert into qgate.dim_characteristic values ('CH-01-A','ST-01','a','mm',10,9,11)"
        )
        conn.execute("insert into qgate.dim_bench values ('B','ST-01',0.02,0,null)")
        conn.execute(
            "insert into qgate.fact_measurement (vin, station_id, characteristic_id, bench_id, "
            "measured_at, value, nominal, lower_limit, upper_limit) "
            "values ('V','ST-01','CH-01-A','B',now(),11.5,10,9,11)"
        )
        dev, oot = conn.execute(
            "select deviation, out_of_tolerance from qgate.fact_measurement where vin = 'V'"
        ).fetchone()  # type: ignore[misc]
        conn.rollback()
    assert dev == 1.5 and oot is True


@pytest.mark.parametrize(
    ("role", "statement"),
    [
        ("agent_ro", "insert into qgate.dim_shift values ('X','x','06:00','14:00','A')"),
        (
            "ingest_rw",
            "insert into qgate.containment_audit (containment_id, thread_id, proposed, "
            "decided, diff, decision, actor) values (gen_random_uuid(), gen_random_uuid(), "
            "'{}', '{}', '{}', 'APPROVE', 'x')",
        ),
        ("detect_ro", "select * from qgate.containment"),
        ("checkpoint_rw", "select * from qgate.fact_measurement"),
    ],
)
def test_roles_are_least_privilege(
    role_url: Callable[[str], str], role: str, statement: str
) -> None:
    with (
        psycopg.connect(role_url(role)) as conn,
        pytest.raises(psycopg.errors.InsufficientPrivilege),
    ):
        conn.execute(statement)


def test_ingest_can_write_facts_and_agent_can_read_them(role_url: Callable[[str], str]) -> None:
    with psycopg.connect(role_url("ingest_rw")) as conn:
        conn.execute(
            "insert into qgate.dim_shift values ('S9','x','06:00','14:00','A') "
            "on conflict do nothing"
        )
        conn.commit()
    with psycopg.connect(role_url("agent_ro")) as conn:
        assert conn.execute(
            "select count(*) from qgate.dim_shift where shift_id = 'S9'"
        ).fetchone() == (1,)
