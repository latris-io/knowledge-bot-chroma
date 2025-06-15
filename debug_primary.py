import requests
import json

print("🔍 Debugging ChromaDB Primary API")
print("=" * 50)

primary_url = "https://chroma-primary.onrender.com"
global_id = "eb07030e-ed7e-4aab-8249-3a95efefccb0"

# Test 1: Direct version check
print("1. Testing version endpoint...")
try:
    version_response = requests.get(f"{primary_url}/api/v2/version", timeout=30)
    print(f"   Version: {version_response.status_code}")
    if version_response.status_code == 200:
        print(f"   Response: {version_response.text}")
except Exception as e:
    print(f"   Error: {e}")

# Test 2: Get collections
print(f"\n2. Testing collections endpoint...")
try:
    collections_response = requests.get(f"{primary_url}/api/v2/tenants/default_tenant/databases/default_database/collections", timeout=30)
    print(f"   Collections: {collections_response.status_code}")
    if collections_response.status_code == 200:
        collections = collections_response.json()
        print(f"   Found {len(collections)} collections")
        global_collection = next((c for c in collections if c['name'] == 'global'), None)
        if global_collection:
            print(f"   Global collection: {global_collection['id']}")
        else:
            print("   No global collection found")
except Exception as e:
    print(f"   Error: {e}")

# Test 3: Simple add request (like ChromaDB expects)
print(f"\n3. Testing direct add to primary...")
try:
    # Test with exact format that worked before
    payload = {
        "embeddings": [[0.1, 0.2, 0.3]],
        "documents": ["Direct test"],
        "metadatas": [{"test": "direct_primary"}],
        "ids": ["direct_test_001"]
    }
    
    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json"
    }
    
    print(f"   Payload: {json.dumps(payload)}")
    print(f"   Headers: {headers}")
    
    response = requests.post(
        f"{primary_url}/api/v2/tenants/default_tenant/databases/default_database/collections/{global_id}/add",
        headers=headers,
        json=payload,
        timeout=30
    )
    
    print(f"   Direct add: {response.status_code}")
    if response.status_code != 200:
        print(f"   Error response: {response.text[:300]}")
    else:
        print(f"   Success: {response.text}")
        
except Exception as e:
    print(f"   Error: {e}")

# Test 4: Check what the load balancer is actually sending
print(f"\n4. Testing via load balancer with debug...")
try:
    lb_url = "https://chroma-load-balancer.onrender.com"
    
    payload = {
        "embeddings": [[0.1, 0.2, 0.3]],
        "documents": ["LB test"],
        "metadatas": [{"test": "lb_debug"}],
        "ids": ["lb_test_001"]
    }
    
    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json"
    }
    
    response = requests.post(
        f"{lb_url}/api/v2/tenants/default_tenant/databases/default_database/collections/{global_id}/add",
        headers=headers,
        json=payload,
        timeout=30
    )
    
    print(f"   Load balancer: {response.status_code}")
    print(f"   Response: {response.text[:300]}")
    
except Exception as e:
    print(f"   Error: {e}")

print(f"\n{'='*50}")
print("�� Debug completed!") 