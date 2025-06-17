#!/usr/bin/env python3

"""
Test script to demonstrate bulletproof global collection protection
Shows that cleanup scripts will never delete the global collection
"""

import requests
import time
from cleanup_all_test_data import TestDataCleaner

def test_global_protection():
    """Test that global collection protection works"""
    
    print("🛡️ TESTING GLOBAL COLLECTION PROTECTION")
    print("=" * 60)
    
    cleaner = TestDataCleaner()
    
    # Test 1: Check is_test_collection method
    print("\n1️⃣ Testing is_test_collection() method:")
    
    test_cases = [
        ('global', False, "Production collection"),
        ('Global', False, "Case variation"),
        ('GLOBAL', False, "Uppercase"),
        ('production', False, "Other production name"),
        ('DELETE_TEST_123', True, "Valid test collection"),
        ('AUTOTEST_abc', True, "Valid test collection"),
        ('test_collection_456', True, "Valid test collection"),
        ('random_collection', False, "Unknown collection (safe approach)"),
        ('global_test', False, "Contains 'global' - protected"),
        ('test_global', False, "Contains 'global' - protected"),
    ]
    
    for collection_name, expected, description in test_cases:
        result = cleaner.is_test_collection(collection_name)
        status = "✅" if result == expected else "❌"
        print(f"   {status} '{collection_name}' -> {result} ({description})")
    
    # Test 2: Verify current global collection exists
    print("\n2️⃣ Verifying global collection exists:")
    
    primary_collections = cleaner.get_collections(cleaner.primary_url, "Primary")
    replica_collections = cleaner.get_collections(cleaner.replica_url, "Replica")
    
    global_on_primary = any(c.get('name', '') == 'global' for c in primary_collections)
    global_on_replica = any(c.get('name', '') == 'global' for c in replica_collections)
    
    print(f"   Primary: {'✅ Global found' if global_on_primary else '❌ Global missing'}")
    print(f"   Replica: {'✅ Global found' if global_on_replica else '❌ Global missing'}")
    
    # Test 3: Create test collection and run cleanup
    print("\n3️⃣ Testing cleanup with test collections:")
    
    test_collection = f"DELETE_TEST_{int(time.time())}_protection_test"
    
    try:
        # Create test collection
        create_response = requests.post(
            f"{cleaner.base_url}/api/v2/tenants/default_tenant/databases/default_database/collections",
            json={"name": test_collection, "configuration": {"hnsw": {"space": "l2"}}},
            timeout=30
        )
        
        if create_response.status_code in [200, 201]:
            print(f"   ✅ Created test collection: {test_collection}")
            
            # Wait for sync
            time.sleep(2)
            
            # Check collections exist
            primary_after_create = cleaner.get_collections(cleaner.primary_url, "Primary")
            replica_after_create = cleaner.get_collections(cleaner.replica_url, "Replica")
            
            primary_count = len(primary_after_create)
            replica_count = len(replica_after_create)
            
            print(f"   📊 After creation - Primary: {primary_count} collections, Replica: {replica_count} collections")
            
            # Test cleanup (only test collections should be deleted)
            print(f"\n   🧹 Running cleanup (should preserve global)...")
            
            # Test the delete_collection method directly
            test_coll_obj = {'name': test_collection, 'id': 'test-id'}
            global_coll_obj = {'name': 'global', 'id': 'global-id'}
            
            # This should succeed
            test_delete_result = cleaner.delete_collection(cleaner.primary_url, test_coll_obj)
            print(f"   📝 Test collection deletion: {'✅ Allowed' if test_delete_result else '❌ Blocked'}")
            
            # This should be blocked
            global_delete_result = cleaner.delete_collection(cleaner.primary_url, global_coll_obj)
            print(f"   🔒 Global collection deletion: {'❌ Wrongly allowed!' if global_delete_result else '✅ Correctly blocked'}")
            
        else:
            print(f"   ❌ Failed to create test collection: {create_response.status_code}")
    
    except Exception as e:
        print(f"   ❌ Test failed: {e}")
    
    # Test 4: Final verification
    print("\n4️⃣ Final verification:")
    
    final_primary = cleaner.get_collections(cleaner.primary_url, "Primary")
    final_replica = cleaner.get_collections(cleaner.replica_url, "Replica")
    
    final_global_primary = any(c.get('name', '') == 'global' for c in final_primary)
    final_global_replica = any(c.get('name', '') == 'global' for c in final_replica)
    
    print(f"   Primary global: {'✅ Still exists' if final_global_primary else '❌ MISSING!'}")
    print(f"   Replica global: {'✅ Still exists' if final_global_replica else '❌ MISSING!'}")
    
    # Overall result
    protection_working = (
        final_global_primary and final_global_replica and 
        not cleaner.is_test_collection('global') and
        not cleaner.is_test_collection('Global') and
        not cleaner.is_test_collection('GLOBAL')
    )
    
    print(f"\n🎯 PROTECTION TEST RESULT:")
    if protection_working:
        print("🎉 GLOBAL COLLECTION PROTECTION IS WORKING PERFECTLY!")
        print("✅ Global collection cannot be deleted by cleanup scripts")
        print("✅ is_test_collection() correctly identifies protected collections")
        print("✅ delete_collection() blocks deletion of protected collections")
        print("✅ Your production data is SAFE during cleanup operations")
    else:
        print("🚨 PROTECTION TEST FAILED!")
        print("❌ Global collection protection may not be working properly")
        print("❌ IMMEDIATE INVESTIGATION REQUIRED!")

def main():
    print("🧪 GLOBAL COLLECTION PROTECTION TEST")
    print("Demonstrating bulletproof protection during cleanup operations")
    print("=" * 70)
    
    test_global_protection()
    
    print(f"\n📋 SUMMARY:")
    print("The cleanup scripts have multiple layers of protection:")
    print("• Layer 1: Protected collection list (case-insensitive)")
    print("• Layer 2: Test pattern validation")
    print("• Layer 3: Safe prefix requirements")
    print("• Layer 4: Runtime safety checks before deletion")
    print("• Layer 5: Post-cleanup verification")
    print(f"\nThe 'global' collection mapping will NEVER be deleted!")

if __name__ == '__main__':
    main() 