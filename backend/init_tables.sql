-- TradeAI Pro: Missing Tables
-- Run this in Supabase Dashboard → SQL Editor

-- 1. bot_settings
CREATE TABLE IF NOT EXISTS public.bot_settings (
    id UUID PRIMARY KEY,
    user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    account_id TEXT,
    strategy TEXT NOT NULL,
    status TEXT DEFAULT 'stopped',
    pair TEXT,
    timeframe TEXT,
    lot_size NUMERIC DEFAULT 0.01,
    take_profit NUMERIC,
    stop_loss NUMERIC,
    max_trades INTEGER DEFAULT 1,
    max_daily_loss NUMERIC,
    config JSONB DEFAULT '{}',
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);
ALTER TABLE public.bot_settings ENABLE ROW LEVEL SECURITY;

CREATE POLICY "users_manage_own_bots"
    ON public.bot_settings FOR ALL
    USING (auth.uid() = user_id)
    WITH CHECK (auth.uid() = user_id);

-- 2. trades
CREATE TABLE IF NOT EXISTS public.trades (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    bot_id UUID REFERENCES public.bot_settings(id) ON DELETE SET NULL,
    account_id TEXT,
    symbol TEXT,
    direction TEXT,
    volume NUMERIC,
    open_price NUMERIC,
    close_price NUMERIC,
    stop_loss NUMERIC,
    take_profit NUMERIC,
    status TEXT DEFAULT 'open',
    profit NUMERIC,
    strategy TEXT,
    opened_at TIMESTAMPTZ DEFAULT NOW(),
    closed_at TIMESTAMPTZ,
    reason TEXT,
    metadata JSONB DEFAULT '{}',
    ticket TEXT
);
CREATE INDEX IF NOT EXISTS idx_trades_ticket ON public.trades(ticket);
ALTER TABLE public.trades ENABLE ROW LEVEL SECURITY;

CREATE POLICY "users_view_own_trades"
    ON public.trades FOR SELECT
    USING (auth.uid() = user_id);

CREATE POLICY "users_insert_own_trades"
    ON public.trades FOR INSERT
    WITH CHECK (auth.uid() = user_id);

CREATE POLICY "users_update_own_trades"
    ON public.trades FOR UPDATE
    USING (auth.uid() = user_id);

-- 3. subscriptions
CREATE TABLE IF NOT EXISTS public.subscriptions (
    id UUID PRIMARY KEY,
    user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    gumroad_license_key TEXT,
    gumroad_product_id TEXT,
    plan TEXT DEFAULT 'free',
    status TEXT DEFAULT 'inactive',
    current_period_start TIMESTAMPTZ,
    current_period_end TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT NOW()
);
ALTER TABLE public.subscriptions ENABLE ROW LEVEL SECURITY;

CREATE POLICY "users_view_own_subscription"
    ON public.subscriptions FOR SELECT
    USING (auth.uid() = user_id);

CREATE POLICY "users_insert_own_subscription"
    ON public.subscriptions FOR INSERT
    WITH CHECK (auth.uid() = user_id);

CREATE POLICY "users_update_own_subscription"
    ON public.subscriptions FOR UPDATE
    USING (auth.uid() = user_id);