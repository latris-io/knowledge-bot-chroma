#!/usr/bin/env python3
import psycopg2
from datetime import datetime

DATABASE_URL = "postgresql://chroma_user:xqIF9T5U6LhySuSw86JqWYf7qtyGDXy8@dpg-d16mkandiees73db52u0-a.oregon-postgres.render.com/chroma_ha"

try:
    with psycopg2.connect(DATABASE_URL) as conn:
        with conn.cursor() as cursor:
            print("🔍 SYNC SERVICE STATUS CHECK")
            print("=" * 50)
            
            # Check sync workers
            cursor.execute("SELECT COUNT(*), MAX(last_heartbeat) FROM sync_workers WHERE last_heartbeat > NOW() - INTERVAL '30 minutes'")
            active_workers, last_heartbeat = cursor.fetchone()
            print(f"🔧 Active Workers (30 min): {active_workers}")
            print(f"📅 Last Heartbeat: {last_heartbeat}")
            
            # Check recent sync history
            cursor.execute("SELECT COUNT(*), MAX(sync_started_at), MAX(sync_completed_at) FROM sync_history WHERE sync_started_at > NOW() - INTERVAL '1 hour'")
            recent_syncs, last_start, last_complete = cursor.fetchone()
            print(f"📊 Recent Syncs (1 hour): {recent_syncs}")
            print(f"🚀 Last Sync Start: {last_start}")
            print(f"✅ Last Sync Complete: {last_complete}")
            
            # Check sync collections status
            cursor.execute("SELECT COUNT(*), COUNT(CASE WHEN sync_status = 'completed' THEN 1 END) FROM sync_collections")
            total_cols, completed_cols = cursor.fetchone()
            print(f"📦 Total Collections Tracked: {total_cols}")
            print(f"✅ Completed Collections: {completed_cols}")
            
            # Check if sync service tables have any data at all
            cursor.execute("SELECT COUNT(*) FROM sync_workers")
            total_workers = cursor.fetchone()[0]
            cursor.execute("SELECT COUNT(*) FROM sync_history")
            total_history = cursor.fetchone()[0]
            print(f"👥 Total Workers Ever: {total_workers}")
            print(f"📚 Total Sync History: {total_history}")
            
            # Determine sync service status
            if active_workers > 0:
                status = "🟢 ACTIVE"
            elif total_workers > 0 or total_history > 0:
                status = "🟡 IDLE (but has been active)"
            else:
                status = "🔴 NOT DEPLOYED"
            
            print(f"\n🎯 SYNC SERVICE STATUS: {status}")
            
except Exception as e:
    print(f"❌ Database check failed: {e}") 