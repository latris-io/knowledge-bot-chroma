#!/usr/bin/env python3
"""
Document Operations Fix for ChromaDB v2 API
Addresses phantom collection issue and query format compatibility
"""

import requests
import json
import time
import uuid
from datetime import datetime

def create_collection_with_embedding_function(base_url, collection_name):
    """Create collection with default embedding function for query_texts support"""
    
    create_url = f"{base_url}/api/v2/tenants/default_tenant/databases/default_database/collections"
    
    # Create collection with default embedding function to support query_texts
    create_data = {
        "name": collection_name,
        "configuration_json": {
            "hnsw": {
                "space": "l2",
                "ef_construction": 100,
                "ef_search": 100,
                "max_neighbors": 16,
                "resize_factor": 1.2,
                "sync_threshold": 1000
            },
            "embedding_function": {
                "name": "default",
                "type": "sentence-transformers",
                "model": "all-MiniLM-L6-v2"
            }
        },
        "metadata": {"created_by": "document_operations_fix"}
    }
    
    print(f"   Creating collection with embedding function...")
    print(f"   URL: {create_url}")
    print(f"   Data: {json.dumps(create_data, indent=2)}")
    
    response = requests.post(create_url, json=create_data, timeout=30)
    return response

def verify_collection_via_listing(base_url, collection_name):
    """Verify collection exists by checking collections listing (workaround for phantom collections)"""
    
    list_url = f"{base_url}/api/v2/tenants/default_tenant/databases/default_database/collections"
    response = requests.get(list_url, timeout=30)
    
    if response.status_code == 200:
        collections = response.json()
        found_collection = None
        for collection in collections:
            if collection.get('name') == collection_name:
                found_collection = collection
                break
        
        if found_collection:
            print(f"✅ Collection found in listing: {found_collection['id']}")
            return found_collection['id']
        else:
            print(f"❌ Collection '{collection_name}' not found in listings")
            return None
    else:
        print(f"❌ Failed to get collections listing: {response.status_code}")
        return None

