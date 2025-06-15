#!/usr/bin/env python3

import requests
import json
import time

def debug_wal_failures():
    """Debug specific WAL failure errors and test collection mapping"""
    
    base_url = "https://chroma-load-balancer.onrender.com"
    primary_url = "https://chroma-primary.onrender.com"
    replica_url = "https://chroma-replica.onrender.com"
    
    print("🔍 Debugging WAL Sync Failures")
    print("=" * 50)
    
    try:
        # Step 1: Check current collections on both instances
        print("1. Checking current collections...")
        
        primary_response = requests.get(f"{primary_url}/api/v2/tenants/default_tenant/databases/default_database/collections", timeout=30)
        replica_response = requests.get(f"{replica_url}/api/v2/tenants/default_tenant/databases/default_database/collections", timeout=30)
        
        primary_collections = primary_response.json() if primary_response.status_code == 200 else []
        replica_collections = replica_response.json() if replica_response.status_code == 200 else []
        
        print(f"   Primary: {len(primary_collections)} collections")
        print(f"   Replica: {len(replica_collections)} collections")
        
        for collection in primary_collections:
            print(f"      Primary: {collection['name']} ({collection['id'][:8]}...)")
        
        for collection in replica_collections:
            print(f"      Replica: {collection['name']} ({collection['id'][:8]}...)")
        
        # Step 2: Test basic connectivity and WAL status
        print(f"\n2. Testing load balancer status...")
        
        status_response = requests.get(f"{base_url}/status", timeout=30)
        if status_response.status_code == 200:
            status = status_response.json()
            print(f"   ✅ Load balancer healthy: {status['healthy_instances']}/{status['total_instances']}")
            print(f"   Failed syncs: {status['performance_stats']['failed_syncs']}")
            print(f"   Successful syncs: {status['performance_stats']['successful_syncs']}")
        
        # Step 3: Test simple collection creation and mapping
        print(f"\n3. Testing intelligent collection mapping...")
        
        test_collection_name = f"debug_test_{int(time.time())}"
        
        # Create collection on primary directly
        create_payload = {
            "name": test_collection_name,
            "configuration": {
                "hnsw": {
                    "space": "l2",
                    "ef_construction": 100,
                    "ef_search": 100,
                    "max_neighbors": 16,
                    "resize_factor": 1.2,
                    "sync_threshold": 1000
                }
            }
        }
        
        primary_create_response = requests.post(
            f"{primary_url}/api/v2/tenants/default_tenant/databases/default_database/collections",
            headers={"Content-Type": "application/json"},
            json=create_payload,
            timeout=30
        )
        
        if primary_create_response.status_code in [200, 201]:
            primary_collection = primary_create_response.json()
            primary_collection_id = primary_collection['id']
            print(f"   ✅ Primary collection created: {primary_collection_id[:8]}...")
        else:
            print(f"   ❌ Primary collection creation failed: {primary_create_response.status_code}")
            return
        
        # Step 4: Test data ingestion through load balancer (should trigger intelligent mapping)
        print(f"\n4. Testing data ingestion with intelligent mapping...")
        
        test_payload = {
            "embeddings": [[0.1, 0.2, 0.3]],
            "documents": ["Debug test document"],
            "metadatas": [{"debug": "collection_mapping_test"}],
            "ids": ["debug_test_001"]
        }
        
        ingest_response = requests.post(
            f"{base_url}/api/v2/tenants/default_tenant/databases/default_database/collections/{primary_collection_id}/add",
            headers={"Content-Type": "application/json"},
            json=test_payload,
            timeout=30
        )
        
        if ingest_response.status_code in [200, 201]:
            print(f"   ✅ Ingestion successful")
        else:
            print(f"   ❌ Ingestion failed: {ingest_response.status_code}")
            print(f"   Response: {ingest_response.text[:200]}")
        
        # Step 5: Wait and check sync
        print(f"\n5. Waiting for intelligent sync (30 seconds)...")
        time.sleep(30)
        
        # Check if collection was auto-created on replica
        final_replica_response = requests.get(f"{replica_url}/api/v2/tenants/default_tenant/databases/default_database/collections", timeout=30)
        if final_replica_response.status_code == 200:
            final_replica_collections = final_replica_response.json()
            replica_test_collections = [c for c in final_replica_collections if c['name'] == test_collection_name]
            
            if replica_test_collections:
                replica_collection_id = replica_test_collections[0]['id']
                print(f"   ✅ Auto-creation successful!")
                print(f"      Primary ID: {primary_collection_id}")
                print(f"      Replica ID: {replica_collection_id}")
                
                # Test document count
                primary_count_response = requests.get(f"{primary_url}/api/v2/tenants/default_tenant/databases/default_database/collections/{primary_collection_id}/count", timeout=30)
                replica_count_response = requests.get(f"{replica_url}/api/v2/tenants/default_tenant/databases/default_database/collections/{replica_collection_id}/count", timeout=30)
                
                if primary_count_response.status_code == 200 and replica_count_response.status_code == 200:
                    primary_count = int(primary_count_response.text.strip())
                    replica_count = int(replica_count_response.text.strip())
                    print(f"      Primary count: {primary_count}")
                    print(f"      Replica count: {replica_count}")
                    
                    if primary_count == replica_count and replica_count > 0:
                        print(f"   🎉 INTELLIGENT SYNC WORKING!")
                    else:
                        print(f"   ❌ Sync incomplete")
            else:
                print(f"   ❌ Auto-creation failed - no replica collection")
        
        # Step 6: Check WAL status details
        print(f"\n6. Checking WAL system details...")
        
        wal_response = requests.get(f"{base_url}/wal/status", timeout=30)
        if wal_response.status_code == 200:
            wal_status = wal_response.json()
            print(f"   Successful syncs: {wal_status['performance_stats']['successful_syncs']}")
            print(f"   Failed syncs: {wal_status['performance_stats']['failed_syncs']}")
            print(f"   Pending writes: {wal_status['wal_system']['pending_writes']}")
            print(f"   Auto-created collections: {wal_status['performance_stats'].get('auto_created_collections', 0)}")
        
        # Step 7: Test with existing "global" collection
        print(f"\n7. Testing with existing 'global' collection...")
        
        global_collections_primary = [c for c in primary_collections if c['name'] == 'global']
        global_collections_replica = [c for c in replica_collections if c['name'] == 'global']
        
        if global_collections_primary and global_collections_replica:
            primary_global_id = global_collections_primary[0]['id']
            replica_global_id = global_collections_replica[0]['id']
            
            print(f"   Global collection mapping:")
            print(f"      Primary: {primary_global_id}")
            print(f"      Replica: {replica_global_id}")
            
            if primary_global_id != replica_global_id:
                print(f"   ✅ Different IDs - mapping needed")
                
                # Test ingestion with global collection
                global_test_payload = {
                    "embeddings": [[0.1] * 3072],  # Match dimension
                    "documents": ["Global debug test"],
                    "metadatas": [{"debug": "global_test", "document_id": f"debug_{int(time.time())}"}],
                    "ids": [f"global_debug_{int(time.time())}"]
                }
                
                global_ingest_response = requests.post(
                    f"{base_url}/api/v2/tenants/default_tenant/databases/default_database/collections/{primary_global_id}/add",
                    headers={"Content-Type": "application/json"},
                    json=global_test_payload,
                    timeout=30
                )
                
                if global_ingest_response.status_code in [200, 201]:
                    print(f"   ✅ Global collection ingestion successful")
                    
                    # Wait and check sync
                    print(f"   Waiting for global sync (20 seconds)...")
                    time.sleep(20)
                    
                    # Check counts
                    global_primary_count_response = requests.get(f"{primary_url}/api/v2/tenants/default_tenant/databases/default_database/collections/{primary_global_id}/count", timeout=30)
                    global_replica_count_response = requests.get(f"{replica_url}/api/v2/tenants/default_tenant/databases/default_database/collections/{replica_global_id}/count", timeout=30)
                    
                    if global_primary_count_response.status_code == 200 and global_replica_count_response.status_code == 200:
                        global_primary_count = int(global_primary_count_response.text.strip())
                        global_replica_count = int(global_replica_count_response.text.strip())
                        print(f"   Global Primary count: {global_primary_count}")
                        print(f"   Global Replica count: {global_replica_count}")
                        
                        if global_primary_count == global_replica_count:
                            print(f"   🎉 GLOBAL COLLECTION SYNC WORKING!")
                        else:
                            print(f"   ❌ Global collection sync issue")
                else:
                    print(f"   ❌ Global ingestion failed: {global_ingest_response.status_code}")
            else:
                print(f"   ⚠️ Same IDs - no mapping needed")
        else:
            print(f"   ❌ Global collection not found on both instances")
        
        print(f"\n{'='*50}")
        print(f"🔍 Debug completed!")
        print(f"{'='*50}")
        
    except Exception as e:
        print(f"\n❌ Debug failed: {e}")
        import traceback
        print(f"Traceback: {traceback.format_exc()}")

if __name__ == "__main__":
    debug_wal_failures() 