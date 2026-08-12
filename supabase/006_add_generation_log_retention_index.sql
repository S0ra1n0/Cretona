-- =============================================================================
-- Migration 006 - generation-log retention index
--
-- STATUS: PREPARED, NOT APPLIED. Do not run this against the remote Supabase
-- project without Bruce's approval. It is additive and re-runnable.
--
-- WHY: B-4 deletes expired generation_logs oldest-first in bounded batches.
-- The existing (project_id, created_at) index serves per-project history but
-- cannot efficiently serve a table-wide created_at cutoff. This index keeps
-- the maintenance scan bounded as the audit table grows.
--
-- Apply after 005_add_poll_lease.sql. CONCURRENTLY avoids blocking ordinary
-- inserts while the index is built, and therefore must not run inside BEGIN.
-- =============================================================================

create index concurrently if not exists idx_logs_retention
  on public.generation_logs (created_at asc, id asc);

-- Verify:
--   select indexdef from pg_indexes
--   where schemaname = 'public' and indexname = 'idx_logs_retention';
--   -- expect one row containing (created_at, id)
--
-- Rollback (also outside a transaction):
--   drop index concurrently if exists public.idx_logs_retention;
