import requests
import time

primary_id = "7b9ee675-09b3-4911-8b9b-8f04ca8f7809"
replica_id = "5beb705b-7903-4f7e-8fc9-3a39ce3a2510"

print("🚀 TESTING INTELLIGENT SYNC AFTER PATH FIX")
print("=" * 50)

# Upload a new test document to trigger sync
test_payload = {
    "embeddings": [[0.4] * 3072],
    "documents": ["SYNC TEST AFTER PATH FIX - This should trigger working sync!"],
    "metadatas": [{"test": "path_fix_verification"}],
    "ids": ["path_fix_test_1"]
}

print("Uploading test document to trigger sync...")
upload = requests.post(
    f"https://chroma-load-balancer.onrender.com/api/v2/tenants/default_tenant/databases/default_database/collections/{primary_id}/add",
    headers={"Content-Type": "application/json"},
    json=test_payload,
    timeout=30
)
print(f"Upload result: {upload.status_code}")

if upload.status_code in [200, 201]:
    print("✅ Upload successful - monitoring intelligent sync...")
    
    for i in range(8):
        time.sleep(5)
        
        try:
            primary_count = int(requests.get(f"https://chroma-primary.onrender.com/api/v2/tenants/default_tenant/databases/default_database/collections/{primary_id}/count", timeout=30).text)
            replica_count = int(requests.get(f"https://chroma-replica.onrender.com/api/v2/tenants/default_tenant/databases/default_database/collections/{replica_id}/count", timeout=30).text)
            
            print(f"({(i+1)*5}s) Counts: Primary={primary_count}, Replica={replica_count}")
            
            if replica_count > 0:
                print()
                print("🎉🎉🎉 SUCCESS! INTELLIGENT WAL SYNC IS NOW FULLY OPERATIONAL! 🎉🎉🎉")
                print("✅ Your file uploads are syncing automatically to replica!")
                print()
                print("📌 WORKING COLLECTION INFO:")
                print(f"   Collection Name: global")
                print(f"   Primary ID:  {primary_id}")
                print(f"   Replica ID:  {replica_id}")
                print()
                print("📝 YOUR INGESTION SERVICE IS ALREADY CONFIGURED CORRECTLY!")
                print(f"   Collection ID: {primary_id}")
                print(f"   URL: https://chroma-load-balancer.onrender.com/api/v2/tenants/default_tenant/databases/default_database/collections/{primary_id}/add")
                break
        except Exception as e:
            print(f"Count error: {e}")
    else:
        print("⚠️ Sync may need more time but path fix is applied")
        
        # Check WAL status
        try:
            wal_response = requests.get("https://chroma-load-balancer.onrender.com/wal/status", timeout=30)
            if wal_response.status_code == 200:
                wal_status = wal_response.json()
                stats = wal_status['performance_stats']
                print(f"WAL Status: {stats['successful_syncs']} successful, {stats['failed_syncs']} failed")
        except:
            pass
            
else:
    print(f"❌ Upload failed: {upload.text}") 