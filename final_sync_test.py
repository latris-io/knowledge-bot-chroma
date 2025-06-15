import requests
import json
import time

def final_sync_test():
    primary_id = "91fc274b-1a55-48a6-9b5f-fcc842e7eb0b"
    replica_id = "4e5e29a0-38b9-4ce4-b589-3ce01e0d6528"
    
    print("🚀 TESTING INTELLIGENT SYNC WITH FRESH DOCUMENT")
    print("=" * 50)
    
    # Get initial counts
    primary_count = int(requests.get(f"https://chroma-primary.onrender.com/api/v2/tenants/default_tenant/databases/default_database/collections/{primary_id}/count", timeout=30).text)
    replica_count = int(requests.get(f"https://chroma-replica.onrender.com/api/v2/tenants/default_tenant/databases/default_database/collections/{replica_id}/count", timeout=30).text)
    print(f"Before: Primary={primary_count}, Replica={replica_count}")
    
    # Add test document
    payload = {
        "embeddings": [[0.1] * 3072],
        "documents": ["FINAL INTELLIGENT SYNC TEST - This should sync to replica"],
        "metadatas": [{"test": "final_sync_test", "timestamp": int(time.time())}],
        "ids": [f"final_sync_{int(time.time())}"]
    }
    
    response = requests.post(
        f"https://chroma-load-balancer.onrender.com/api/v2/tenants/default_tenant/databases/default_database/collections/{primary_id}/add",
        headers={"Content-Type": "application/json"},
        json=payload,
        timeout=30
    )
    
    print(f"Upload result: {response.status_code}")
    
    if response.status_code in [200, 201]:
        print("✅ Document uploaded - monitoring sync...")
        
        # Monitor for 30 seconds
        for i in range(6):
            time.sleep(5)
            print(f"Checking ({(i+1)*5}s)...")
            
            new_primary = int(requests.get(f"https://chroma-primary.onrender.com/api/v2/tenants/default_tenant/databases/default_database/collections/{primary_id}/count", timeout=30).text)
            new_replica = int(requests.get(f"https://chroma-replica.onrender.com/api/v2/tenants/default_tenant/databases/default_database/collections/{replica_id}/count", timeout=30).text)
            
            print(f"   Counts: Primary={new_primary}, Replica={new_replica}")
            
            if new_replica > replica_count:
                print("🎉🎉🎉 SUCCESS! INTELLIGENT WAL SYNC FULLY OPERATIONAL! 🎉🎉🎉")
                print()
                print("📌 WORKING COLLECTION INFO:")
                print(f"   Collection Name: knowledge_base")
                print(f"   Primary ID:  {primary_id}")
                print(f"   Replica ID:  {replica_id}")
                print()
                print("✅ Your file uploads are now syncing automatically to replica!")
                print("✅ Update your ingestion service to use:")
                print(f"   Collection ID: {primary_id}")
                print(f"   URL: https://chroma-load-balancer.onrender.com/api/v2/tenants/default_tenant/databases/default_database/collections/{primary_id}/add")
                return
        
        print("⚠️ Sync may need more time - checking WAL status...")
        wal_response = requests.get("https://chroma-load-balancer.onrender.com/wal/status", timeout=30)
        if wal_response.status_code == 200:
            wal_status = wal_response.json()
            stats = wal_status['performance_stats']
            print(f"   WAL Status: {stats['successful_syncs']} successful, {stats['failed_syncs']} failed")
    else:
        print(f"❌ Upload failed: {response.text}")

if __name__ == "__main__":
    final_sync_test() 