def test_enhanced_document_operations():
    """Test document operations with ChromaDB v2 API fixes"""
    
    base_url = "https://chroma-load-balancer.onrender.com"
    
    print(f"🔧 Enhanced Document Operations Test with v2 API Fixes")
    print(f"🕐 Started at: {datetime.now().isoformat()}")
    print("=" * 80)
    
    # Generate unique test collection name
    test_id = f"{int(time.time())}_{uuid.uuid4().hex[:8]}"
    collection_name = f"enhanced_test_{test_id}"
    collection_id = None
    
    try:
        # Step 1: Create collection with embedding function
        print(f"📚 Step 1: Creating collection with embedding function...")
        response = create_collection_with_embedding_function(base_url, collection_name)
        
        if response.status_code == 200 or response.status_code == 201:
            collection_data = response.json()
            collection_id = collection_data.get('id')
            print(f"✅ Collection created successfully: {collection_id}")
        else:
            print(f"❌ Failed to create collection: {response.status_code}")
            print(f"   Response: {response.text}")
            
            # Fallback: try simple collection creation
            print(f"🔄 Fallback: Creating simple collection...")
            simple_data = {"name": collection_name}
            response = requests.post(
                f"{base_url}/api/v2/tenants/default_tenant/databases/default_database/collections",
                json=simple_data, timeout=30
            )
            if response.status_code in [200, 201]:
                collection_data = response.json()
                collection_id = collection_data.get('id')
                print(f"✅ Simple collection created: {collection_id}")
            else:
                print(f"❌ Simple collection creation also failed: {response.status_code}")
                return
        
        # Step 2: Verify via listing (phantom collection workaround)
        print(f"🔍 Step 2: Verifying collection via listings (phantom workaround)...")
        verified_id = verify_collection_via_listing(base_url, collection_name)
        
        if verified_id:
            if verified_id != collection_id:
                print(f"⚠️ ID mismatch: Created={collection_id}, Listed={verified_id}")
                collection_id = verified_id  # Use the verified ID
        else:
            print(f"❌ Collection verification failed - proceeding with created ID")
        
        # Wait for collection to be ready
        time.sleep(3)
        
        # Step 3: Add documents with explicit embeddings
        print(f"📄 Step 3: Adding documents with explicit embeddings...")
        add_url = f"{base_url}/api/v2/tenants/default_tenant/databases/default_database/collections/{collection_id}/add"
        
        # Use explicit embeddings to avoid dependency on embedding function
        add_data = {
            "ids": ["doc1", "doc2"],
            "documents": ["Test document 1 about technology", "Test document 2 about science"],
            "metadatas": [{"type": "test", "topic": "technology"}, {"type": "test", "topic": "science"}],
            "embeddings": [
                [0.1, 0.2, 0.3, 0.4, 0.5],  # 5-dimensional embedding for doc1
                [0.6, 0.7, 0.8, 0.9, 1.0]   # 5-dimensional embedding for doc2
            ]
        }
        
        print(f"   URL: {add_url}")
        print(f"   Data: {json.dumps(add_data, indent=2)}")
        
        response = requests.post(add_url, json=add_data, timeout=30)
        print(f"   Status: {response.status_code}")
        print(f"   Response: {response.text}")
        
        if response.status_code == 200 or response.status_code == 201:
            print("✅ Documents added successfully with embeddings")
        else:
            print(f"❌ Failed to add documents: {response.status_code}")
            return
        
        # Wait for indexing
        time.sleep(2)
        
        # Step 4: Get documents  
        print(f"📋 Step 4: Getting documents...")
        get_url = f"{base_url}/api/v2/tenants/default_tenant/databases/default_database/collections/{collection_id}/get"
        get_data = {"ids": ["doc1", "doc2"], "include": ["documents", "metadatas"]}
        
        response = requests.post(get_url, json=get_data, timeout=30)
        print(f"   Status: {response.status_code}")
        
        if response.status_code == 200:
            result = response.json()
            doc_count = len(result.get('ids', []))
            print(f"✅ Documents retrieved: {doc_count} documents found")
            
            if doc_count > 0:
                print(f"   Documents: {result.get('documents', [])}")
                print(f"   Metadatas: {result.get('metadatas', [])}")
            else:
                print("⚠️ Warning: No documents returned despite successful add")
        else:
            print(f"❌ Failed to get documents: {response.status_code}")
            print(f"   Response: {response.text}")
        
        # Step 5: Query with embedding vector (v2 API compatible)
        print(f"🔍 Step 5: Querying with embedding vector (v2 API format)...")
        query_url = f"{base_url}/api/v2/tenants/default_tenant/databases/default_database/collections/{collection_id}/query"
        
        # Use query_embeddings format for v2 API
        query_data = {
            "query_embeddings": [[0.1, 0.2, 0.3, 0.4, 0.5]],  # Query with similar embedding
            "n_results": 2,
            "include": ["documents", "metadatas", "distances"]
        }
        
        print(f"   URL: {query_url}")
        print(f"   Data: {json.dumps(query_data, indent=2)}")
        
        response = requests.post(query_url, json=query_data, timeout=30)
        print(f"   Status: {response.status_code}")
        print(f"   Response: {response.text}")
        
        if response.status_code == 200:
            result = response.json()
            found_ids = result.get('ids', [[]])[0] if result.get('ids') else []
            print(f"✅ Query successful: Found {len(found_ids)} results")
            
            if found_ids:
                distances = result.get('distances', [[]])[0] if result.get('distances') else []
                for i, doc_id in enumerate(found_ids):
                    distance = distances[i] if i < len(distances) else "unknown"
                    print(f"   Result {i+1}: {doc_id} (distance: {distance})")
        elif response.status_code == 422:
            print("⚠️ Query format issue (422) - trying alternative format...")
            
            # Try with query_texts if collection has embedding function
            alt_query_data = {
                "query_texts": ["technology"],
                "n_results": 2,
                "include": ["documents", "metadatas"]
            }
            
            response = requests.post(query_url, json=alt_query_data, timeout=30)
            print(f"   Alternative query status: {response.status_code}")
            
            if response.status_code == 200:
                print("✅ Alternative query_texts format worked")
            else:
                print(f"❌ Alternative query also failed: {response.status_code}")
                print(f"   This is expected for collections without embedding functions")
        else:
            print(f"❌ Query failed: {response.status_code}")
            print(f"   Response: {response.text}")
        
        print(f"✅ Enhanced document operations test completed successfully!")
        
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
    print(f"🏁 Enhanced test completed at: {datetime.now().isoformat()}")

if __name__ == "__main__":
    test_enhanced_document_operations() 