#!/usr/bin/env python3
import psycopg2
import requests
from datetime import datetime

DATABASE_URL = "postgresql://chroma_user:xqIF9T5U6LhySuSw86JqWYf7qtyGDXy8@dpg-d16mkandiees73db52u0-a.oregon-postgres.render.com/chroma_ha"
replica_id = "4e5e29a0-38b9-4ce4-b589-3ce01e0d6528"

print("🔍 CHECKING CURRENT SYNC STATUS")
print("=" * 50)

# Check most recent failed sync
with psycopg2.connect(DATABASE_URL) as conn:
    with conn.cursor() as cur:
        cur.execute("SELECT path, error_message, updated_at FROM unified_wal_writes WHERE status = 'failed' ORDER BY updated_at DESC LIMIT 1")
        result = cur.fetchone()
        
        if result:
            path, error_msg, updated_at = result
            print(f"Most recent failed sync:")
            print(f"   Path: {path}")
            print(f"   Error: {error_msg[:100]}...")
            print(f"   Time: {updated_at}")
            print(f"   Contains Replica ID: {replica_id in path}")
            
            if replica_id in path:
                print("   ✅ Collection ID mapping is working!")
                print("   ❌ Issue must be elsewhere...")
                
                # Test replica collection directly
                print("\nTesting replica collection directly...")
                test_response = requests.get(f"https://chroma-replica.onrender.com/api/v2/tenants/default_tenant/databases/default_database/collections/{replica_id}", timeout=30)
                print(f"   Replica collection status: {test_response.status_code}")
                
                if test_response.status_code != 200:
                    print(f"   ❌ Replica collection doesn't exist or is inaccessible!")
                    print(f"   Response: {test_response.text}")
                else:
                    print("   ✅ Replica collection exists")
            else:
                print("   ❌ Still using wrong collection ID")
        else:
            print("No failed sync entries found")

# Check if there are any pending/executed entries for our collection
print("\nChecking for pending sync entries...")
with psycopg2.connect(DATABASE_URL) as conn:
    with conn.cursor() as cur:
        cur.execute("SELECT COUNT(*) FROM unified_wal_writes WHERE status IN ('pending', 'executed') AND path LIKE %s", (f'%{replica_id}%',))
        pending_count = cur.fetchone()[0]
        print(f"Pending/executed entries for knowledge_base: {pending_count}")

print("\nWAL Status:")
wal_response = requests.get("https://chroma-load-balancer.onrender.com/wal/status", timeout=30)
if wal_response.status_code == 200:
    wal_status = wal_response.json()
    stats = wal_status['performance_stats']
    print(f"   Successful syncs: {stats['successful_syncs']}")
    print(f"   Failed syncs: {stats['failed_syncs']}")
else:
    print(f"   WAL status error: {wal_response.status_code}")

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