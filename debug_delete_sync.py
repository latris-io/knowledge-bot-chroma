#!/usr/bin/env python3
"""
Debug DELETE Sync Issue
Test DELETE operations to see where they're failing
"""

import requests
import json
import time

def debug_delete_sync():
    """Debug DELETE sync to understand why replica deletions fail"""
    
    print("🔍 DEBUG: DELETE Sync Investigation")
    print("=" * 60)
    
    # URLs
    load_balancer_url = "https://chroma-load-balancer.onrender.com"
    primary_url = "https://chroma-primary.onrender.com"
    replica_url = "https://chroma-replica.onrender.com"
    
    # Create a test collection via load balancer
    collection_name = f"DELETE_DEBUG_TEST_{int(time.time())}"
    
    print(f"📝 Step 1: Creating test collection '{collection_name}'")
    create_response = requests.post(
        f"{load_balancer_url}/api/v2/tenants/default_tenant/databases/default_database/collections",
        json={"name": collection_name},
        timeout=30
    )
    
    if create_response.status_code not in [200, 201]:
        print(f"❌ Collection creation failed: {create_response.status_code}")
        return
    
    print(f"✅ Collection created: {create_response.status_code}")
    
    # Wait for auto-mapping
    print("⏱️ Waiting 10s for auto-mapping...")
    time.sleep(10)
    
    # Get collection mappings
    print("📋 Step 2: Getting collection mappings")
    mappings_response = requests.get(f"{load_balancer_url}/collection/mappings", timeout=30)
    
    primary_uuid = None
    replica_uuid = None
    
    if mappings_response.status_code == 200:
        mappings = mappings_response.json().get('mappings', [])
        for mapping in mappings:
            if mapping['collection_name'] == collection_name:
                primary_uuid = mapping['primary_collection_id']
                replica_uuid = mapping['replica_collection_id']
                print(f"✅ Found mapping:")
                print(f"   Primary UUID: {primary_uuid}")
                print(f"   Replica UUID: {replica_uuid}")
                break
    
    if not primary_uuid or not replica_uuid:
        print(f"❌ No mapping found for collection '{collection_name}'")
        return
    
    # Verify collection exists on both instances
    print("🔍 Step 3: Verifying collection exists on both instances")
    
    # Check primary by UUID
    primary_check = requests.get(
        f"{primary_url}/api/v2/tenants/default_tenant/databases/default_database/collections/{primary_uuid}",
        timeout=30
    )
    print(f"   Primary (UUID): {primary_check.status_code}")
    
    # Check primary by name
    primary_name_check = requests.get(
        f"{primary_url}/api/v2/tenants/default_tenant/databases/default_database/collections/{collection_name}",
        timeout=30
    )
    print(f"   Primary (name): {primary_name_check.status_code}")
    
    # Check replica by UUID
    replica_check = requests.get(
        f"{replica_url}/api/v2/tenants/default_tenant/databases/default_database/collections/{replica_uuid}",
        timeout=30
    )
    print(f"   Replica (UUID): {replica_check.status_code}")
    
    # Check replica by name
    replica_name_check = requests.get(
        f"{replica_url}/api/v2/tenants/default_tenant/databases/default_database/collections/{collection_name}",
        timeout=30
    )
    print(f"   Replica (name): {replica_name_check.status_code}")
    
    # Now test DELETE via load balancer
    print("🗑️ Step 4: Testing DELETE via load balancer")
    
    delete_response = requests.delete(
        f"{load_balancer_url}/api/v2/tenants/default_tenant/databases/default_database/collections/{collection_name}",
        timeout=30
    )
    
    print(f"✅ DELETE request: {delete_response.status_code}")
    
    if delete_response.content:
        try:
            delete_result = delete_response.json()
            print(f"   Response: {json.dumps(delete_result, indent=2)}")
        except:
            print(f"   Response (raw): {delete_response.text}")
    
    # Wait for any async processing
    print("⏱️ Waiting 5s for DELETE processing...")
    time.sleep(5)
    
    # Verify deletion on both instances
    print("🔍 Step 5: Verifying deletion on both instances")
    
    # Check primary
    primary_after = requests.get(
        f"{primary_url}/api/v2/tenants/default_tenant/databases/default_database/collections/{collection_name}",
        timeout=30
    )
    print(f"   Primary after DELETE: {primary_after.status_code} {'(deleted)' if primary_after.status_code == 404 else '(still exists)'}")
    
    # Check replica  
    replica_after = requests.get(
        f"{replica_url}/api/v2/tenants/default_tenant/databases/default_database/collections/{collection_name}",
        timeout=30
    )
    print(f"   Replica after DELETE: {replica_after.status_code} {'(deleted)' if replica_after.status_code == 404 else '(still exists)'}")
    
    # Manual cleanup if DELETE failed
    if replica_after.status_code != 404:
        print("🧹 Step 6: Manual replica cleanup")
        manual_delete = requests.delete(
            f"{replica_url}/api/v2/tenants/default_tenant/databases/default_database/collections/{collection_name}",
            timeout=30
        )
        print(f"   Manual replica DELETE: {manual_delete.status_code}")
    
    print("\n" + "=" * 60)
    print("🎯 DELETE Sync Analysis:")
    if primary_after.status_code == 404 and replica_after.status_code == 404:
        print("✅ SUCCESS: Both instances properly deleted")
    elif primary_after.status_code == 404 and replica_after.status_code != 404:
        print("❌ FAILED: Primary deleted, replica still exists (DELETE sync broken)")
    elif primary_after.status_code != 404 and replica_after.status_code == 404:
        print("❌ FAILED: Replica deleted, primary still exists (unusual)")
    else:
        print("❌ FAILED: Both instances still exist (DELETE completely failed)")

if __name__ == "__main__":
    debug_delete_sync() 