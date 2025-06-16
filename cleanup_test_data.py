#!/usr/bin/env python3
"""
Test Data Cleanup Script
Finds and removes all test collections from the database
"""
import requests
import sys

def cleanup_test_data(base_url="https://chroma-load-balancer.onrender.com"):
    """Clean up all test collections"""
    print("🧹 Scanning for test collections...")
    
    try:
        # Get all collections
        response = requests.get(
            f"{base_url}/api/v2/tenants/default_tenant/databases/default_database/collections",
            timeout=30
        )
        
        if response.status_code != 200:
            print(f"❌ Failed to list collections: {response.status_code}")
            return False
        
        collections = response.json()
        
        # Find test collections
        test_collections = [
            c for c in collections 
            if any(pattern in c.get('name', '').lower() for pattern in [
                'autotest', 'failover', 'test_', '_test', 'demo_', 'temp_'
            ])
        ]
        
        if not test_collections:
            print("✅ No test collections found - database is clean")
            return True
        
        print(f"Found {len(test_collections)} test collections:")
        for c in test_collections:
            print(f"  - {c['name']}")
        
        # Clean up each collection
        cleaned = 0
        failed = 0
        
        for collection in test_collections:
            name = collection['name']
            try:
                response = requests.delete(
                    f"{base_url}/api/v2/tenants/default_tenant/databases/default_database/collections/{name}",
                    timeout=30
                )
                
                if response.status_code in [200, 404]:
                    print(f"✅ Deleted: {name}")
                    cleaned += 1
                else:
                    print(f"❌ Failed to delete {name}: {response.status_code}")
                    failed += 1
            except Exception as e:
                print(f"❌ Error deleting {name}: {e}")
                failed += 1
        
        print(f"\n🧹 Cleanup Summary:")
        print(f"  Collections cleaned: {cleaned}")
        print(f"  Failed cleanups: {failed}")
        print(f"  Success rate: {cleaned/(cleaned+failed)*100:.1f}%" if (cleaned+failed) > 0 else "  No collections processed")
        
        return failed == 0
        
    except Exception as e:
        print(f"❌ Cleanup failed: {e}")
        return False

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Clean up test collections")
    parser.add_argument("--url", default="https://chroma-load-balancer.onrender.com", help="Base URL")
    args = parser.parse_args()
    
    success = cleanup_test_data(args.url)
    sys.exit(0 if success else 1) 