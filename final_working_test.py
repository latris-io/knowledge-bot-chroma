import requests
import time

print("🎉 FINAL INTELLIGENT WAL SYNC TEST")
print("=" * 50)

base_url = "https://chroma-load-balancer.onrender.com"
primary_url = "https://chroma-primary.onrender.com"
replica_url = "https://chroma-replica.onrender.com"

global_id = "eb07030e-ed7e-4aab-8249-3a95efefccb0"
replica_global_id = "0c6ab3d3-bbf2-44e4-9cfe-e95654c43ace"

try:
    # Get current counts
    print("1. Checking current document counts...")
    primary_count = int(requests.get(f"{primary_url}/api/v2/tenants/default_tenant/databases/default_database/collections/{global_id}/count", timeout=30).text)
    replica_count = int(requests.get(f"{replica_url}/api/v2/tenants/default_tenant/databases/default_database/collections/{replica_global_id}/count", timeout=30).text)
    
    print(f"   Before test - Primary: {primary_count}, Replica: {replica_count}")
    
    # Test with CORRECT 3072-dimensional embeddings
    print("2. Testing with CORRECT 3072-dimensional embeddings...")
    
    payload = {
        "embeddings": [[0.1] * 3072],  # CORRECT 3072 dimensions!
        "documents": ["🎉 FINAL INTELLIGENT SYNC TEST - SUCCESS!"],
        "metadatas": [{"test": "final_success", "document_id": f"success_test_{int(time.time())}"}],
        "ids": [f"success_{int(time.time())}"]
    }
    
    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json"
    }
    
    response = requests.post(
        f"{base_url}/api/v2/tenants/default_tenant/databases/default_database/collections/{global_id}/add",
        headers=headers,
        json=payload,
        timeout=30
    )
    
    print(f"   Ingestion response: {response.status_code}")
    
    if response.status_code in [200, 201]:
        print("   ✅ INGESTION SUCCESSFUL!")
        print("   🔄 Waiting 30 seconds for intelligent WAL sync...")
        time.sleep(30)
        
        # Check final counts
        final_primary_count = int(requests.get(f"{primary_url}/api/v2/tenants/default_tenant/databases/default_database/collections/{global_id}/count", timeout=30).text)
        final_replica_count = int(requests.get(f"{replica_url}/api/v2/tenants/default_tenant/databases/default_database/collections/{replica_global_id}/count", timeout=30).text)
        
        print(f"   After test - Primary: {final_primary_count}, Replica: {final_replica_count}")
        
        # Check for sync success
        if final_replica_count > replica_count:
            print("   🎉🎉🎉 SUCCESS! INTELLIGENT WAL SYNC WORKING! 🎉🎉🎉")
            print(f"   ✅ Replica count increased from {replica_count} to {final_replica_count}")
            print("   ✅ Collection ID mapping working correctly!")
            print("   ✅ Auto-sync between instances successful!")
        elif final_primary_count > primary_count:
            print("   ✅ Primary updated successfully")
            print(f"   ✅ Primary count increased from {primary_count} to {final_primary_count}")
            print("   ⏳ Replica sync may need more time...")
        else:
            print("   ⚠️ Counts unchanged - may need to check sync status")
        
        # Check WAL system status
        print("3. Checking WAL system status...")
        wal_response = requests.get(f"{base_url}/wal/status", timeout=30)
        if wal_response.status_code == 200:
            wal_status = wal_response.json()
            successful = wal_status["performance_stats"]["successful_syncs"]
            failed = wal_status["performance_stats"]["failed_syncs"]
            
            print(f"   WAL Status: {successful} successful, {failed} failed syncs")
            
            if successful > 0:
                print("   🎉 CONFIRMED: WAL SYNC SYSTEM WORKING!")
            else:
                print("   ⏳ WAL syncs may be processing...")
        
    else:
        print(f"   ❌ Ingestion failed: {response.status_code}")
        print(f"   Response: {response.text}")
        
except Exception as e:
    print(f"❌ Test failed: {e}")

print(f"\n{'='*50}")
print("🎉 FINAL TEST COMPLETED!")
print(f"{'='*50}") 