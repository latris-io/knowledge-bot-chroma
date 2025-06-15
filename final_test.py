import requests
import time
import json

def final_test():
    """Final test to verify intelligent sync is working"""
    
    base_url = "https://chroma-load-balancer.onrender.com"
    primary_url = "https://chroma-primary.onrender.com"
    replica_url = "https://chroma-replica.onrender.com"
    
    print("🧪 Final Intelligent Sync Test")
    print("=" * 50)
    
    # Test with global collection
    global_id = "eb07030e-ed7e-4aab-8249-3a95efefccb0"
    replica_global_id = "0c6ab3d3-bbf2-44e4-9cfe-e95654c43ace"
    
    try:
        # Get current counts
        primary_count = int(requests.get(f"{primary_url}/api/v2/tenants/default_tenant/databases/default_database/collections/{global_id}/count", timeout=30).text)
        replica_count = int(requests.get(f"{replica_url}/api/v2/tenants/default_tenant/databases/default_database/collections/{replica_global_id}/count", timeout=30).text)
        
        print(f"Before test - Primary: {primary_count}, Replica: {replica_count}")
        
        # Add test document
        test_payload = {
            "embeddings": [[0.1] * 3072],
            "documents": ["Final test document"],
            "metadatas": [{"test": "final_verification", "document_id": f"final_test_{int(time.time())}"}],
            "ids": [f"final_test_{int(time.time())}"]
        }
        
        ingest_response = requests.post(
            f"{base_url}/api/v2/tenants/default_tenant/databases/default_database/collections/{global_id}/add",
            headers={"Content-Type": "application/json"},
            json=test_payload,
            timeout=30
        )
        
        print(f"Ingestion: {ingest_response.status_code}")
        
        if ingest_response.status_code in [200, 201]:
            print("✅ Ingestion successful")
            
            # Wait for sync
            print("Waiting 25 seconds for intelligent sync...")
            time.sleep(25)
            
            # Check final counts
            final_primary_count = int(requests.get(f"{primary_url}/api/v2/tenants/default_tenant/databases/default_database/collections/{global_id}/count", timeout=30).text)
            final_replica_count = int(requests.get(f"{replica_url}/api/v2/tenants/default_tenant/databases/default_database/collections/{replica_global_id}/count", timeout=30).text)
            
            print(f"After test - Primary: {final_primary_count}, Replica: {final_replica_count}")
            
            # Check for improvement
            if final_replica_count > replica_count:
                print("🎉 SUCCESS! Intelligent sync is working!")
                print(f"   Replica count increased from {replica_count} to {final_replica_count}")
            elif final_primary_count > primary_count:
                print("⚠️ Primary updated but replica sync delayed")
                print(f"   Primary count increased from {primary_count} to {final_primary_count}")
            else:
                print("❌ No changes detected")
            
            # Check system status
            status_response = requests.get(f"{base_url}/status", timeout=30)
            if status_response.status_code == 200:
                status = status_response.json()
                successful_syncs = status["performance_stats"]["successful_syncs"]
                failed_syncs = status["performance_stats"]["failed_syncs"]
                
                print(f"System status:")
                print(f"   Successful syncs: {successful_syncs}")
                print(f"   Failed syncs: {failed_syncs}")
                
                if successful_syncs > 0:
                    print("✅ System has successful syncs!")
                else:
                    print("⚠️ No successful syncs yet")
            
        else:
            print(f"❌ Ingestion failed: {ingest_response.status_code}")
            print(f"Response: {ingest_response.text}")
        
    except Exception as e:
        print(f"❌ Test failed: {e}")
        import traceback
        print(traceback.format_exc())

if __name__ == "__main__":
    final_test() 