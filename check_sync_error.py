import psycopg2
import requests
import json

DATABASE_URL = "postgresql://chroma_user:xqIF9T5U6LhySuSw86JqWYf7qtyGDXy8@dpg-d16mkandiees73db52u0-a.oregon-postgres.render.com/chroma_ha"

print("🔍 CHECKING DETAILED SYNC ERROR")
print("=" * 50)

# Check the exact error message
with psycopg2.connect(DATABASE_URL) as conn:
    with conn.cursor() as cur:
        cur.execute("SELECT path, error_message FROM unified_wal_writes WHERE status = 'failed' ORDER BY created_at DESC LIMIT 1")
        result = cur.fetchone()
        if result:
            print(f"Failed path: {result[0]}")
            print(f"Error: {result[1]}")
            
            # Check if this path has the correct collection ID mapping
            primary_id = "7b9ee675-09b3-4911-8b9b-8f04ca8f7809"
            replica_id = "5beb705b-7903-4f7e-8fc9-3a39ce3a2510"
            
            print()
            print("COLLECTION ID ANALYSIS:")
            print(f"Primary ID:  {primary_id}")
            print(f"Replica ID:  {replica_id}")
            print(f"Path contains Primary: {primary_id in result[0]}")
            print(f"Path contains Replica: {replica_id in result[0]}")
            
            if primary_id in result[0]:
                print("❌ Path still uses PRIMARY ID instead of REPLICA ID!")
                print("🔧 Collection ID mapping not being applied in sync")
            elif replica_id in result[0]:
                print("✅ Path uses correct REPLICA ID")
                print("❌ Issue is with the request itself, not mapping")
            else:
                print("⚠️ Path uses unknown collection ID")
        else:
            print("No failed entries found")

# Test a manual sync to see what happens
print()
print("🧪 TESTING MANUAL SYNC")
print("=" * 50)

# Create a test WAL entry and see if it gets processed correctly
primary_id = "7b9ee675-09b3-4911-8b9b-8f04ca8f7809"

test_payload = {
    "embeddings": [[0.3] * 3072],
    "documents": ["Manual sync test to debug WAL"],
    "metadatas": [{"test": "manual_sync_debug"}],
    "ids": ["manual_sync_debug_1"]
}

print("Uploading test document...")
upload_response = requests.post(
    f"https://chroma-load-balancer.onrender.com/api/v2/tenants/default_tenant/databases/default_database/collections/{primary_id}/add",
    headers={"Content-Type": "application/json"},
    json=test_payload,
    timeout=30
)

print(f"Upload status: {upload_response.status_code}")

if upload_response.status_code in [200, 201]:
    print("✅ Upload successful - WAL entry should be created")
    
    # Check if new WAL entry was created
    import time
    time.sleep(2)
    
    with psycopg2.connect(DATABASE_URL) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT path, status FROM unified_wal_writes ORDER BY created_at DESC LIMIT 1")
            latest = cur.fetchone()
            if latest:
                print(f"Latest WAL entry: {latest[1]} - {latest[0][:60]}...")
                
                # Check if it uses correct replica ID
                replica_id = "5beb705b-7903-4f7e-8fc9-3a39ce3a2510"
                if replica_id in latest[0]:
                    print("✅ WAL entry uses correct replica ID")
                else:
                    print("❌ WAL entry still uses wrong collection ID")
            else:
                print("❌ No WAL entries found")
else:
    print(f"❌ Upload failed: {upload_response.text}") 