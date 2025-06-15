#!/usr/bin/env python3
"""
Single Transaction Sync Verification
Tests a complete add -> sync -> delete -> sync cycle to verify
the enhanced sync service handles both addition and deletion correctly.
"""

import os
import time
import json
import random
import string
import requests
import psycopg2
from datetime import datetime

# Configuration
PRIMARY_URL = "https://chroma-primary.onrender.com"
REPLICA_URL = "https://chroma-replica.onrender.com"
DATABASE_URL = "postgresql://chroma_user:xqIF9T5U6LhySuSw86JqWYf7qtyGDXy8@dpg-d16mkandiees73db52u0-a.oregon-postgres.render.com/chroma_ha"

# Test configuration
TEST_PREFIX = "AUTOTEST_"
SYNC_WAIT_TIMEOUT = 120  # seconds
POLL_INTERVAL = 5  # seconds

def make_request(method: str, url: str, **kwargs) -> requests.Response:
    """Make HTTP request with proper headers"""
    headers = kwargs.get('headers', {})
    headers.update({
        'Accept-Encoding': '',
        'Accept': 'application/json',
        'Content-Type': 'application/json'
    })
    kwargs['headers'] = headers
    
    response = requests.request(method, url, **kwargs)
    response.raise_for_status()
    return response

def create_test_collection_name() -> str:
    """Create a unique test collection name"""
    timestamp = int(time.time())
    random_suffix = ''.join(random.choices(string.ascii_lowercase + string.digits, k=6))
    return f"{TEST_PREFIX}single_sync_{timestamp}_{random_suffix}"

def get_collection_by_name(endpoint_url: str, collection_name: str) -> dict:
    """Get a specific collection by name from an endpoint"""
    try:
        collections_url = f"{endpoint_url}/api/v2/tenants/default_tenant/databases/default_database/collections"
        response = make_request('GET', collections_url)
        collections = response.json()
        
        for collection in collections:
            if collection['name'] == collection_name:
                return collection
        return None
    except Exception as e:
        print(f"    ❌ Error getting collection from {endpoint_url}: {e}")
        return None

def wait_for_collection_sync(collection_name: str, should_exist: bool = True, timeout: int = SYNC_WAIT_TIMEOUT) -> bool:
    """Wait for collection to appear/disappear on replica"""
    start_time = time.time()
    endpoint_name = "replica"
    action = "appear" if should_exist else "disappear"
    
    print(f"  ⏳ Waiting for collection to {action} on {endpoint_name} (timeout: {timeout}s)...")
    
    while time.time() - start_time < timeout:
        replica_collection = get_collection_by_name(REPLICA_URL, collection_name)
        
        if should_exist and replica_collection is not None:
            sync_metadata = replica_collection.get('metadata', {})
            synced_from = sync_metadata.get('synced_from', 'unknown')
            sync_version = sync_metadata.get('sync_version', 'unknown')
            print(f"    ✅ Collection found on replica! (synced_from: {synced_from}, version: {sync_version})")
            return True
        elif not should_exist and replica_collection is None:
            print(f"    ✅ Collection removed from replica!")
            return True
        
        elapsed = time.time() - start_time
        print(f"    ⏳ Still waiting... ({elapsed:.1f}s elapsed)")
        time.sleep(POLL_INTERVAL)
    
    print(f"    ❌ Timeout: Collection did not {action} on replica within {timeout}s")
    return False

def check_sync_service_activity():
    """Check if sync service is active by looking at database"""
    try:
        with psycopg2.connect(DATABASE_URL) as conn:
            with conn.cursor() as cursor:
                # Check recent sync activity
                cursor.execute("""
                    SELECT COUNT(*) as recent_syncs
                    FROM sync_history 
                    WHERE sync_started_at > NOW() - INTERVAL '10 minutes'
                """)
                recent_syncs = cursor.fetchone()[0]
                
                # Check active workers
                cursor.execute("""
                    SELECT COUNT(*) as active_workers
                    FROM sync_workers 
                    WHERE last_heartbeat > NOW() - INTERVAL '5 minutes'
                """)
                active_workers = cursor.fetchone()[0]
                
                print(f"  📊 Sync Service Status:")
                print(f"    Recent syncs (10 min): {recent_syncs}")
                print(f"    Active workers: {active_workers}")
                
                return active_workers > 0 or recent_syncs > 0
                
    except Exception as e:
        print(f"  ❌ Error checking sync service: {e}")
        return False

