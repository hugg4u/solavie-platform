-- CreateTable
CREATE TABLE "users" (
    "id" UUID NOT NULL,
    "tenant_id" UUID NOT NULL,
    "phone_number" VARCHAR(20),
    "avatar_url" VARCHAR(255),
    "department" VARCHAR(50),
    "status" VARCHAR(20) NOT NULL DEFAULT 'PENDING',
    "created_at" TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updated_at" TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT "users_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "user_preferences" (
    "user_id" UUID NOT NULL,
    "theme" VARCHAR(20) NOT NULL DEFAULT 'dark',
    "language" VARCHAR(10) NOT NULL DEFAULT 'vi',
    "notifications_enabled" BOOLEAN NOT NULL DEFAULT true,
    "created_at" TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "updated_at" TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT "user_preferences_pkey" PRIMARY KEY ("user_id")
);

-- AddForeignKey
ALTER TABLE "user_preferences" ADD CONSTRAINT "user_preferences_user_id_fkey" FOREIGN KEY ("user_id") REFERENCES "users"("id") ON DELETE CASCADE ON UPDATE CASCADE;

-- Enable Row-Level Security (RLS)
ALTER TABLE "users" ENABLE ROW LEVEL SECURITY;
ALTER TABLE "users" FORCE ROW LEVEL SECURITY;

-- Create Tenant Isolation Policy for users
CREATE POLICY tenant_user_isolation_policy ON "users"
    FOR ALL
    USING ("tenant_id" = NULLIF(current_setting('app.current_tenant_id', true), '')::UUID);

-- Enable RLS for user_preferences
ALTER TABLE "user_preferences" ENABLE ROW LEVEL SECURITY;
ALTER TABLE "user_preferences" FORCE ROW LEVEL SECURITY;

-- Create Tenant Isolation Policy for user_preferences
CREATE POLICY tenant_pref_isolation_policy ON "user_preferences"
    FOR ALL
    USING ("user_id" IN (
        SELECT "id" FROM "users" 
        WHERE "tenant_id" = NULLIF(current_setting('app.current_tenant_id', true), '')::UUID
    ));
