#!/usr/bin/env python3

import requests
import json
import time
import random
import uuid
import logging

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Production safety
TEST_PREFIX = "AUTOTEST_"
test_collections_created = []

def create_safe_test_collection_name() -> str:
    """Create a production-safe test collection name"""
    timestamp = int(time.time())
    random_suffix = str(uuid.uuid4())[:8]
    collection_name = f"{TEST_PREFIX}intelligent_sync_{timestamp}_{random_suffix}"
    test_collections_created.append(collection_name)
    return collection_name

def cleanup_test_collections(base_url: str):
    """Clean up all test collections from the system"""
    logger.info("🧹 Cleaning up intelligent WAL sync test collections...")
    
    cleanup_results = {"attempted": 0, "successful": 0, "failed": 0}
    
    for collection_name in test_collections_created:
        cleanup_results["attempted"] += 1
        
        # Safety check
        if not collection_name.startswith(TEST_PREFIX):
            logger.error(f"❌ SAFETY: Refused to delete {collection_name}")
            cleanup_results["failed"] += 1
            continue
        
        try:
            # Delete collection
            response = requests.delete(
                f"{base_url}/api/v2/collections/{collection_name}",
                timeout=30
            )
            if response.status_code in [200, 404]:  # 404 means already deleted
                logger.info(f"✅ Deleted: {collection_name}")
                cleanup_results["successful"] += 1
            else:
                logger.warning(f"⚠️ Failed to delete {collection_name}: {response.status_code}")
                cleanup_results["failed"] += 1
        except Exception as e:
            logger.warning(f"⚠️ Error deleting {collection_name}: {e}")
            cleanup_results["failed"] += 1
    
    logger.info(f"🧹 Cleanup complete: {cleanup_results['successful']}/{cleanup_results['attempted']} collections")
    test_collections_created.clear()
    return cleanup_results

