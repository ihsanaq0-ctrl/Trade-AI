"""
Database module for TradeAI Pro.
Uses Supabase with the service role key on the server side so RLS is bypassed.
"""

from supabase import create_client
from app.config import settings

# Server-side client — uses service role key (bypasses RLS) if available,
# otherwise falls back to anon key.
# The service role key is safe here because the backend authenticates users
# via JWT middleware before any data access.
key = settings.supabase_service_key or settings.supabase_key
supabase = create_client(settings.supabase_url, key)