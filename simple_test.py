import requests
import time

base_url = "https://chroma-load-balancer.onrender.com"
global_id = "eb07030e-ed7e-4aab-8249-3a95efefccb0"

print("🧪 Simple Intelligent Sync Test")
print("=" * 50)

# Simple test ingestion
payload = {
    "embeddings": [[0.1, 0.2, 0.3]],
    "documents": ["Final mapping test"],
    "metadatas": [{"test": "final_mapping_verification"}],
    "ids": [f"final_test_{int(time.time())}"]
}

try:
    print("Testing ingestion...")
    response = requests.post(
        f"{base_url}/api/v2/tenants/default_tenant/databases/default_database/collections/{global_id}/add",
        headers={"Content-Type": "application/json"},
        json=payload,
        timeout=30
    )
    
    print(f"Ingestion response: {response.status_code}")
    
    if response.status_code in [200, 201]:
        print("✅ Ingestion successful!")
        print("Waiting 20 seconds for intelligent sync...")
        time.sleep(20)
        
        # Check WAL status to see if syncs are working
        try:
            wal_response = requests.get(f"{base_url}/wal/status", timeout=30)
            if wal_response.status_code == 200:
                wal_status = wal_response.json()
                successful = wal_status["performance_stats"]["successful_syncs"]
                failed = wal_status["performance_stats"]["failed_syncs"]
                
                print(f"Sync status: {successful} successful, {failed} failed")
                
                if successful > 0:
                    print("🎉 SUCCESS! Intelligent sync is working!")
                else:
                    print("⚠️ No successful syncs yet")
            else:
                print(f"❌ WAL status check failed: {wal_response.status_code}")
        
        except Exception as e:
            print(f"❌ WAL status error: {e}")
            
    else:
        print(f"❌ Ingestion failed: {response.status_code}")
        print(f"Response: {response.text[:200]}")
        
except Exception as e:
    print(f"❌ Test failed: {e}")

print("✅ Test completed!") 