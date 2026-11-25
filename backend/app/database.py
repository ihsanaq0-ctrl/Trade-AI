"""
Database module for Trade-AI.
Uses Supabase with the service role key on the server side so RLS is bypassed.
Provides per-thread Supabase clients so concurrent asyncio.to_thread queries
never collide on a single shared httpx connection pool (prevents WinError 10054),
plus transparent retry + socket reset on transient Cloudflare/TLS WinError 10054 drops.
"""

import threading
import time
import httpx
from postgrest.exceptions import APIError
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


def reset_thread_supabase():
    """Drop the current thread's cached Supabase/httpx connection so a fresh socket is opened."""
    client = getattr(_thread_local, "client", None)
    _thread_local.client = None
    try:
        if client is not None and hasattr(client, "postgrest") and hasattr(client.postgrest, "session"):
            client.postgrest.session.close()
    except Exception:
        pass


class _ResilientQuery:
    """Replays chained PostgREST query calls cleanly on transient transport/TLS drops (WinError 10054)."""

    def __init__(self, root_fn, ops=None):
        self._root_fn = root_fn
        self._ops = ops or []

    def __getattr__(self, item: str):
        if item == "execute":
            return self._execute

        def _chained(*args, **kwargs):
            return _ResilientQuery(self._root_fn, [*self._ops, (item, args, kwargs)])

        return _chained

    def _execute(self, *args, **kwargs):
        last_exc = None
        for attempt in range(3):
            try:
                client = get_thread_supabase()
                q = self._root_fn(client)
                for op_name, op_args, op_kwargs in self._ops:
                    q = getattr(q, op_name)(*op_args, **op_kwargs)
                return q.execute(*args, **kwargs)
            except APIError:
                raise
            except Exception as exc:
                last_exc = exc
                msg = str(exc)
                is_transient = isinstance(exc, (httpx.TransportError, OSError)) or any(
                    tok in msg for tok in ("10054", "Connection", "RemoteProtocol", "timed out", "EOF", "reset")
                )
                if not is_transient or attempt == 2:
                    raise
                reset_thread_supabase()
                time.sleep(0.15 * (attempt + 1))
        raise last_exc


class _ThreadSafeSupabaseProxy:
    def table(self, name: str):
        return _ResilientQuery(lambda c: c.table(name))

    def from_(self, name: str):
        return _ResilientQuery(lambda c: c.from_(name))

    def rpc(self, fn: str, params=None):
        return _ResilientQuery(lambda c: c.rpc(fn, params))

    @property
    def auth(self):
        return _root_client.auth

    def __getattr__(self, item: str):
        return getattr(_root_client, item)


supabase = _ThreadSafeSupabaseProxy()
