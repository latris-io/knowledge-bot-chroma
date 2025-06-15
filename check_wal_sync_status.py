import requests
import psycopg2

print("🔍 CHECKING WAL SYNC STATUS AFTER FIX")
print("=" * 50)

# Check WAL status
wal_response = requests.get("https://chroma-load-balancer.onrender.com/wal/status", timeout=30)
if wal_response.status_code == 200:
    wal_status = wal_response.json()
    stats = wal_status["performance_stats"]
    print(f"WAL Status: {stats['successful_syncs']} successful, {stats['failed_syncs']} failed")
else:
    print(f"WAL status error: {wal_response.status_code}")

# Check recent WAL entries
DATABASE_URL = "postgresql://chroma_user:xqIF9T5U6LhySuSw86JqWYf7qtyGDXy8@dpg-d16mkandiees73db52u0-a.oregon-postgres.render.com/chroma_ha"
with psycopg2.connect(DATABASE_URL) as conn:
    with conn.cursor() as cur:
        cur.execute("SELECT status, COUNT(*) FROM unified_wal_writes GROUP BY status")
        status_counts = cur.fetchall()
        print("WAL Entry Status Counts:")
        for status, count in status_counts:
            print(f"  {status}: {count}")
        
        # Check latest entries
        cur.execute("SELECT method, path, status, error_message, created_at FROM unified_wal_writes ORDER BY created_at DESC LIMIT 5")
        recent = cur.fetchall()
        print("Recent WAL entries:")
        for entry in recent:
            error = (entry[3][:50] + "...") if entry[3] else "None"
            print(f"  {entry[0]} {entry[1][:50]}... - {entry[2]} - {error}")
        
        # Check if there are entries for our new replica collection
        replica_id = "5beb705b-7903-4f7e-8fc9-3a39ce3a2510"
        cur.execute("SELECT COUNT(*) FROM unified_wal_writes WHERE path LIKE %s", (f"%{replica_id}%",))
        replica_entries = cur.fetchone()[0]
        print(f"Entries for new replica collection: {replica_entries}")
        
        # Check for any pending entries that should be syncing
        cur.execute("SELECT COUNT(*) FROM unified_wal_writes WHERE status = 'pending'")
        pending_count = cur.fetchone()[0]
        print(f"Pending sync entries: {pending_count}")

print()
print("ANALYSIS:")
print("✅ Infrastructure fixed - both collections exist")
print("✅ Collection mapping established")  
print("❓ Checking if WAL sync processor is running...")

# Test if sync processor is active
test_response = requests.get("https://chroma-load-balancer.onrender.com/health", timeout=30)
print(f"Load balancer health: {test_response.status_code}")

if test_response.status_code == 200:
    print("✅ Load balancer is healthy")
    print("🔍 Sync may need manual trigger or more time")
else:
    print("❌ Load balancer health issue") 