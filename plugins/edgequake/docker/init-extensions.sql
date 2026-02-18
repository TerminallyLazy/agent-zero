-- EdgeQuake PostgreSQL extensions initialization
-- Creates required extensions on first database start.
-- Table creation is handled by EdgeQuake's SQLx migrations.

-- Set search path for the edgequake user
ALTER USER edgequake SET search_path TO public;

-- UUID generation
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- pgvector for vector similarity search
CREATE EXTENSION IF NOT EXISTS vector;

-- Apache AGE for graph database support (optional, may not be available)
DO $$
BEGIN
    CREATE EXTENSION IF NOT EXISTS age;
    LOAD 'age';
    SET search_path = ag_catalog, "$user", public;
    RAISE NOTICE 'Apache AGE extension loaded successfully';
EXCEPTION WHEN OTHERS THEN
    RAISE NOTICE 'Apache AGE extension not available: %. Graph features will use fallback storage.', SQLERRM;
END
$$;

-- Trigram index support
CREATE EXTENSION IF NOT EXISTS pg_trgm;

DO $$ BEGIN RAISE NOTICE 'EdgeQuake extensions initialized.'; END $$;
