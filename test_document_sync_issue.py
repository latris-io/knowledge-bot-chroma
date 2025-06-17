#!/usr/bin/env python3

import requests
import time
import json

def test_document_sync():
    """Test document sync by adding a test document and monitoring sync"""
    
    print("🔍 TESTING DOCUMENT SYNC ISSUE")
    print("=" * 50)
    
    # Step 1: Add a test document via load balancer
    print("1. Adding test document via load balancer...")
    
    test_doc = {
        "ids": ["sync_test_001"],
        "documents": ["This is a test document to verify sync functionality"],
        "metadatas": [{"test": True, "timestamp": str(time.time())}]
    }
    
    try:
        response = requests.post(
            "https://chroma-load-balancer.onrender.com/api/v2/tenants/default_tenant/databases/default_database/collections/global/add",
            headers={"Content-Type": "application/json"},
            json=test_doc,
            timeout=30
        )
        
        print(f"   Add response: {response.status_code}")
        if response.status_code != 200:
            print(f"   Error: {response.text}")
            return
        
    except Exception as e:
        print(f"   ❌ Error adding document: {e}")
        return
    
    # Step 2: Wait for sync
    print("2. Waiting for WAL sync...")
    time.sleep(20)
    
    # Step 3: Check document counts on both instances
    print("3. Checking document counts after sync...")
    
    # Primary count
    try:
        primary_response = requests.post(
            "https://chroma-primary.onrender.com/api/v2/tenants/default_tenant/databases/default_database/collections/efc00f17-111e-45c4-a85f-4b908406665d/get",
            headers={"Content-Type": "application/json"},
            json={"limit": 1, "include": ["documents"]},
            timeout=15
        )
        primary_count = len(primary_response.json()["ids"]) if primary_response.status_code == 200 else 0
        print(f"   Primary documents: {primary_count}")
        
    except Exception as e:
        print(f"   ❌ Error checking primary: {e}")
        primary_count = 0
    
    # Replica count
    try:
        replica_response = requests.post(
            "https://chroma-replica.onrender.com/api/v2/tenants/default_tenant/databases/default_database/collections/799fd0bf-ee2d-4174-bf3a-71f842a3acb8/get",
            headers={"Content-Type": "application/json"},
            json={"limit": 1, "include": ["documents"]},
            timeout=15
        )
        replica_count = len(replica_response.json()["ids"]) if replica_response.status_code == 200 else 0
        print(f"   Replica documents: {replica_count}")
        
    except Exception as e:
        print(f"   ❌ Error checking replica: {e}")
        replica_count = 0
    
    # Step 4: Check WAL status
    print("4. Checking WAL sync status...")
    try:
        wal_response = requests.get("https://chroma-load-balancer.onrender.com/wal/status", timeout=10)
        if wal_response.status_code == 200:
            wal_data = wal_response.json()
            stats = wal_data["performance_stats"]
            print(f"   WAL: {stats['successful_syncs']} success / {stats['failed_syncs']} failed")
        else:
            print(f"   ❌ WAL status error: {wal_response.status_code}")
            
    except Exception as e:
        print(f"   ❌ Error getting WAL status: {e}")
    
    # Step 5: Analysis
    print("\n📊 SYNC ANALYSIS:")
    if primary_count > replica_count:
        print(f"   ❌ SYNC FAILURE: Primary has {primary_count} docs, replica has {replica_count} docs")
        print(f"   🔍 This confirms WAL document sync is broken")
    elif primary_count == replica_count and primary_count > 0:
        print(f"   ✅ SYNC SUCCESS: Both instances have {primary_count} documents")
    else:
        print(f"   ⚠️ UNCLEAR: Primary={primary_count}, Replica={replica_count}")

if __name__ == "__main__":
    test_document_sync() 