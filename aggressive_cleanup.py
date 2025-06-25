#!/usr/bin/env python3
"""
🧹 AGGRESSIVE CLEANUP: Remove all USE CASE 5 test collections
"""

import requests
import time
import argparse

def main():
    parser = argparse.ArgumentParser(description='Aggressive cleanup of USE CASE 5 test data')
    parser.add_argument('--url', required=True, help='Chroma server URL')
    args = parser.parse_args()
    
    base_url = args.url.rstrip('/')
    
    print("🧹 AGGRESSIVE CLEANUP: Removing all USE CASE 5 test collections")
    print("=" * 60)
    
    # Get all collections
    print("📋 Fetching all collections...")
    response = requests.get(f"{base_url}/api/v2/tenants/default_tenant/databases/default_database/collections")
    if response.status_code != 200:
        print(f"❌ Failed to fetch collections: {response.status_code}")
        return False
    
    collections = response.json()
    print(f"Total collections found: {len(collections)}")
    
    # Filter test collections
    test_patterns = [
        'UC5_SCALABILITY',
        'test_',
        'USE_CASE_',
        'UC4_SAFETY',
        'UC3_FAILOVER',
        'UC2_RESILIENCE',
        'UC1_DISTRIBUTED',
        '_baseline_',
        '_connection_pooling_',
        '_granular_locking_',
        '_combined_features_',
        '_resource_scaling_',
        '_scalability_test_',
        'CONCURRENT_NORMAL',
        'CONCURRENT_STRESS'
    ]
    
    test_collections = []
    for collection in collections:
        name = collection['name']
        if any(pattern in name for pattern in test_patterns):
            test_collections.append(name)
    
    print(f"Test collections to remove: {len(test_collections)}")
    
    if not test_collections:
        print("✅ No test collections found to clean")
        return True
    
    # Delete collections in batches
    batch_size = 10
    deleted_count = 0
    failed_count = 0
    
    for i in range(0, len(test_collections), batch_size):
        batch = test_collections[i:i + batch_size]
        print(f"\n🗑️  Processing batch {i//batch_size + 1}/{(len(test_collections) + batch_size - 1)//batch_size}")
        
        for collection_name in batch:
            try:
                # Delete collection
                delete_url = f"{base_url}/api/v2/tenants/default_tenant/databases/default_database/collections/{collection_name}"
                response = requests.delete(delete_url)
                
                if response.status_code == 200:
                    deleted_count += 1
                    print(f"  ✅ Deleted: {collection_name}")
                else:
                    failed_count += 1
                    print(f"  ❌ Failed to delete {collection_name}: {response.status_code}")
                    
            except Exception as e:
                failed_count += 1
                print(f"  ❌ Error deleting {collection_name}: {e}")
        
        # Small delay between batches
        time.sleep(0.5)
    
    print(f"\n📊 Cleanup Summary:")
    print(f"  ✅ Successfully deleted: {deleted_count}")
    print(f"  ❌ Failed to delete: {failed_count}")
    
    # Final verification
    print(f"\n🔍 Final verification...")
    response = requests.get(f"{base_url}/api/v2/tenants/default_tenant/databases/default_database/collections")
    if response.status_code == 200:
        remaining_collections = response.json()
        remaining_test_collections = [col['name'] for col in remaining_collections 
                                    if any(pattern in col['name'] for pattern in test_patterns)]
        
        print(f"  Total collections remaining: {len(remaining_collections)}")
        print(f"  Test collections remaining: {len(remaining_test_collections)}")
        
        if remaining_test_collections:
            print("  ⚠️  Some test collections still remain:")
            for name in remaining_test_collections[:5]:  # Show first 5
                print(f"    - {name}")
            if len(remaining_test_collections) > 5:
                print(f"    ... and {len(remaining_test_collections) - 5} more")
    
    print(f"\n✅ Aggressive cleanup completed!")
    return deleted_count > 0

if __name__ == "__main__":
    main()
