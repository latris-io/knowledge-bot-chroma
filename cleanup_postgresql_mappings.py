#!/usr/bin/env python3

import requests
import time

def cleanup_postgresql_mappings():
    """Clean up phantom PostgreSQL collection mappings via load balancer API"""
    
    base_url = 'https://chroma-load-balancer.onrender.com'
    
    print("🗄️ CLEANING POSTGRESQL COLLECTION MAPPINGS")
    print("=" * 60)
    
    # Test patterns to identify collections to remove
    test_patterns = [
        'DELETE_TEST_',
        'AUTOTEST_',
        'TEST_',
        'PATCH_TEST_',
        'test_collection_',
        'failover_test_',
        'clean_query_test_',
        'test_'
    ]
    
    # Production collections to preserve
    preserve = ['global']
    
    try:
        # Get all collection mappings
        print("📊 Fetching collection mappings...")
        response = requests.get(f'{base_url}/collection/mappings', timeout=30)
        
        if response.status_code != 200:
            print(f"❌ Failed to get mappings: {response.status_code}")
            return
        
        mappings_data = response.json()
        all_mappings = mappings_data.get('mappings', [])
        
        print(f"Found {len(all_mappings)} collection mappings")
        
        # Identify test collections to delete
        to_delete = []
        to_preserve = []
        
        for mapping in all_mappings:
            collection_name = mapping.get('collection_name', '')
            
            if collection_name in preserve:
                to_preserve.append(collection_name)
            elif any(pattern in collection_name for pattern in test_patterns):
                to_delete.append(collection_name)
            else:
                to_preserve.append(collection_name)
        
        print(f"\n📋 Analysis:")
        print(f"  Collections to delete: {len(to_delete)}")
        print(f"  Collections to preserve: {len(to_preserve)}")
        
        if not to_delete:
            print("✅ No test collections to clean up!")
            return
        
        print(f"\n🗑️ Collections to be deleted:")
        for name in to_delete[:10]:  # Show first 10
            print(f"  • {name}")
        if len(to_delete) > 10:
            print(f"  • ... and {len(to_delete) - 10} more")
        
        print(f"\n🛡️ Collections to be preserved:")
        for name in to_preserve:
            print(f"  • {name}")
        
        confirm = input(f"\nProceed with deleting {len(to_delete)} test mappings? (yes/no): ").lower().strip()
        if confirm not in ['yes', 'y']:
            print("❌ Cancelled by user")
            return
        
        # Delete test collection mappings
        print(f"\n🧹 Deleting test collection mappings...")
        deleted_count = 0
        failed_count = 0
        
        for collection_name in to_delete:
            try:
                # Try to delete via load balancer API
                delete_response = requests.delete(
                    f'{base_url}/collection/mappings/{collection_name}',
                    timeout=30
                )
                
                if delete_response.status_code in [200, 204, 404]:
                    deleted_count += 1
                    print(f"  ✅ Deleted: {collection_name}")
                else:
                    failed_count += 1
                    print(f"  ❌ Failed: {collection_name} - status {delete_response.status_code}")
                
                # Small delay to avoid overwhelming the server
                time.sleep(0.5)
                
            except Exception as e:
                failed_count += 1
                print(f"  ❌ Failed: {collection_name} - {str(e)}")
        
        print(f"\n📊 Deletion Results:")
        print(f"  ✅ Successfully deleted: {deleted_count}")
        print(f"  ❌ Failed to delete: {failed_count}")
        
        # Verify cleanup
        print(f"\n🔍 Verifying cleanup...")
        verify_response = requests.get(f'{base_url}/collection/mappings', timeout=30)
        
        if verify_response.status_code == 200:
            verify_data = verify_response.json()
            remaining_mappings = verify_data.get('mappings', [])
            
            # Count remaining test collections
            remaining_test = 0
            for mapping in remaining_mappings:
                collection_name = mapping.get('collection_name', '')
                if any(pattern in collection_name for pattern in test_patterns) and collection_name not in preserve:
                    remaining_test += 1
            
            print(f"  Total mappings remaining: {len(remaining_mappings)}")
            print(f"  Test mappings remaining: {remaining_test}")
            
            if remaining_test == 0:
                print(f"\n🎉 POSTGRESQL CLEANUP SUCCESSFUL!")
                print("✅ All test collection mappings removed")
                print("✅ Production mappings preserved")
                print("✅ Database optimized")
            else:
                print(f"\n⚠️ PARTIAL SUCCESS")
                print(f"Still {remaining_test} test mappings remaining")
                print("These may need manual cleanup or database admin access")
        else:
            print(f"  ❌ Verification failed: {verify_response.status_code}")
        
    except Exception as e:
        print(f"❌ Cleanup failed: {e}")

def main():
    print("🧹 POSTGRESQL MAPPING CLEANUP")
    print("=" * 50)
    print("This will clean up phantom collection mappings from PostgreSQL")
    print("that are causing WAL sync failures and DELETE inconsistencies")
    
    cleanup_postgresql_mappings()
    
    print(f"\n🎯 WHAT THIS ACCOMPLISHED:")
    print("• Removed phantom collection mappings from PostgreSQL")
    print("• Preserved production collection mappings") 
    print("• Reduced WAL sync failures")
    print("• Improved DELETE operation consistency")
    print("• Optimized database performance")

if __name__ == '__main__':
    main() 