def test_single_sync_transaction():
    """Test a complete add -> sync -> delete -> sync cycle"""
    print("🧪 SINGLE TRANSACTION SYNC VERIFICATION")
    print("=" * 80)
    print("Testing enhanced sync service with a single collection:")
    print("1. Add collection to primary")
    print("2. Wait for sync to replica")
    print("3. Delete from primary") 
    print("4. Wait for deletion sync from replica")
    print()
    
    collection_name = create_test_collection_name()
    collection_id = None
    
    try:
        # Step 1: Create collection on primary
        print("📦 STEP 1: Creating collection on primary")
        print(f"  Collection name: {collection_name}")
        
        create_url = f"{PRIMARY_URL}/api/v2/tenants/default_tenant/databases/default_database/collections"
        create_data = {
            "name": collection_name,
            "metadata": {
                "test_type": "single_sync_transaction",
                "safe_to_delete": True,
                "created_at": time.time(),
                "test_phase": "creation"
            }
        }
        
        start_time = time.time()
        response = make_request('POST', create_url, json=create_data)
        collection_id = response.json()['id']
        creation_time = time.time() - start_time
        
        print(f"  ✅ Collection created on primary ({creation_time:.2f}s)")
        print(f"  📄 Collection ID: {collection_id}")
        
        # Add some test documents
        add_url = f"{PRIMARY_URL}/api/v2/tenants/default_tenant/databases/default_database/collections/{collection_id}/add"
        add_data = {
            "ids": ["test_doc_1", "test_doc_2", "test_doc_3"],
            "documents": ["Test document 1", "Test document 2", "Test document 3"],
            "metadatas": [
                {"index": 1, "test": True},
                {"index": 2, "test": True}, 
                {"index": 3, "test": True}
            ]
        }
        make_request('POST', add_url, json=add_data)
        print(f"  📄 Added 3 test documents")
        
        # Verify collection exists on primary
        primary_collection = get_collection_by_name(PRIMARY_URL, collection_name)
        if primary_collection:
            print(f"  ✅ Verified collection exists on primary")
        else:
            print(f"  ❌ Collection not found on primary!")
            return False
        
        # Step 2: Wait for sync to replica
        print(f"\n🔄 STEP 2: Waiting for addition sync to replica")
        check_sync_service_activity()
        
        addition_sync_success = wait_for_collection_sync(collection_name, should_exist=True)
        if not addition_sync_success:
            print(f"  ❌ Addition sync failed - collection not synced to replica")
            return False
        
        # Verify documents synced correctly
        replica_collection = get_collection_by_name(REPLICA_URL, collection_name)
        if replica_collection:
            replica_id = replica_collection['id']
            try:
                count_url = f"{REPLICA_URL}/api/v2/tenants/default_tenant/databases/default_database/collections/{replica_id}/count"
                count_response = make_request('GET', count_url)
                doc_count = count_response.json()
                print(f"  📄 Replica has {doc_count} documents (expected: 3)")
            except Exception as e:
                print(f"  ⚠️ Could not verify document count on replica: {e}")
        
        print(f"  🎉 Addition sync completed successfully!")
        
        # Step 3: Delete collection from primary  
        print(f"\n🗑️ STEP 3: Deleting collection from primary")
        
        delete_url = f"{PRIMARY_URL}/api/v2/tenants/default_tenant/databases/default_database/collections/{collection_id}"
        start_time = time.time()
        make_request('DELETE', delete_url)
        deletion_time = time.time() - start_time
        
        print(f"  ✅ Collection deleted from primary ({deletion_time:.2f}s)")
        
        # Verify deletion on primary
        primary_collection_after = get_collection_by_name(PRIMARY_URL, collection_name)
        if primary_collection_after is None:
            print(f"  ✅ Verified collection removed from primary")
        else:
            print(f"  ❌ Collection still exists on primary!")
            return False
        
        # Step 4: Wait for deletion sync to replica
        print(f"\n🔄 STEP 4: Waiting for deletion sync to replica")
        check_sync_service_activity()
        
        deletion_sync_success = wait_for_collection_sync(collection_name, should_exist=False)
        if not deletion_sync_success:
            print(f"  ❌ Deletion sync failed - collection still exists on replica")
            print(f"  💡 This could indicate the enhanced deletion sync needs debugging")
            return False
        
        print(f"  🎉 Deletion sync completed successfully!")
        
        # Final verification
        print(f"\n✅ VERIFICATION COMPLETE")
        print("=" * 40)
        print("✅ Collection created on primary: SUCCESS")
        print("✅ Addition sync to replica: SUCCESS") 
        print("✅ Collection deleted from primary: SUCCESS")
        print("✅ Deletion sync from replica: SUCCESS")
        print()
        print("🎯 Enhanced sync service is working correctly for single transactions!")
        
        return True
        
    except Exception as e:
        print(f"\n❌ Test failed with error: {e}")
        return False
    
    finally:
        # Cleanup: ensure collection is deleted from both endpoints
        print(f"\n🧹 CLEANUP")
        if collection_id:
            for endpoint_name, endpoint_url in [("primary", PRIMARY_URL), ("replica", REPLICA_URL)]:
                try:
                    cleanup_collection = get_collection_by_name(endpoint_url, collection_name)
                    if cleanup_collection:
                        delete_url = f"{endpoint_url}/api/v2/tenants/default_tenant/databases/default_database/collections/{cleanup_collection['id']}"
                        make_request('DELETE', delete_url)
                        print(f"  ✅ Cleaned up collection from {endpoint_name}")
                    else:
                        print(f"  ✅ No cleanup needed on {endpoint_name}")
                except Exception as e:
                    print(f"  ⚠️ Cleanup failed on {endpoint_name}: {e}")

if __name__ == "__main__":
    success = test_single_sync_transaction()
    exit(0 if success else 1) 