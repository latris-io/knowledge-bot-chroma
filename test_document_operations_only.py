#!/usr/bin/env python3
"""
Focused Document Operations Test for ChromaDB
Tests only document-level operations to isolate 503 errors
"""

import requests
import json
import time
import uuid
from datetime import datetime

def test_document_operations(base_url="https://chroma-load-balancer.onrender.com"):
    """Test document operations specifically"""
    
    print(f"🧪 Testing Document Operations on {base_url}")
    print(f"🕐 Started at: {datetime.now().isoformat()}")
    print("=" * 80)
    
    # Generate unique test collection name
    test_id = f"{int(time.time())}_{uuid.uuid4().hex[:8]}"
    collection_name = f"doc_test_{test_id}"
    
    try:
        # Step 1: Create test collection
        print(f"📚 Step 1: Creating test collection '{collection_name}'...")
        create_url = f"{base_url}/api/v2/tenants/default_tenant/databases/default_database/collections"
        create_data = {"name": collection_name}
        
        response = requests.post(create_url, json=create_data, timeout=30)
        if response.status_code == 200 or response.status_code == 201:
            collection_data = response.json()
            collection_id = collection_data.get('id')
            print(f"✅ Collection created successfully: {collection_id}")
        else:
            print(f"❌ Failed to create collection: {response.status_code}")
            print(f"   Response: {response.text}")
            return
        
        # Step 1.5: Verify collection exists immediately after creation
        print(f"🔍 Step 1.5: Verifying collection exists after creation...")
        verify_url = f"{base_url}/api/v2/tenants/default_tenant/databases/default_database/collections/{collection_id}"
        response = requests.get(verify_url, timeout=30)
        print(f"   Status: {response.status_code}")
        if response.status_code == 200:
            print("✅ Collection verified immediately after creation")
        else:
            print(f"❌ PHANTOM COLLECTION DETECTED: Collection disappeared immediately!")
            print(f"   Response: {response.text}")
        
        # Wait a moment for collection to be ready
        time.sleep(5)
        
        # Step 1.6: Re-verify collection exists after wait
        print(f"🔍 Step 1.6: Re-verifying collection exists after 5s wait...")
        response = requests.get(verify_url, timeout=30)
        print(f"   Status: {response.status_code}")
        if response.status_code == 200:
            print("✅ Collection still exists after wait")
        else:
            print(f"❌ PHANTOM COLLECTION: Collection disappeared after wait!")
            print(f"   Response: {response.text}")
        
        # Step 2: Add documents
        print(f"📄 Step 2: Adding test documents to collection...")
        add_url = f"{base_url}/api/v2/tenants/default_tenant/databases/default_database/collections/{collection_id}/add"
        add_data = {
            "ids": ["doc1", "doc2"],
            "documents": ["Test document 1", "Test document 2"],
            "metadatas": [{"type": "test"}, {"type": "test"}]
        }
        
        print(f"   URL: {add_url}")
        print(f"   Data: {json.dumps(add_data, indent=2)}")
        
        response = requests.post(add_url, json=add_data, timeout=30)
        print(f"   Status: {response.status_code}")
        print(f"   Response: {response.text}")
        
        if response.status_code == 200 or response.status_code == 201:
            print("✅ Documents added successfully")
        else:
            print(f"❌ Failed to add documents: {response.status_code}")
            return
        
        # Step 2.5: Verify collection still exists after document add
        print(f"🔍 Step 2.5: Verifying collection exists after document add...")
        response = requests.get(verify_url, timeout=30)
        print(f"   Status: {response.status_code}")
        if response.status_code == 200:
            print("✅ Collection still exists after document add")
        else:
            print(f"❌ PHANTOM COLLECTION: Collection disappeared after document add!")
            print(f"   Response: {response.text}")
            return
        
        # Wait for potential sync
        time.sleep(3)
        
        # Step 3: Get documents
        print(f"📋 Step 3: Getting documents from collection...")
        get_url = f"{base_url}/api/v2/tenants/default_tenant/databases/default_database/collections/{collection_id}/get"
        get_data = {"ids": ["doc1", "doc2"]}
        
        print(f"   URL: {get_url}")
        print(f"   Data: {json.dumps(get_data, indent=2)}")
        
        response = requests.post(get_url, json=get_data, timeout=30)
        print(f"   Status: {response.status_code}")
        print(f"   Response: {response.text}")
        
        if response.status_code == 200:
            result = response.json()
            doc_count = len(result.get('ids', []))
            print(f"✅ Documents retrieved successfully: {doc_count} documents found")
            if doc_count == 0:
                print("⚠️ Warning: No documents returned despite successful add operation")
        else:
            print(f"❌ Failed to get documents: {response.status_code}")
        
        # Step 4: Query documents (using proper v2 API format)
        print(f"🔍 Step 4: Attempting to get collection for query...")
        
        # First, let's try to get the collection info to see embedding function
        response = requests.get(verify_url, timeout=30)
        if response.status_code != 200:
            print(f"❌ Cannot query: Collection not found for query operation")
            return
            
        print(f"🔍 Step 4: Querying documents in collection...")
        query_url = f"{base_url}/api/v2/tenants/default_tenant/databases/default_database/collections/{collection_id}/query"
        
        # For ChromaDB v2 API, we need to use query_embeddings or provide an embedding function
        # Let's try a simple approach first - query without embeddings to test the collection
        query_data = {
            "query_texts": ["Test document"],  # This should work if collection has embedding function
            "n_results": 2,
            "include": ["documents", "metadatas"]
        }
        
        print(f"   URL: {query_url}")
        print(f"   Data: {json.dumps(query_data, indent=2)}")
        
        response = requests.post(query_url, json=query_data, timeout=30)
        print(f"   Status: {response.status_code}")
        print(f"   Response: {response.text}")
        
        if response.status_code == 200:
            print("✅ Query executed successfully")
        elif response.status_code == 422:
            print("⚠️ Query format issue (422) - ChromaDB v2 API requires different format")
            print("   This is expected and will be fixed in the load balancer")
        else:
            print(f"❌ Failed to query documents: {response.status_code}")
        
    finally:
        # Cleanup: Delete test collection
        print(f"🧹 Cleanup: Deleting test collection...")
        try:
            delete_url = f"{base_url}/api/v2/tenants/default_tenant/databases/default_database/collections/{collection_name}"
            response = requests.delete(delete_url, timeout=30)
            if response.status_code == 200:
                print("✅ Test collection deleted successfully")
            else:
                print(f"⚠️ Failed to delete test collection: {response.status_code}")
        except Exception as e:
            print(f"⚠️ Cleanup error: {e}")
    
    print("=" * 80)
    print(f"🏁 Document operations test completed at: {datetime.now().isoformat()}")

if __name__ == "__main__":
    test_document_operations() 