-- Create users if they do not exist
DO $$
BEGIN
  IF NOT EXISTS (SELECT FROM pg_catalog.pg_roles WHERE rolname = 'keycloak') THEN
    CREATE ROLE keycloak WITH LOGIN PASSWORD '{{KC_DB_PASSWORD}}';
  END IF;
  IF NOT EXISTS (SELECT FROM pg_catalog.pg_roles WHERE rolname = 'kong') THEN
    CREATE ROLE kong WITH LOGIN PASSWORD '{{KONG_DB_PASSWORD}}';
  END IF;
  IF NOT EXISTS (SELECT FROM pg_catalog.pg_roles WHERE rolname = 'solavie_user') THEN
    CREATE ROLE solavie_user WITH LOGIN PASSWORD '{{USER_SERVICE_DB_PASSWORD}}';
  END IF;
END
$$;

-- Create databases and assign owners
SELECT 'CREATE DATABASE keycloak_db OWNER keycloak' WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = 'keycloak_db') \gexec
SELECT 'CREATE DATABASE kong_db OWNER kong' WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = 'kong_db') \gexec
SELECT 'CREATE DATABASE solavie_user_db OWNER solavie_user' WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = 'solavie_user_db') \gexec
