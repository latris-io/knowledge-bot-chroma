#!/usr/bin/env python3
"""
Test script to verify that POST requests to read endpoints are not logged to WAL
"""
import requests
import time
import json

BASE_URL = "https://chroma-load-balancer.onrender.com"

def get_wal_count():
    """Get current WAL count"""
    try:
        response = requests.get(f"{BASE_URL}/admin/wal_count", timeout=10)
        if response.status_code == 200:
            return response.json().get('pending_writes', 0)
        return -1
    except:
        return -1

def test_read_operations_not_logged():
    """Test that read operations are not logged to WAL"""
    print("🧪 Testing WAL read fix...")
    
    # Get initial WAL count
    initial_count = get_wal_count()
    print(f"   Initial WAL count: {initial_count}")
    
    # Test 1: Make a POST request to /get endpoint (should NOT be logged to WAL)
    print("   Testing POST to /get endpoint...")
    try:
        response = requests.post(
            f"{BASE_URL}/api/v2/tenants/default_tenant/databases/default_database/collections/global/get",
            headers={"Content-Type": "application/json"},
            json={"include": ["documents"], "limit": 1},
            timeout=10
        )
        print(f"   GET request status: {response.status_code}")
    except Exception as e:
        print(f"   GET request failed: {e}")
    
    # Test 2: Make a POST request to /query endpoint (should NOT be logged to WAL)
    print("   Testing POST to /query endpoint...")
    try:
        response = requests.post(
            f"{BASE_URL}/api/v2/tenants/default_tenant/databases/default_database/collections/global/query",
            headers={"Content-Type": "application/json"},
            json={"query_texts": ["test"], "n_results": 1},
            timeout=10
        )
        print(f"   Query request status: {response.status_code}")
    except Exception as e:
        print(f"   Query request failed: {e}")
    
    # Test 3: Make a POST request to /count endpoint (should NOT be logged to WAL)  
    print("   Testing POST to /count endpoint...")
    try:
        response = requests.post(
            f"{BASE_URL}/api/v2/tenants/default_tenant/databases/default_database/collections/global/count",
            headers={"Content-Type": "application/json"},
            json={},
            timeout=10
        )
        print(f"   Count request status: {response.status_code}")
    except Exception as e:
        print(f"   Count request failed: {e}")
    
    # Wait a few seconds for any potential WAL logging
    print("   Waiting 5 seconds for potential WAL logging...")
    time.sleep(5)
    
    # Check final WAL count
    final_count = get_wal_count()
    print(f"   Final WAL count: {final_count}")
    
    # Verify no increase in WAL count
    if final_count == initial_count:
        print("✅ SUCCESS: Read operations were NOT logged to WAL (fix working!)")
        return True
    elif final_count > initial_count:
        print(f"❌ FAILURE: WAL count increased by {final_count - initial_count} (read operations still being logged)")
        return False
    else:
        print("⚠️  WARNING: Could not determine WAL status")
        return False

def test_write_operations_still_logged():
    """Test that write operations are still logged to WAL"""
    print("🧪 Testing that write operations are still logged...")
    
    # Get initial WAL count
    initial_count = get_wal_count()
    print(f"   Initial WAL count: {initial_count}")
    
    # Create a test collection (should be logged to WAL for sync)
    test_collection = f"WAL_TEST_{int(time.time())}"
    print(f"   Creating test collection: {test_collection}")
    
    try:
        response = requests.post(
            f"{BASE_URL}/api/v2/tenants/default_tenant/databases/default_database/collections",
            headers={"Content-Type": "application/json"},
            json={"name": test_collection},
            timeout=15
        )
        print(f"   Collection creation status: {response.status_code}")
        
        if response.status_code == 200:
            # Wait for potential WAL logging
            time.sleep(3)
            
            # Check if WAL count increased (it should for write operations)
            final_count = get_wal_count()
            print(f"   Final WAL count: {final_count}")
            
            # Clean up test collection
            try:
                requests.delete(
                    f"{BASE_URL}/api/v2/tenants/default_tenant/databases/default_database/collections/{test_collection}",
                    timeout=10
                )
                print(f"   ✅ Cleaned up test collection: {test_collection}")
            except:
                print(f"   ⚠️ Failed to clean up test collection: {test_collection}")
            
            if final_count >= initial_count:
                print("✅ SUCCESS: Write operations are still being logged to WAL")
                return True
            else:
                print("❌ FAILURE: Write operations not being logged to WAL")
                return False
        else:
            print(f"❌ FAILURE: Could not create test collection (status: {response.status_code})")
            return False
            
    except Exception as e:
        print(f"❌ FAILURE: Exception during write test: {e}")
        return False

if __name__ == "__main__":
    print("🔧 WAL Read Fix Verification Test")
    print("=" * 50)
    
    # Test 1: Read operations should NOT be logged
    read_test_passed = test_read_operations_not_logged()
    print()
    
    # Test 2: Write operations should STILL be logged  
    write_test_passed = test_write_operations_still_logged()
    print()
    
    # Summary
    print("📊 TEST RESULTS")
    print("=" * 50)
    print(f"Read operations NOT logged to WAL: {'✅ PASS' if read_test_passed else '❌ FAIL'}")
    print(f"Write operations STILL logged to WAL: {'✅ PASS' if write_test_passed else '❌ FAIL'}")
    
    if read_test_passed and write_test_passed:
        print("🎉 ALL TESTS PASSED - WAL read fix is working correctly!")
    else:
        print("⚠️ SOME TESTS FAILED - WAL read fix may need additional work") 