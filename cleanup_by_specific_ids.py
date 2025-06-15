#!/usr/bin/env python3
"""
Cleanup by Specific IDs
Uses the actual collection IDs from each endpoint's listing to attempt deletion.
This handles the case where primary and replica have different IDs for same-named collections.
"""

import requests
import time
import json
import concurrent.futures
from typing import List, Dict, Tuple

# Configuration
PRIMARY_URL = "https://chroma-primary.onrender.com"
REPLICA_URL = "https://chroma-replica.onrender.com"
LOAD_BALANCER_URL = "https://chroma-load-balancer.onrender.com"
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

def get_collections_with_ids(endpoint_url: str, endpoint_name: str) -> List[Dict]:
    """Get all test collections with their specific IDs from an endpoint"""
    try:
        print(f"📋 Getting collections with IDs from {endpoint_name}...")
        response = make_request('GET', f"{endpoint_url}/api/v2/tenants/default_tenant/databases/default_database/collections")
        collections = response.json()
        
        test_collections = [c for c in collections if c['name'].startswith(TEST_PREFIX)]
        print(f"   Found {len(test_collections)} test collections on {endpoint_name}")
        
        # Show first few collections with their IDs
        for i, col in enumerate(test_collections[:3]):
            print(f"   Example {i+1}: {col['name']} -> ID: {col['id']}")
        if len(test_collections) > 3:
            print(f"   ... and {len(test_collections) - 3} more")
        
        return test_collections
    except Exception as e:
        print(f"❌ Error getting collections from {endpoint_name}: {e}")
        return []

def delete_collection_by_id(endpoint_url: str, endpoint_name: str, collection: Dict) -> Tuple[bool, str, str]:
    """Delete a single collection using its specific ID"""
    collection_name = collection['name']
    collection_id = collection['id']
    
    try:
        # Try deletion by ID
        delete_url = f"{endpoint_url}/api/v2/tenants/default_tenant/databases/default_database/collections/{collection_id}"
        make_request('DELETE', delete_url)
        return True, f"✅ Deleted '{collection_name}' (ID: {collection_id}) from {endpoint_name}", collection_id
        
    except requests.exceptions.HTTPError as e:
        if e.response.status_code == 404:
            return False, f"⚠️ Collection '{collection_name}' (ID: {collection_id}) not found on {endpoint_name} (404)", collection_id
        else:
            return False, f"❌ Failed to delete '{collection_name}' (ID: {collection_id}) from {endpoint_name}: {e}", collection_id
    except Exception as e:
        return False, f"❌ Error deleting '{collection_name}' (ID: {collection_id}) from {endpoint_name}: {e}", collection_id

def cleanup_endpoint_by_ids(endpoint_url: str, endpoint_name: str) -> Tuple[int, int, List[str]]:
    """Clean up test collections using their specific IDs"""
    print(f"\n🧹 CLEANING UP {endpoint_name.upper()} BY SPECIFIC IDS")
    print("=" * 60)
    
    # Get collections with their IDs
    test_collections = get_collections_with_ids(endpoint_url, endpoint_name)
    
    if not test_collections:
        print(f"✅ No test collections found on {endpoint_name}")
        return 0, 0, []
    
    # Attempt deletions using specific IDs
    successful_deletions = 0
    failed_deletions = 0
    successful_ids = []
    
    print(f"🗑️ Attempting to delete {len(test_collections)} collections using their specific IDs...")
    
    # Try both parallel and sequential approaches
    print(f"   📍 Using parallel deletion (max 5 workers to avoid overwhelming server)")
    
    with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
        # Submit deletion tasks
        future_to_collection = {
            executor.submit(delete_collection_by_id, endpoint_url, endpoint_name, collection): collection
            for collection in test_collections
        }
        
        # Process results
        for future in concurrent.futures.as_completed(future_to_collection):
            success, message, collection_id = future.result()
            print(f"   {message}")
            
            if success:
                successful_deletions += 1
                successful_ids.append(collection_id)
            else:
                failed_deletions += 1
    
    print(f"\n📊 {endpoint_name} Cleanup Results:")
    print(f"   ✅ Successfully deleted: {successful_deletions}")
    print(f"   ❌ Failed to delete: {failed_deletions}")
    
    if successful_deletions > 0:
        print(f"   🎯 Successfully deleted IDs: {successful_ids[:3]}{'...' if len(successful_ids) > 3 else ''}")
    
    return successful_deletions, failed_deletions, successful_ids

def verify_cleanup_status() -> None:
    """Verify current cleanup status across all endpoints"""
    print(f"\n🔍 VERIFYING CLEANUP STATUS")
    print("=" * 40)
    
    endpoints = [
        (PRIMARY_URL, "Primary"),
        (REPLICA_URL, "Replica"), 
        (LOAD_BALANCER_URL, "Load Balancer")
    ]
    
    for endpoint_url, endpoint_name in endpoints:
        try:
            response = make_request('GET', f"{endpoint_url}/api/v2/tenants/default_tenant/databases/default_database/collections")
            collections = response.json()
            test_collections = [c for c in collections if c['name'].startswith(TEST_PREFIX)]
            
            print(f"📊 {endpoint_name}: {len(test_collections)} test collections remaining")
            if test_collections and len(test_collections) <= 5:
                for col in test_collections:
                    print(f"     - {col['name']} (ID: {col['id']})")
        except Exception as e:
            print(f"❌ Error checking {endpoint_name}: {e}")

def main():
    """Main cleanup function"""
    print("🧹 CLEANUP BY SPECIFIC IDS")
    print("=" * 50)
    print("This script attempts to delete test collections using their specific IDs")
    print("from each endpoint's current listing, handling ID differences properly.")
    print("")
    
    # Get initial status
    verify_cleanup_status()
    
    # Cleanup primary endpoint using its specific IDs
    primary_success, primary_failed, primary_ids = cleanup_endpoint_by_ids(PRIMARY_URL, "Primary")
    
    # Small delay between endpoints
    time.sleep(2)
    
    # Cleanup replica endpoint using its specific IDs  
    replica_success, replica_failed, replica_ids = cleanup_endpoint_by_ids(REPLICA_URL, "Replica")
    
    # Summary
    total_success = primary_success + replica_success
    total_failed = primary_failed + replica_failed
    
    print(f"\n🎯 OVERALL CLEANUP SUMMARY")
    print("=" * 35)
    print(f"✅ Total collections deleted: {total_success}")
    print(f"❌ Total deletions failed: {total_failed}")
    
    if total_success > 0:
        print(f"🎉 Successfully deleted {total_success} collections!")
        print(f"   Primary: {primary_success} deleted")
        print(f"   Replica: {replica_success} deleted")
        
        # Wait for database consistency
        print(f"\n⏳ Waiting 15 seconds for database consistency...")
        time.sleep(15)
        
        # Verify final status
        verify_cleanup_status()
        
        print(f"\n🚀 Ready to test enhanced sync service with proper ID mapping!")
        
    elif total_failed > 0:
        print(f"\n💡 Analysis:")
        if primary_failed > 0 and replica_failed > 0:
            print(f"   - Both endpoints had deletion failures")
            print(f"   - This confirms the database consistency issue (phantom collections)")
            print(f"   - Collections exist in listings but return 404 on direct access")
        
        print(f"\n🔧 Next Steps:")
        print(f"   - Enhanced sync service improvements are still valid")
        print(f"   - Database consistency issue is separate from sync functionality")
        print(f"   - Can proceed with testing sync service enhancements")

if __name__ == "__main__":
    main() 