#!/usr/bin/env python3

import requests
import json
import time
import uuid

def test_controlled_delete():
    """Test DELETE operations in a controlled manner"""
    
    load_balancer_url = 'https://chroma-load-balancer.onrender.com'
    primary_url = 'https://chroma-primary.onrender.com'
    replica_url = 'https://chroma-replica.onrender.com'
    
    print('🧪 CONTROLLED DELETE OPERATION TEST')
    print('=' * 60)
    
    # Generate unique test collection name
    test_collection_name = f"DELETE_TEST_{int(time.time())}_{uuid.uuid4().hex[:8]}"
    print(f'Test collection: {test_collection_name}')
    
    try:
        # Phase 1: Create a test collection through load balancer
        print('\n1️⃣ CREATING TEST COLLECTION...')
        
        create_payload = {
            "name": test_collection_name,
            "configuration": {
                "hnsw": {
                    "space": "l2",
                    "ef_construction": 100,
                    "ef_search": 100
                }
            }
        }
        
        create_response = requests.post(
            f'{load_balancer_url}/api/v2/tenants/default_tenant/databases/default_database/collections',
            json=create_payload,
            timeout=30
        )
        
        print(f'   Create response: {create_response.status_code}')
        
        if create_response.status_code in [200, 201]:
            collection_data = create_response.json()
            collection_id = collection_data.get('id')
            print(f'   ✅ Collection created: {collection_id[:8]}...')
        else:
            print(f'   ❌ Creation failed: {create_response.text[:200]}')
            return False
        
        # Phase 2: Add some test documents
        print('\n2️⃣ ADDING TEST DOCUMENTS...')
        
        add_payload = {
            "documents": ["This is a test document for DELETE testing"],
            "metadatas": [{"test": "delete_test", "timestamp": str(time.time())}],
            "ids": [f"doc_{uuid.uuid4().hex[:8]}"]
        }
        
        add_response = requests.post(
            f'{load_balancer_url}/api/v2/tenants/default_tenant/databases/default_database/collections/{test_collection_name}/add',
            json=add_payload,
            timeout=30
        )
        
        print(f'   Add documents response: {add_response.status_code}')
        
        if add_response.status_code in [200, 201]:
            print(f'   ✅ Documents added successfully')
        else:
            print(f'   ⚠️ Document add failed: {add_response.text[:200]}')
            # Continue anyway for DELETE testing
        
        # Phase 3: Wait for sync and verify collection exists on both instances
        print('\n3️⃣ VERIFYING COLLECTION SYNC...')
        time.sleep(5)  # Wait for sync
        
        # Check primary instance
        primary_check = requests.get(f'{primary_url}/api/v2/tenants/default_tenant/databases/default_database/collections')
        if primary_check.status_code == 200:
            primary_collections = [c.get('name') for c in primary_check.json()]
            primary_has_collection = test_collection_name in primary_collections
            print(f'   Primary has collection: {primary_has_collection}')
        else:
            print(f'   ⚠️ Primary check failed: {primary_check.status_code}')
            primary_has_collection = False
        
        # Check replica instance
        replica_check = requests.get(f'{replica_url}/api/v2/tenants/default_tenant/databases/default_database/collections')
        if replica_check.status_code == 200:
            replica_collections = [c.get('name') for c in replica_check.json()]
            replica_has_collection = test_collection_name in replica_collections
            print(f'   Replica has collection: {replica_has_collection}')
        else:
            print(f'   ⚠️ Replica check failed: {replica_check.status_code}')
            replica_has_collection = False
        
        # Phase 4: Execute DELETE operation through load balancer
        print('\n4️⃣ EXECUTING DELETE OPERATION...')
        
        delete_response = requests.delete(
            f'{load_balancer_url}/api/v2/tenants/default_tenant/databases/default_database/collections/{test_collection_name}',
            timeout=30
        )
        
        print(f'   DELETE response: {delete_response.status_code}')
        print(f'   DELETE response body: {delete_response.text[:200]}')
        
        if delete_response.status_code in [200, 204]:
            print(f'   ✅ DELETE request accepted by load balancer')
            delete_accepted = True
        else:
            print(f'   ❌ DELETE request failed')
            delete_accepted = False
        
        # Phase 5: Wait for WAL sync processing
        print('\n5️⃣ WAITING FOR WAL SYNC...')
        print('   Waiting 20 seconds for WAL processing...')
        time.sleep(20)
        
        # Phase 6: Verify deletion on both instances
        print('\n6️⃣ VERIFYING DELETION RESULTS...')
        
        # Check primary instance after deletion
        primary_check_after = requests.get(f'{primary_url}/api/v2/tenants/default_tenant/databases/default_database/collections')
        if primary_check_after.status_code == 200:
            primary_collections_after = [c.get('name') for c in primary_check_after.json()]
            primary_deleted = test_collection_name not in primary_collections_after
            print(f'   Primary collection deleted: {primary_deleted}')
        else:
            print(f'   ⚠️ Primary check failed: {primary_check_after.status_code}')
            primary_deleted = None
        
        # Check replica instance after deletion
        replica_check_after = requests.get(f'{replica_url}/api/v2/tenants/default_tenant/databases/default_database/collections')
        if replica_check_after.status_code == 200:
            replica_collections_after = [c.get('name') for c in replica_check_after.json()]
            replica_deleted = test_collection_name not in replica_collections_after
            print(f'   Replica collection deleted: {replica_deleted}')
        else:
            print(f'   ⚠️ Replica check failed: {replica_check_after.status_code}')
            replica_deleted = None
        
        # Check load balancer view
        lb_check_after = requests.get(f'{load_balancer_url}/api/v2/tenants/default_tenant/databases/default_database/collections')
        if lb_check_after.status_code == 200:
            lb_collections_after = [c.get('name') for c in lb_check_after.json()]
            lb_deleted = test_collection_name not in lb_collections_after
            print(f'   Load balancer collection deleted: {lb_deleted}')
        else:
            print(f'   ⚠️ Load balancer check failed: {lb_check_after.status_code}')
            lb_deleted = None
        
        # Phase 7: Check WAL status
        print('\n7️⃣ CHECKING WAL STATUS...')
        
        wal_status_response = requests.get(f'{load_balancer_url}/wal/status')
        if wal_status_response.status_code == 200:
            wal_data = wal_status_response.json()
            perf_stats = wal_data.get("performance_stats", {})
            successful_syncs = perf_stats.get("successful_syncs", 0)
            failed_syncs = perf_stats.get("failed_syncs", 0)
            pending_writes = wal_data.get("wal_system", {}).get("pending_writes", 0)
            
            print(f'   WAL successful syncs: {successful_syncs}')
            print(f'   WAL failed syncs: {failed_syncs}')
            print(f'   WAL pending writes: {pending_writes}')
        else:
            print(f'   ⚠️ WAL status check failed: {wal_status_response.status_code}')
        
        # Phase 8: Test results analysis
        print('\n8️⃣ TEST RESULTS ANALYSIS...')
        
        if delete_accepted:
            if primary_deleted and replica_deleted and lb_deleted:
                print('   ✅ PERFECT: DELETE worked correctly on all instances')
                test_result = "SUCCESS"
            elif primary_deleted and replica_deleted:
                print('   ✅ GOOD: DELETE worked on both instances (LB view may be cached)')
                test_result = "SUCCESS"
            elif primary_deleted or replica_deleted:
                print('   ⚠️ PARTIAL: DELETE worked on one instance but not both')
                print(f'      Primary deleted: {primary_deleted}')
                print(f'      Replica deleted: {replica_deleted}')
                test_result = "PARTIAL_SUCCESS"
            else:
                print('   ❌ FAILED: DELETE did not work on either instance')
                test_result = "FAILED"
        else:
            print('   ❌ FAILED: DELETE request was not accepted by load balancer')
            test_result = "FAILED"
        
        print(f'\n📊 FINAL TEST RESULT: {test_result}')
        
        return test_result == "SUCCESS"
        
    except Exception as e:
        print(f'\n❌ Test failed with exception: {e}')
        return False

if __name__ == '__main__':
    success = test_controlled_delete()
    
    if success:
        print('\n🎉 DELETE FUNCTIONALITY WORKING!')
        print('The WAL sync system is properly handling DELETE operations.')
    else:
        print('\n⚠️ DELETE FUNCTIONALITY NEEDS FIXING')
        print('The issue with your CMS deletions is confirmed - sync is not working properly.') 