-- TradeAI Pro — Migration 003: Align live `accounts` table with backend code.
-- Live schema is the OLD plan-schema (`type`, `connected`, `metaapi_id`) and is
-- MISSING the columns the backend inserts: `password`, `status`, `connected_at`.
-- Result without this: POST /api/accounts → 500 PGRST204 "Could not find the
-- 'password' column of 'accounts' in the schema cache".
--
-- This migration is IDEMPOTENT — safe to run multiple times.
-- Run in Supabase Dashboard → SQL Editor → New query → Run.

-- 1. Add the columns the backend expects (IF NOT EXISTS = safe to re-run)
ALTER TABLE public.accounts
    ADD COLUMN IF NOT EXISTS password TEXT,
    ADD COLUMN IF NOT EXISTS status TEXT DEFAULT 'disconnected',
    ADD COLUMN IF NOT EXISTS connected_at TIMESTAMPTZ;

-- 2. Backfill status for any existing rows (old table had no status)
UPDATE public.accounts SET status = 'disconnected' WHERE status IS NULL;

-- 3. Make the code's status values valid (constraint on status if it exists is
--    the old one: ('connected','disconnected','error') — keep compatible)
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'accounts_status_check'
    ) THEN
        ALTER TABLE public.accounts
            ADD CONSTRAINT accounts_status_check
            CHECK (status IN ('connected', 'disconnected', 'error'));
    END IF;
END$$;

-- 4. Ensure account_type CHECK exists (already present, but keep consistent)
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'accounts_account_type_check'
    ) THEN
        ALTER TABLE public.accounts
            ADD CONSTRAINT accounts_account_type_check
            CHECK (account_type IN ('demo', 'live'));
    END IF;
END$$;

-- 5. Verify — should list: id, user_id, nickname, broker, login, server,
--    account_type, password, status, connected_at, balance, equity, profit, ...
SELECT column_name, data_type
FROM information_schema.columns
WHERE table_schema = 'public' AND table_name = 'accounts'
ORDER BY ordinal_position;
