"""
Database module for Trade-AI.
Uses Supabase with the service role key on the server side so RLS is bypassed.
Provides per-thread Supabase clients so concurrent asyncio.to_thread queries
never collide on a single shared httpx connection pool (prevents WinError 10054).
"""

import threading
from supabase import create_client
from app.config import settings

_key = settings.supabase_service_key or settings.supabase_key
_thread_local = threading.local()
_root_client = create_client(settings.supabase_url, _key)


def get_thread_supabase():
    """Return a Supabase client dedicated to the current OS thread."""
    client = getattr(_thread_local, "client", None)
    if client is None:
        client = create_client(settings.supabase_url, _key)
        _thread_local.client = client
    return client


class _ThreadSafeSupabaseProxy:
    def table(self, name: str):
        return get_thread_supabase().table(name)

    def from_(self, name: str):
        return get_thread_supabase().from_(name)

    def rpc(self, fn: str, params=None):
        return get_thread_supabase().rpc(fn, params)

    @property
    def auth(self):
        return _root_client.auth

    def __getattr__(self, item: str):
        return getattr(_root_client, item)


supabase = _ThreadSafeSupabaseProxy()
