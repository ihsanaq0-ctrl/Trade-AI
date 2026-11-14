-- Add new strategies to the bot_settings strategy CHECK constraint.
-- The original 001_schema.sql only allowed the 5 original strategies; the UI
-- offers scalp_pyramid and scalp_fvg, so creating those bots was rejected by
-- PostgREST with a 400 — the bot never ran at all.
ALTER TABLE bot_settings DROP CONSTRAINT IF EXISTS bot_settings_strategy_check;
ALTER TABLE bot_settings ADD CONSTRAINT bot_settings_strategy_check
  CHECK (strategy IN ('smart_money', 'mirror', 'classic', 'full_confluence',
                      'scalp', 'scalp_pyramid', 'scalp_fvg'));

-- bot_events table — used by the drawdown kill switch to log STOP_TRADING events.
-- It was referenced in code (scalp_scheduler._execute_stop_trading) but never
-- created in 001_schema.sql, so every drawdown halt failed to persist its log.
CREATE TABLE IF NOT EXISTS bot_events (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  bot_id UUID REFERENCES bot_settings(id) ON DELETE CASCADE,
  event_type TEXT NOT NULL,
  message TEXT,
  positions_closed INT DEFAULT 0,
  created_at TIMESTAMPTZ DEFAULT NOW()
);

ALTER TABLE bot_events ENABLE ROW LEVEL SECURITY;
