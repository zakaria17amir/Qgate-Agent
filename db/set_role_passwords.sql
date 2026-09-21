-- Applied after migrations by the `roles` compose service: psql -v pw="$POSTGRES_PASSWORD" -f this.
-- One password for all application roles in the dev stack; production would use one each.
alter role ingest_rw     password :'pw';
alter role api_rw        password :'pw';
alter role agent_ro      password :'pw';
alter role detect_ro     password :'pw';
alter role checkpoint_rw password :'pw';
