import os
import sys
from dotenv import load_dotenv

# Ensure we can import from the app module
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
load_dotenv()

from app.database import supabase

def clean_stale_bots():
    print("Starting cleanup of stale bots...")
    try:
        # Delete bots with status 'error'
        res_error = supabase.table('bot_settings').delete().eq('status', 'error').execute()
        print(f"Deleted {len(res_error.data)} bots with status 'error'.")

        # Delete bots with status 'stopped'
        res_stopped = supabase.table('bot_settings').delete().eq('status', 'stopped').execute()
        print(f"Deleted {len(res_stopped.data)} bots with status 'stopped'.")

        print("Cleanup complete. The database is ready for a fresh start.")
    except Exception as e:
        print(f"An error occurred during cleanup: {e}")

if __name__ == "__main__":
    clean_stale_bots()
