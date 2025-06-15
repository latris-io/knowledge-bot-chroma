import requests
import json
import time

def test_new_collection():
    print("🚀 TESTING NEW COLLECTION & INTELLIGENT SYNC")
    print("=" * 50)
    
    try:
        # Step 1: Create new collection
        collection_name = f"test_collection_{int(time.time())}"
        print(f"1. Creating new collection: {collection_name}")
        
        create_payload = {
            "name": collection_name,
            "configuration_json": {
                "hnsw": {
                    "space": "l2", 
                    "ef_construction": 100
                }
            }
        }
        
        create_response = requests.post(
            "https://chroma-load-balancer.onrender.com/api/v2/tenants/default_tenant/databases/default_database/collections",
            headers={"Content-Type": "application/json"},
            json=create_payload,
            timeout=30
        )
        
        print(f"   Creation result: {create_response.status_code}")
        
        if create_response.status_code in [200, 201]:
            collection_data = create_response.json()
            collection_id = collection_data.get('id')
            print(f"   ✅ Created: {collection_name} ({collection_id[:8]}...)")
            
            # Step 2: Add document
            print("2. Adding document to new collection...")
            
            doc_payload = {
                "embeddings": [[0.1] * 3072],
                "documents": ["First document in new collection - testing intelligent sync"],
                "metadatas": [{"test": "new_collection", "timestamp": int(time.time())}],
                "ids": ["doc_1"]
            }
            
            doc_response = requests.post(
                f"https://chroma-load-balancer.onrender.com/api/v2/tenants/default_tenant/databases/default_database/collections/{collection_id}/add",
                headers={"Content-Type": "application/json"},
                json=doc_payload,
                timeout=30
            )
            
            print(f"   Document result: {doc_response.status_code}")
            
            if doc_response.status_code in [200, 201]:
                print("   ✅ Document added - should trigger intelligent sync!")
                
                # Step 3: Monitor sync
                print("3. Monitoring intelligent sync for 30 seconds...")
                
                for i in range(6):
                    time.sleep(5)
                    print(f"   Checking sync ({(i+1)*5}s)...")
                    
                    try:
                        wal_response = requests.get("https://chroma-load-balancer.onrender.com/wal/status", timeout=30)
                        if wal_response.status_code == 200:
                            wal_status = wal_response.json()
                            successful = wal_status['performance_stats']['successful_syncs']
                            failed = wal_status['performance_stats']['failed_syncs']
                            print(f"      WAL: {successful} successful, {failed} failed")
                            
                            if successful > 0:
                                print("      🎉 SUCCESS! Intelligent sync working!")
                                break
                        else:
                            print(f"      ⚠️ WAL status error: {wal_response.status_code}")
                    except Exception as e:
                        print(f"      ⚠️ Status check error: {e}")
                
                # Step 4: Final verification
                print("4. Final verification...")
                
                replica_response = requests.get("https://chroma-replica.onrender.com/api/v2/tenants/default_tenant/databases/default_database/collections", timeout=30)
                if replica_response.status_code == 200:
                    replica_collections = replica_response.json()
                    print(f"   Replica collections: {len(replica_collections)}")
                    
                    for c in replica_collections:
                        if c['name'] == collection_name:
                            replica_count = int(requests.get(f"https://chroma-replica.onrender.com/api/v2/tenants/default_tenant/databases/default_database/collections/{c['id']}/count", timeout=30).text)
                            print(f"   - {c['name']}: {replica_count} documents")
                            
                            if replica_count > 0:
                                print("   🎉🎉🎉 SUCCESS! INTELLIGENT WAL SYNC FULLY OPERATIONAL! 🎉🎉🎉")
                                return
                    
                    print("   ⚠️ Collection not yet synced to replica")
                else:
                    print(f"   ❌ Failed to check replica: {replica_response.status_code}")
            else:
                print(f"   ❌ Document failed: {doc_response.text}")
        else:
            print(f"   ❌ Collection creation failed: {create_response.text}")
            
    except Exception as e:
        print(f"❌ Test failed: {e}")

if __name__ == "__main__":
    test_new_collection() 