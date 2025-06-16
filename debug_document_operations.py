#!/usr/bin/env python3
"""
Debug Document Operations Test
=============================
Focused test for document operations with detailed debugging
"""

import requests
import json
import time
import uuid
import logging

# Set up detailed logging
logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def debug_document_operations():
    """Test document operations with detailed debugging"""
    base_url = "https://chroma-load-balancer.onrender.com"
    
    print("🔬 DEBUG: Document Operations Test")
    print("=" * 50)
    
    # Create a test collection first
    collection_name = f"DEBUG_docs_{int(time.time())}_{uuid.uuid4().hex[:8]}"
    print(f"📦 Creating test collection: {collection_name}")
    
    try:
        # Step 1: Create collection
        collection_payload = {
            "name": collection_name,
            "metadata": {"test_type": "document_debug", "safe_to_delete": True},
            "configuration": {
                "hnsw": {
                    "space": "l2",
                    "ef_construction": 100,
                    "ef_search": 100,
                    "max_neighbors": 16
                }
            }
        }
        
        create_response = requests.post(
            f"{base_url}/api/v2/tenants/default_tenant/databases/default_database/collections",
            headers={"Content-Type": "application/json"},
            json=collection_payload,
            timeout=30
        )
        
        print(f"📋 Collection creation status: {create_response.status_code}")
        if create_response.status_code not in [200, 201]:
            print(f"❌ Collection creation failed: {create_response.text}")
            return
        
        collection_data = create_response.json()
        collection_id = collection_data.get('id')
        print(f"✅ Collection created: {collection_id}")
        
        # Step 2: Test document addition with debugging
        print(f"\n📄 Testing document addition...")
        
        doc_payload = {
            "documents": ["Test document 1", "Test document 2"],
            "metadatas": [{"test": True, "index": 1}, {"test": True, "index": 2}],
            "ids": [f"test_doc_1_{uuid.uuid4().hex[:8]}", f"test_doc_2_{uuid.uuid4().hex[:8]}"]
        }
        
        print(f"🔍 Request payload: {json.dumps(doc_payload, indent=2)}")
        
        add_url = f"{base_url}/api/v2/tenants/default_tenant/databases/default_database/collections/{collection_id}/add"
        print(f"🌐 Request URL: {add_url}")
        
        # Make request with detailed error handling
        try:
            add_response = requests.post(
                add_url,
                headers={"Content-Type": "application/json"},
                json=doc_payload,
                timeout=30
            )
            
            print(f"📊 Response status: {add_response.status_code}")
            print(f"📋 Response headers: {dict(add_response.headers)}")
            
            # FIXED: Handle both 200 and 201 status codes for success
            if add_response.status_code in [200, 201]:
                print(f"✅ Document addition successful! (Status: {add_response.status_code})")
                
                # Check if response has content
                if add_response.content:
                    try:
                        response_data = add_response.json()
                        print(f"📄 Response data: {json.dumps(response_data, indent=2)}")
                    except:
                        print(f"📄 Response content (raw): {add_response.content}")
                else:
                    print(f"⚠️ Empty response body (this might be normal for some ChromaDB operations)")
                
                # Step 3: Test document retrieval
                print(f"\n📖 Testing document retrieval...")
                
                get_payload = {
                    "ids": doc_payload["ids"],
                    "include": ["documents", "metadatas"]
                }
                
                get_url = f"{base_url}/api/v2/tenants/default_tenant/databases/default_database/collections/{collection_id}/get"
                print(f"🌐 Get URL: {get_url}")
                print(f"🔍 Get payload: {json.dumps(get_payload, indent=2)}")
                
                get_response = requests.post(
                    get_url,
                    headers={"Content-Type": "application/json"},
                    json=get_payload,
                    timeout=30
                )
                
                print(f"📊 Get response status: {get_response.status_code}")
                print(f"📋 Get response headers: {dict(get_response.headers)}")
                
                if get_response.status_code == 200:
                    print(f"✅ Document retrieval successful!")
                    get_data = get_response.json()
                    print(f"📄 Retrieved data: {json.dumps(get_data, indent=2)}")
                    
                    # Step 4: Test document query
                    print(f"\n🔍 Testing document query...")
                    
                    query_payload = {
                        "query_texts": ["Test document"],
                        "n_results": 2,
                        "include": ["documents", "metadatas", "distances"]
                    }
                    
                    query_url = f"{base_url}/api/v2/tenants/default_tenant/databases/default_database/collections/{collection_id}/query"
                    print(f"🌐 Query URL: {query_url}")
                    print(f"🔍 Query payload: {json.dumps(query_payload, indent=2)}")
                    
                    query_response = requests.post(
                        query_url,
                        headers={"Content-Type": "application/json"},
                        json=query_payload,
                        timeout=30
                    )
                    
                    print(f"📊 Query response status: {query_response.status_code}")
                    print(f"📋 Query response headers: {dict(query_response.headers)}")
                    
                    if query_response.status_code == 200:
                        print(f"✅ Document query successful!")
                        query_data = query_response.json()
                        print(f"📄 Query results: {json.dumps(query_data, indent=2)}")
                    else:
                        print(f"❌ Document query failed: {query_response.text}")
                        
                else:
                    print(f"❌ Document retrieval failed: {get_response.text}")
                    
            else:
                print(f"❌ Document addition failed!")
                print(f"📄 Error response: {add_response.text}")
                print(f"📄 Response content: {add_response.content}")
                
                # Try to get more debugging info
                if add_response.headers.get('content-type', '').startswith('application/json'):
                    try:
                        error_data = add_response.json()
                        print(f"🔍 Error JSON: {json.dumps(error_data, indent=2)}")
                    except:
                        print(f"🔍 Could not parse error JSON")
                        
        except requests.exceptions.Timeout:
            print(f"⏰ Request timed out after 30 seconds")
        except requests.exceptions.ConnectionError as e:
            print(f"🔌 Connection error: {e}")
        except Exception as e:
            print(f"❌ Unexpected error: {e}")
            
    except Exception as e:
        print(f"❌ Test setup failed: {e}")
        
    finally:
        # Cleanup
        try:
            print(f"\n🧹 Cleaning up test collection...")
            delete_response = requests.delete(
                f"{base_url}/api/v2/tenants/default_tenant/databases/default_database/collections/{collection_name}",
                timeout=30
            )
            print(f"🗑️ Cleanup status: {delete_response.status_code}")
        except:
            print(f"⚠️ Cleanup failed (collection may need manual deletion)")

if __name__ == "__main__":
    debug_document_operations() 