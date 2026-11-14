-- TradeAI Pro — Migration 005: add `nyao_scalper` to the bot_settings
-- strategy CHECK constraint.
--
-- Adds 'nyao_scalper' to the allowed strategies in bot_settings.
--
-- IDEMPOTENT — safe to re-run.
-- Run in Supabase Dashboard → SQL Editor → New query → Run.

ALTER TABLE bot_settings DROP CONSTRAINT IF EXISTS bot_settings_strategy_check;
ALTER TABLE bot_settings ADD CONSTRAINT bot_settings_strategy_check
  CHECK (strategy IN ('smart_money', 'mirror', 'classic', 'full_confluence',
                      'scalp', 'scalp_pyramid', 'scalp_fvg',
                      'signal_strength_hedge', 'nyao_scalper'));

-- Verify: should show the new constraint with nyao_scalper allowed
SELECT conname, pg_get_constraintdef(oid)
FROM pg_constraint
WHERE conname = 'bot_settings_strategy_check';
