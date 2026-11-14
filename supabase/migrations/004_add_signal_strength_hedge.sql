-- TradeAI Pro — Migration 004: add `signal_strength_hedge` to the bot_settings
-- strategy CHECK constraint.
--
-- The backend engine, strategy file, frontend UI and strategy_store all support
-- signal_strength_hedge (see bot_engine.py _get_strategy / _bot_loop_signal_strength_hedge,
-- app/services/strategies/signal_strength_hedge.py), but creating a bot with it
-- fails with 400 "violates check constraint bot_settings_strategy_check" because
-- the DB constraint predates the strategy.
--
-- Same fix pattern as 002_add_strategies.sql. IDEMPOTENT — safe to re-run.
-- Run in Supabase Dashboard → SQL Editor → New query → Run.

ALTER TABLE bot_settings DROP CONSTRAINT IF EXISTS bot_settings_strategy_check;
ALTER TABLE bot_settings ADD CONSTRAINT bot_settings_strategy_check
  CHECK (strategy IN ('smart_money', 'mirror', 'classic', 'full_confluence',
                      'scalp', 'scalp_pyramid', 'scalp_fvg',
                      'signal_strength_hedge'));

-- Verify: should show the new constraint with signal_strength_hedge allowed
SELECT conname, pg_get_constraintdef(oid)
FROM pg_constraint
WHERE conname = 'bot_settings_strategy_check';
