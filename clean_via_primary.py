#!/usr/bin/env python3
"""
Clean up test collections from PRIMARY endpoint
This will test the enhanced sync service's deletion sync capability.
After deleting from primary, the enhanced sync service should detect
and remove the orphaned collections from replica.
"""

import requests
import time
import concurrent.futures
from typing import List, Dict

# Configuration
PRIMARY_URL = "https://chroma-primary.onrender.com"
REPLICA_URL = "https://chroma-replica.onrender.com"
TEST_PREFIX = "AUTOTEST_"

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

def delete_collection_from_primary(collection_info: Dict) -> Dict:
    """Delete a collection from primary"""
    collection_name = collection_info['name']
    collection_id = collection_info['id']
    
    try:
        start_time = time.time()
        
        delete_url = f"{PRIMARY_URL}/api/v2/tenants/default_tenant/databases/default_database/collections/{collection_id}"
        make_request('DELETE', delete_url)
        
        duration = time.time() - start_time
        
        return {
            'success': True,
            'collection_name': collection_name,
            'collection_id': collection_id,
            'duration_seconds': duration
        }
        
    except Exception as e:
        return {
            'success': False,
            'collection_name': collection_name,
            'collection_id': collection_id,
            'error': str(e),
            'duration_seconds': time.time() - start_time
        }

def get_collections_from_endpoint(endpoint_url: str, endpoint_name: str) -> List[Dict]:
    """Get collections from a specific endpoint"""
    try:
        collections_url = f"{endpoint_url}/api/v2/tenants/default_tenant/databases/default_database/collections"
        response = make_request('GET', collections_url)
        collections = response.json()
        test_collections = [col for col in collections if col['name'].startswith(TEST_PREFIX)]
        print(f"  📊 {endpoint_name}: {len(test_collections)} test collections")
        return test_collections
    except Exception as e:
        print(f"  ❌ {endpoint_name}: Error getting collections - {e}")
        return []

def clean_test_collections_from_primary():
    """Clean up test collections from primary and monitor replica"""
    print("🧹 CLEANING TEST COLLECTIONS FROM PRIMARY")
    print("=" * 60)
    print("This tests the enhanced sync service's deletion sync capability.")
    print()
    
    # Check collections on both endpoints before cleanup
    print("📊 BEFORE CLEANUP:")
    primary_collections = get_collections_from_endpoint(PRIMARY_URL, "Primary")
    replica_collections = get_collections_from_endpoint(REPLICA_URL, "Replica")
    
    if not primary_collections:
        print("✅ No test collections found on primary - cleanup not needed")
        return True
    
    print(f"\n🎯 Deleting {len(primary_collections)} collections from PRIMARY:")
    
    # Show what we're about to delete (first 10)
    for i, col in enumerate(primary_collections[:10], 1):
        print(f"   {i:2d}. {col['name']}")
    
    if len(primary_collections) > 10:
        print(f"   ... and {len(primary_collections) - 10} more")
        
    print(f"\n🗑️  Deleting from primary in parallel...")
    
    # Delete collections from primary in parallel
    successful_deletions = 0
    failed_deletions = 0
    
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as executor:
        # Submit deletion tasks
        future_to_collection = {
            executor.submit(delete_collection_from_primary, collection): collection
            for collection in primary_collections
        }
        
        # Process results as they complete
        for future in concurrent.futures.as_completed(future_to_collection):
            result = future.result()
            
            if result['success']:
                successful_deletions += 1
                print(f"  ✅ Deleted from primary: {result['collection_name']} ({result['duration_seconds']:.2f}s)")
            else:
                failed_deletions += 1
                print(f"  ❌ Failed: {result['collection_name']} - {result['error']}")
    
    print(f"\n📊 PRIMARY DELETION RESULTS:")
    print(f"  ✅ Successfully deleted: {successful_deletions}")
    print(f"  ❌ Failed to delete: {failed_deletions}")
    print(f"  📈 Success rate: {successful_deletions / len(primary_collections) * 100:.1f}%")
    
    # Check collections after cleanup
    print(f"\n📊 AFTER PRIMARY CLEANUP:")
    primary_collections_after = get_collections_from_endpoint(PRIMARY_URL, "Primary")
    replica_collections_after = get_collections_from_endpoint(REPLICA_URL, "Replica")
    
    print(f"\n🔄 SYNC SERVICE TEST:")
    if len(replica_collections_after) > 0:
        print(f"  🔍 Replica still has {len(replica_collections_after)} collections")
        print(f"  ⏳ Enhanced deletion sync should clean these up automatically")
        print(f"  💡 You can monitor this by checking the replica endpoint")
    else:
        print(f"  ✅ Replica is already clean - enhanced sync service working instantly!")
    
    print(f"\n🎉 Primary cleanup completed!")
    print(f"   Enhanced sync service will handle replica cleanup automatically.")
    
    return failed_deletions == 0

if __name__ == "__main__":
    success = clean_test_collections_from_primary()
    exit(0 if success else 1) 