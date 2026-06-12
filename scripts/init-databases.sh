#!/bin/bash
set -e
sed -e "s|{{KC_DB_PASSWORD}}|$KC_DB_PASSWORD|g" \
    -e "s|{{KONG_DB_PASSWORD}}|$KONG_DB_PASSWORD|g" \
    -e "s|{{USER_SERVICE_DB_PASSWORD}}|$USER_SERVICE_DB_PASSWORD|g" \
    /scripts/init-databases.template.sql > /tmp/init-databases.sql

psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" -f /tmp/init-databases.sql
