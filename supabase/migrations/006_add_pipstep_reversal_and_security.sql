-- Trade-AI — Migration 006:
-- 1. Allow 'pipstep_reversal' and custom/ai_committee strategies in bot_settings
-- 2. Allow 'elite' in profiles.plan
-- 3. Prevent client-side privilege escalation on profiles.plan via RLS trigger
--
-- IDEMPOTENT — safe to run in Supabase Dashboard -> SQL Editor.

ALTER TABLE public.bot_settings DROP CONSTRAINT IF EXISTS bot_settings_strategy_check;
ALTER TABLE public.bot_settings ADD CONSTRAINT bot_settings_strategy_check
  CHECK (strategy IN (
    'smart_money', 'mirror', 'mmc_mirror', 'classic', 'full_confluence',
    'scalp', 'scalp_pyramid', 'scalp_fvg', 'signal_strength_hedge',
    'nyao_scalper', 'trading_agents', 'ai_committee', 'pipstep_reversal'
  ));

ALTER TABLE public.profiles DROP CONSTRAINT IF EXISTS profiles_plan_check;
ALTER TABLE public.profiles ADD CONSTRAINT profiles_plan_check
  CHECK (plan IN ('free', 'pro', 'elite'));

-- Prevent regular authenticated users from modifying their own `plan` column directly
CREATE OR REPLACE FUNCTION public.prevent_client_plan_escalation()
RETURNS trigger
LANGUAGE plpgsql
SECURITY DEFINER
AS $$
BEGIN
  IF NEW.plan IS DISTINCT FROM OLD.plan THEN
    IF current_setting('request.jwt.claim.role', true) = 'authenticated' THEN
      RAISE EXCEPTION 'Unauthorized: plan tier can only be updated by server billing';
    END IF;
  END IF;
  RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS trg_prevent_client_plan_escalation ON public.profiles;
CREATE TRIGGER trg_prevent_client_plan_escalation
  BEFORE UPDATE ON public.profiles
  FOR EACH ROW
  EXECUTE FUNCTION public.prevent_client_plan_escalation();