def test_intelligent_wal_sync():
    """Test the intelligent WAL sync system with collection mapping and auto-creation"""
    
    base_url = "https://chroma-load-balancer.onrender.com"
    primary_url = "https://chroma-primary.onrender.com"
    replica_url = "https://chroma-replica.onrender.com"
    
    print("🧪 Testing Intelligent WAL Sync System")
    print("=" * 60)
    
    try:
        # Step 1: Check system status
        print("1. Checking system status...")
        status_response = requests.get(f"{base_url}/status", timeout=30)
        if status_response.status_code == 200:
            status = status_response.json()
            print(f"   ✅ Load balancer healthy: {status['healthy_instances']}/{status['total_instances']} instances")
            print(f"   WAL pending writes: {status['unified_wal']['pending_writes']}")
        else:
            print(f"   ❌ Status check failed: {status_response.status_code}")
            return
        
        # Step 2: Create test collection through load balancer
        collection_name = create_safe_test_collection_name()
        print(f"\n2. Creating test collection '{collection_name}' through load balancer...")
        
        create_payload = {
            "name": collection_name,
            "metadata": {"test_type": "intelligent_wal_sync", "safe_to_delete": True},
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
        
        create_response = requests.post(
            f"{base_url}/api/v2/tenants/default_tenant/databases/default_database/collections",
            headers={"Content-Type": "application/json"},
            json=create_payload,
            timeout=30
        )
        
        if create_response.status_code in [200, 201]:
            collection_data = create_response.json()
            collection_id = collection_data['id']
            print(f"   ✅ Collection created: {collection_id[:8]}...")
        else:
            print(f"   ❌ Collection creation failed: {create_response.status_code}")
            print(f"   Response: {create_response.text[:200]}")
            return
        
        # Step 3: Wait for collection mapping to be created
        print("\n3. Waiting for collection mapping creation (10 seconds)...")
        time.sleep(10)
        
        # Step 4: Check collections on both instances
        print("\n4. Checking collections on both instances...")
        
        # Check primary
        primary_collections_response = requests.get(
            f"{primary_url}/api/v2/tenants/default_tenant/databases/default_database/collections",
            timeout=30
        )
        
        primary_collection_ids = []
        if primary_collections_response.status_code == 200:
            primary_collections = primary_collections_response.json()
            primary_collection_ids = [c['id'] for c in primary_collections if c['name'] == collection_name]
            print(f"   Primary: {len(primary_collection_ids)} collections named '{collection_name}'")
        
        # Check replica  
        replica_collections_response = requests.get(
            f"{replica_url}/api/v2/tenants/default_tenant/databases/default_database/collections",
            timeout=30
        )
        
        replica_collection_ids = []
        if replica_collections_response.status_code == 200:
            replica_collections = replica_collections_response.json()
            replica_collection_ids = [c['id'] for c in replica_collections if c['name'] == collection_name]
            print(f"   Replica: {len(replica_collection_ids)} collections named '{collection_name}'")
        
        if len(primary_collection_ids) == 1 and len(replica_collection_ids) == 1:
            primary_id = primary_collection_ids[0]
            replica_id = replica_collection_ids[0]
            print(f"   ✅ Collection mapping working:")
            print(f"      Primary ID: {primary_id}")
            print(f"      Replica ID: {replica_id}")
            
            # IDs should be different (proving mapping works)
            if primary_id != replica_id:
                print(f"   ✅ Collection ID mapping confirmed (different IDs)")
            else:
                print(f"   ⚠️ Same collection ID on both instances")
        else:
            print(f"   ❌ Collection mapping failed - missing collections")
            return
        
        # Step 5: Test data ingestion and sync
        print(f"\n5. Testing data ingestion and intelligent sync...")
        
        test_document_id = f"test_doc_{int(time.time())}"
        test_payload = {
            "embeddings": [[random.random() for _ in range(100)] for _ in range(3)],  # 3 test chunks
            "documents": [f"Test document chunk {i} for intelligent sync" for i in range(3)],
            "metadatas": [{"document_id": test_document_id, "chunk": i, "test": "intelligent_sync"} for i in range(3)],
            "ids": [f"{test_document_id}_chunk_{i}" for i in range(3)]
        }
        
        # Ingest through load balancer (will use primary collection ID)
        ingest_response = requests.post(
            f"{base_url}/api/v2/tenants/default_tenant/databases/default_database/collections/{collection_id}/add",
            headers={"Content-Type": "application/json"},
            json=test_payload,
            timeout=30
        )
        
        if ingest_response.status_code in [200, 201]:
            print(f"   ✅ Ingestion successful: 3 chunks added")
        else:
            print(f"   ❌ Ingestion failed: {ingest_response.status_code}")
            print(f"   Response: {ingest_response.text[:200]}")
            return
        
        # Step 6: Wait for WAL sync
        print("\n6. Waiting for intelligent WAL sync (25 seconds)...")
        time.sleep(25)
        
        # Step 7: Verify sync to replica using mapped collection ID
        print("\n7. Verifying sync to replica...")
        
        # Count documents on primary (using original collection ID)
        primary_count_response = requests.get(
            f"{primary_url}/api/v2/tenants/default_tenant/databases/default_database/collections/{primary_id}/count",
            timeout=30
        )
        
        primary_count = 0
        if primary_count_response.status_code == 200:
            primary_count = int(primary_count_response.text.strip())
            print(f"   Primary count: {primary_count}")
        
        # Count documents on replica (using mapped collection ID)
        replica_count_response = requests.get(
            f"{replica_url}/api/v2/tenants/default_tenant/databases/default_database/collections/{replica_id}/count",
            timeout=30
        )
        
        replica_count = 0
        if replica_count_response.status_code == 200:
            replica_count = int(replica_count_response.text.strip())
            print(f"   Replica count: {replica_count}")
        
        if primary_count == replica_count and replica_count >= 3:
            print(f"   🎉 INTELLIGENT SYNC SUCCESSFUL! Both instances have {replica_count} documents")
        else:
            print(f"   ❌ Sync incomplete: Primary({primary_count}) vs Replica({replica_count})")
        
        # Step 8: Test deletion through load balancer
        print(f"\n8. Testing intelligent deletion sync...")
        
        # Delete by document_id through load balancer
        delete_payload = {
            "where": {"document_id": {"$eq": test_document_id}}
        }
        
        delete_response = requests.post(
            f"{base_url}/api/v2/tenants/default_tenant/databases/default_database/collections/{collection_id}/delete",
            headers={"Content-Type": "application/json"},
            json=delete_payload,
            timeout=30
        )
        
        if delete_response.status_code == 200:
            print(f"   ✅ Deletion queued through WAL system")
        else:
            print(f"   ❌ Deletion failed: {delete_response.status_code}")
        
        # Step 9: Wait for deletion sync
        print("\n9. Waiting for deletion sync (20 seconds)...")
        time.sleep(20)
        
        # Step 10: Verify deletion sync
        print("\n10. Verifying deletion sync...")
        
        # Check final counts
        final_primary_response = requests.get(
            f"{primary_url}/api/v2/tenants/default_tenant/databases/default_database/collections/{primary_id}/count",
            timeout=30
        )
        
        final_replica_response = requests.get(
            f"{replica_url}/api/v2/tenants/default_tenant/databases/default_database/collections/{replica_id}/count",
            timeout=30
        )
        
        if (final_primary_response.status_code == 200 and final_replica_response.status_code == 200):
            final_primary_count = int(final_primary_response.text.strip())
            final_replica_count = int(final_replica_response.text.strip())
            
            print(f"   Final Primary count: {final_primary_count}")
            print(f"   Final Replica count: {final_replica_count}")
            
            if final_primary_count == final_replica_count:
                if final_primary_count < primary_count:
                    print(f"   🎉 DELETION SYNC SUCCESSFUL! {primary_count - final_primary_count} documents deleted from both instances")
                else:
                    print(f"   ⚠️ No documents were deleted (expected)")
            else:
                print(f"   ❌ Deletion sync incomplete")
        
        # Step 11: Check WAL system status
        print(f"\n11. Final WAL system status...")
        
        final_status_response = requests.get(f"{base_url}/wal/status", timeout=30)
        if final_status_response.status_code == 200:
            wal_status = final_status_response.json()
            successful_syncs = wal_status['performance_stats']['successful_syncs']
            failed_syncs = wal_status['performance_stats']['failed_syncs']
            auto_created = wal_status['performance_stats'].get('auto_created_collections', 0)
            
            print(f"   Successful syncs: {successful_syncs}")
            print(f"   Failed syncs: {failed_syncs}")
            print(f"   Auto-created collections: {auto_created}")
            
            if successful_syncs > 0 and failed_syncs == 0:
                print(f"   🎉 WAL SYSTEM PERFECT! All syncs successful")
            elif successful_syncs > failed_syncs:
                print(f"   ✅ WAL system mostly working")
            else:
                print(f"   ⚠️ WAL system has issues")
        
        print(f"\n{'='*60}")
        print(f"🎯 Intelligent WAL Sync Test Completed!")
        print(f"   Collection: {collection_name}")
        print(f"   Primary ID: {primary_id[:8]}..." if 'primary_id' in locals() else "")
        print(f"   Replica ID: {replica_id[:8]}..." if 'replica_id' in locals() else "")
        print(f"{'='*60}")
        
    except Exception as e:
        print(f"\n❌ Test failed with error: {e}")
        import traceback
        print(f"Full traceback: {traceback.format_exc()}")
    
    finally:
        # Always cleanup test collections
        cleanup_test_collections(base_url)

if __name__ == "__main__":
    test_intelligent_wal_sync() 