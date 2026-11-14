-- TradeAI Pro Database Schema
-- Run this in Supabase SQL Editor

-- 1. Profiles table (extends auth.users)
CREATE TABLE IF NOT EXISTS profiles (
  id UUID PRIMARY KEY REFERENCES auth.users(id) ON DELETE CASCADE,
  name TEXT,
  email TEXT,
  plan TEXT DEFAULT 'free' CHECK (plan IN ('free', 'pro')),
  created_at TIMESTAMPTZ DEFAULT NOW(),
  updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- 2. Accounts table (broker connections)
CREATE TABLE IF NOT EXISTS accounts (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id UUID REFERENCES profiles(id) ON DELETE CASCADE NOT NULL,
  nickname TEXT DEFAULT '',
  broker TEXT DEFAULT 'metaapi',
  login TEXT NOT NULL,
  server TEXT NOT NULL,
  account_type TEXT DEFAULT 'demo' CHECK (account_type IN ('demo', 'live')),
  color TEXT DEFAULT '#00d4ff',
  balance DECIMAL DEFAULT 0,
  equity DECIMAL DEFAULT 0,
  profit DECIMAL DEFAULT 0,
  status TEXT DEFAULT 'disconnected' CHECK (status IN ('connected', 'disconnected', 'error')),
  connected_at TIMESTAMPTZ,
  created_at TIMESTAMPTZ DEFAULT NOW(),
  UNIQUE(user_id, login, server)
);

-- 3. Bot settings table
CREATE TABLE IF NOT EXISTS bot_settings (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id UUID REFERENCES profiles(id) ON DELETE CASCADE NOT NULL,
  account_id UUID REFERENCES accounts(id) ON DELETE CASCADE NOT NULL,
  strategy TEXT NOT NULL CHECK (strategy IN ('smart_money', 'mirror', 'classic', 'full_confluence', 'scalp', 'scalp_pyramid', 'scalp_fvg', 'signal_strength_hedge', 'nyao_scalper')),
  status TEXT DEFAULT 'stopped' CHECK (status IN ('running', 'stopped', 'error')),
  pair TEXT DEFAULT 'EURUSD',
  timeframe TEXT DEFAULT 'H1',
  lot_size DECIMAL DEFAULT 0.01,
  take_profit DECIMAL DEFAULT 50,
  stop_loss DECIMAL DEFAULT 25,
  max_trades INT DEFAULT 1,
  max_daily_loss DECIMAL DEFAULT 100,
  config JSONB DEFAULT '{}',
  created_at TIMESTAMPTZ DEFAULT NOW(),
  updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- 4. Trades table
CREATE TABLE IF NOT EXISTS trades (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id UUID REFERENCES profiles(id) ON DELETE CASCADE NOT NULL,
  account_id UUID REFERENCES accounts(id) ON DELETE CASCADE,
  bot_id UUID REFERENCES bot_settings(id) ON DELETE SET NULL,
  strategy TEXT,
  pair TEXT NOT NULL,
  type TEXT NOT NULL CHECK (type IN ('buy', 'sell')),
  lot_size DECIMAL DEFAULT 0.01,
  open_price DECIMAL NOT NULL,
  close_price DECIMAL,
  stop_loss DECIMAL,
  take_profit DECIMAL,
  profit DECIMAL,
  pips DECIMAL,
  status TEXT DEFAULT 'open' CHECK (status IN ('open', 'closed', 'cancelled')),
  opened_at TIMESTAMPTZ DEFAULT NOW(),
  closed_at TIMESTAMPTZ
);

-- 5. Subscriptions table (Gumroad)
CREATE TABLE IF NOT EXISTS subscriptions (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id UUID REFERENCES profiles(id) ON DELETE CASCADE NOT NULL,
  gumroad_license_key TEXT UNIQUE NOT NULL,
  gumroad_product_id TEXT,
  plan TEXT DEFAULT 'pro',
  status TEXT DEFAULT 'active' CHECK (status IN ('active', 'expired', 'cancelled')),
  current_period_start TIMESTAMPTZ,
  current_period_end TIMESTAMPTZ,
  created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Indexes
CREATE INDEX IF NOT EXISTS idx_accounts_user_id ON accounts(user_id);
CREATE INDEX IF NOT EXISTS idx_bot_settings_user_id ON bot_settings(user_id);
CREATE INDEX IF NOT EXISTS idx_bot_settings_account_id ON bot_settings(account_id);
CREATE INDEX IF NOT EXISTS idx_trades_user_id ON trades(user_id);
CREATE INDEX IF NOT EXISTS idx_trades_account_id ON trades(account_id);
CREATE INDEX IF NOT EXISTS idx_trades_bot_id ON trades(bot_id);
CREATE INDEX IF NOT EXISTS idx_trades_opened_at ON trades(opened_at DESC);
CREATE INDEX IF NOT EXISTS idx_subscriptions_user_id ON subscriptions(user_id);

-- Enable Row Level Security
ALTER TABLE profiles ENABLE ROW LEVEL SECURITY;
ALTER TABLE accounts ENABLE ROW LEVEL SECURITY;
ALTER TABLE bot_settings ENABLE ROW LEVEL SECURITY;
ALTER TABLE trades ENABLE ROW LEVEL SECURITY;
ALTER TABLE subscriptions ENABLE ROW LEVEL SECURITY;

-- RLS Policies: users can CRUD their own rows
CREATE POLICY "Users can view own profile" ON profiles FOR SELECT USING (auth.uid() = id);
CREATE POLICY "Users can update own profile" ON profiles FOR UPDATE USING (auth.uid() = id);

CREATE POLICY "Users can view own accounts" ON accounts FOR SELECT USING (auth.uid() = user_id);
CREATE POLICY "Users can insert own accounts" ON accounts FOR INSERT WITH CHECK (auth.uid() = user_id);
CREATE POLICY "Users can update own accounts" ON accounts FOR UPDATE USING (auth.uid() = user_id);
CREATE POLICY "Users can delete own accounts" ON accounts FOR DELETE USING (auth.uid() = user_id);

CREATE POLICY "Users can view own bot settings" ON bot_settings FOR SELECT USING (auth.uid() = user_id);
CREATE POLICY "Users can insert own bot settings" ON bot_settings FOR INSERT WITH CHECK (auth.uid() = user_id);
CREATE POLICY "Users can update own bot settings" ON bot_settings FOR UPDATE USING (auth.uid() = user_id);
CREATE POLICY "Users can delete own bot settings" ON bot_settings FOR DELETE USING (auth.uid() = user_id);

CREATE POLICY "Users can view own trades" ON trades FOR SELECT USING (auth.uid() = user_id);
CREATE POLICY "Users can insert own trades" ON trades FOR INSERT WITH CHECK (auth.uid() = user_id);
CREATE POLICY "Users can update own trades" ON trades FOR UPDATE USING (auth.uid() = user_id);

CREATE POLICY "Users can view own subscriptions" ON subscriptions FOR SELECT USING (auth.uid() = user_id);

-- Auto-create profile on signup
CREATE OR REPLACE FUNCTION public.handle_new_user()
RETURNS trigger
LANGUAGE plpgsql
SECURITY DEFINER SET search_path = public
AS $$
BEGIN
  INSERT INTO public.profiles (id, name, email)
  VALUES (
    NEW.id,
    COALESCE(NEW.raw_user_meta_data->>'full_name', NEW.email),
    NEW.email
  );
  RETURN NEW;
END;
$$;

CREATE OR REPLACE TRIGGER on_auth_user_created
  AFTER INSERT ON auth.users
  FOR EACH ROW
  EXECUTE FUNCTION public.handle_new_user();
