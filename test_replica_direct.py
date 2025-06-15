import requests
import json

def test_replica_direct():
    replica_id = "4e5e29a0-38b9-4ce4-b589-3ce01e0d6528"
    
    print("🔍 TESTING REPLICA COLLECTION DIRECTLY")
    print("=" * 50)
    
    # Test 1: Check if collection exists
    print("1. Checking if replica collection exists...")
    get_response = requests.get(
        f"https://chroma-replica.onrender.com/api/v2/tenants/default_tenant/databases/default_database/collections/{replica_id}",
        timeout=30
    )
    print(f"   Collection status: {get_response.status_code}")
    
    if get_response.status_code == 200:
        collection_data = get_response.json()
        print(f"   ✅ Collection exists: {collection_data.get('name')}")
        print(f"   Config: {collection_data.get('configuration_json', {})}")
    else:
        print(f"   ❌ Collection issue: {get_response.text}")
        return
    
    # Test 2: Try adding a document directly to replica
    print("2. Testing direct document add to replica...")
    
    test_payload = {
        "embeddings": [[0.1] * 3072],
        "documents": ["Direct test to replica collection"],
        "metadatas": [{"test": "replica_direct"}],
        "ids": ["replica_test_1"]
    }
    
    add_response = requests.post(
        f"https://chroma-replica.onrender.com/api/v2/tenants/default_tenant/databases/default_database/collections/{replica_id}/add",
        headers={"Content-Type": "application/json"},
        json=test_payload,
        timeout=30
    )
    
    print(f"   Direct add status: {add_response.status_code}")
    
    if add_response.status_code in [200, 201]:
        print("   ✅ Direct add successful - replica collection is working!")
        
        # Check document count
        count_response = requests.get(
            f"https://chroma-replica.onrender.com/api/v2/tenants/default_tenant/databases/default_database/collections/{replica_id}/count",
            timeout=30
        )
        if count_response.status_code == 200:
            count = int(count_response.text)
            print(f"   ✅ Replica now has {count} documents")
            
            if count > 0:
                print("   🎉 REPLICA COLLECTION IS FULLY FUNCTIONAL!")
                print("   ❌ Issue must be in the WAL sync request format")
        
    else:
        print(f"   ❌ Direct add failed: {add_response.status_code}")
        print(f"   Error details: {add_response.text}")
        
        # This will help us understand what the 400 error specifically is
        print("   📝 This error shows us what's wrong with the sync requests")
    
    print(f"\n{'='*50}")
    print("🔍 REPLICA DIRECT TEST COMPLETED!")
    print(f"{'='*50}")

if __name__ == "__main__":
    test_replica_direct() 