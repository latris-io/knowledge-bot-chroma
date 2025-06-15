import psycopg2
import requests

DATABASE_URL = "postgresql://chroma_user:xqIF9T5U6LhySuSw86JqWYf7qtyGDXy8@dpg-d16mkandiees73db52u0-a.oregon-postgres.render.com/chroma_ha"

print("🔍 CHECKING SYNC EXECUTION STATUS")
print("=" * 50)

# Check WAL entry statuses
with psycopg2.connect(DATABASE_URL) as conn:
    with conn.cursor() as cur:
        print("1. WAL Entry Status Distribution:")
        cur.execute("SELECT status, COUNT(*) FROM unified_wal_writes GROUP BY status ORDER BY status")
        for status, count in cur.fetchall():
            print(f"   {status}: {count}")
        
        print("\n2. Recent entries (last 5):")
        cur.execute("SELECT status, target_instance, path, error_message FROM unified_wal_writes ORDER BY created_at DESC LIMIT 5")
        for status, target, path, error in cur.fetchall():
            error_short = (error[:50] + "...") if error else "None"
            print(f"   {status} - {target} - {path[:40]}... - {error_short}")
        
        print("\n3. Entries ready for sync:")
        cur.execute("SELECT COUNT(*) FROM unified_wal_writes WHERE status = 'executed' AND retry_count < 3")
        ready_count = cur.fetchone()[0]
        print(f"   Ready to sync: {ready_count}")
        
        if ready_count > 0:
            print("   Sample ready entries:")
            cur.execute("SELECT write_id, target_instance, path FROM unified_wal_writes WHERE status = 'executed' AND retry_count < 3 LIMIT 3")
            for write_id, target, path in cur.fetchall():
                print(f"     {write_id[:8]}: {target} - {path[:50]}...")

# Check load balancer health
print("\n4. Load Balancer Health:")
try:
    health_response = requests.get("https://chroma-load-balancer.onrender.com/health", timeout=30)
    print(f"   Health status: {health_response.status_code}")
    if health_response.status_code == 200:
        health_data = health_response.json()
        print(f"   Status: {health_data.get('status')}")
        print(f"   Healthy instances: {health_data.get('healthy_instances')}")
    else:
        print(f"   Health response: {health_response.text[:100]}")
except Exception as e:
    print(f"   Health check error: {e}")

# Check if sync service is running
print("\n5. Sync Service Status:")
try:
    wal_response = requests.get("https://chroma-load-balancer.onrender.com/wal/status", timeout=30)
    if wal_response.status_code == 200:
        wal_data = wal_response.json()
        print(f"   WAL system status: OK")
        print(f"   Is syncing: {wal_data.get('wal_system', {}).get('is_syncing', 'Unknown')}")
        print(f"   Pending writes: {wal_data.get('wal_system', {}).get('pending_writes', 'Unknown')}")
        
        perf_stats = wal_data.get('performance_stats', {})
        print(f"   Successful syncs: {perf_stats.get('successful_syncs', 0)}")
        print(f"   Failed syncs: {perf_stats.get('failed_syncs', 0)}")
    else:
        print(f"   WAL status error: {wal_response.status_code}")
except Exception as e:
    print(f"   WAL status error: {e}")

print("\nANALYSIS:")
if ready_count > 0:
    print("✅ WAL entries are ready for sync")
    print("❓ Sync processor may be paused or encountering errors")
    print("🔧 Try manual sync trigger or check load balancer logs")
else:
    print("⚠️ No entries ready for sync - all may be failed or already synced")
    print("🔧 Check failed entries and retry logic") 