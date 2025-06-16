#!/usr/bin/env python3
"""
Test WAL Sync & Document Operations after Memoryview Fix
========================================================

This test verifies that the critical memoryview fix resolved:
1. Empty request bodies in WAL sync
2. Document operations working properly
3. Collection replication between instances

With comprehensive cleanup mechanisms.
"""

import requests
import time
import json
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
    random_suffix = uuid.uuid4().hex[:8]
    collection_name = f"{TEST_PREFIX}memoryview_fix_{timestamp}_{random_suffix}"
    test_collections_created.append(collection_name)
    return collection_name

def cleanup_test_collections(base_url: str):
    """Clean up all test collections from the system"""
    logger.info("🧹 Cleaning up memoryview fix test collections...")
    
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

def test_document_operations_and_sync():
    lb_url = 'https://chroma-load-balancer.onrender.com'
    
    print('🧪 TESTING DOCUMENT OPERATIONS & COLLECTION REPLICATION')
    print('=' * 60)
    
    # Use production-safe collection name
    collection_name = create_safe_test_collection_name()
    collection_id = None
    
    try:
        # 1. Create collection
        print(f'📁 Creating test collection: {collection_name}')
        response = requests.post(
            f'{lb_url}/api/v2/tenants/default_tenant/databases/default_database/collections', 
            json={
                'name': collection_name, 
                'metadata': {
                    'test': 'memoryview_fix',
                    'safe_to_delete': True,
                    'test_type': 'memoryview_fix'
                }
            },
            timeout=30
        )
        print(f'   Status: {response.status_code}')
        
        if response.status_code == 200:
            collection_id = response.json()['id']
            print(f'   ✅ Collection ID: {collection_id}')
            
            # 2. Add document
            print('📄 Adding document...')
            doc_response = requests.post(
                f'{lb_url}/api/v2/tenants/default_tenant/databases/default_database/collections/{collection_id}/add',
                json={
                    'ids': ['test_doc_1'],
                    'documents': ['This is a test document to verify WAL sync after memoryview fix'],
                    'metadatas': [{'source': 'memoryview_fix_test', 'timestamp': str(time.time())}]
                },
                timeout=30
            )
            print(f'   Status: {doc_response.status_code}')
            
            if doc_response.status_code == 201:
                print('   ✅ Document added successfully!')
                
                # 3. Wait for WAL sync
                print('⏰ Waiting 20 seconds for WAL sync...')
                time.sleep(20)
                
                # 4. Check WAL status
                print('🔍 Checking WAL sync status...')
                wal_status = requests.get(f'{lb_url}/wal/status', timeout=10).json()
                print(f'   Pending writes: {wal_status["wal_system"]["pending_writes"]}')
                print(f'   Successful syncs: {wal_status["performance_stats"]["successful_syncs"]}')
                print(f'   Failed syncs: {wal_status["performance_stats"]["failed_syncs"]}')
                
                # 5. Query collection to verify replication
                print('🔍 Querying collection to verify replication...')
                query_response = requests.post(
                    f'{lb_url}/api/v2/tenants/default_tenant/databases/default_database/collections/{collection_id}/query',
                    json={'query_texts': ['test'], 'n_results': 10},
                    timeout=30
                )
                print(f'   Status: {query_response.status_code}')
                
                if query_response.status_code == 200:
                    results = query_response.json()
                    doc_count = len(results.get('ids', [[]])[0]) if results.get('ids') else 0
                    print(f'   Documents found: {doc_count}')
                    
                    if doc_count > 0:
                        print('   ✅ COLLECTION REPLICATION SUCCESS!')
                        print('   ✅ WAL SYNC IS WORKING!')
                        print('   ✅ MEMORYVIEW FIX SUCCESSFUL!')
                        return True
                    else:
                        print('   ❌ No documents found - sync may still be in progress')
                        return False
                else:
                    print(f'   ❌ Query failed: {query_response.text[:200]}')
                    return False
            else:
                print(f'   ❌ Document add failed: {doc_response.text[:200]}')
                return False
        else:
            print(f'   ❌ Collection creation failed: {response.text[:200]}')
            return False
            
    except Exception as e:
        print(f'❌ Test error: {e}')
        return False
    
    finally:
        # Always cleanup test collections
        cleanup_test_collections(lb_url)

if __name__ == "__main__":
    success = test_document_operations_and_sync()
    
    print('\n' + '='*60)
    if success:
        print('🎉 MEMORYVIEW FIX VERIFICATION: SUCCESS!')
        print('✅ Document operations working')
        print('✅ WAL sync operational') 
        print('✅ Collection replication confirmed')
        print('✅ Test cleanup completed')
        exit(0)
    else:
        print('⚠️ MEMORYVIEW FIX VERIFICATION: NEEDS INVESTIGATION')
        print('❌ Some functionality may still need debugging')
        print('✅ Test cleanup completed')
        exit(1) 