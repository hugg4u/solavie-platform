-- Create users if they do not exist
DO $$
BEGIN
  IF NOT EXISTS (SELECT FROM pg_catalog.pg_roles WHERE rolname = 'keycloak') THEN
    CREATE ROLE keycloak WITH LOGIN PASSWORD 'keycloak_password';
  END IF;
  IF NOT EXISTS (SELECT FROM pg_catalog.pg_roles WHERE rolname = 'kong') THEN
    CREATE ROLE kong WITH LOGIN PASSWORD 'kong_password';
  END IF;
END
$$;

-- Create databases and assign owners
SELECT 'CREATE DATABASE keycloak_db OWNER keycloak' WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = 'keycloak_db') \gexec
SELECT 'CREATE DATABASE kong_db OWNER kong' WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = 'kong_db') \gexec
