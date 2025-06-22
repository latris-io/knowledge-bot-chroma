#!/usr/bin/env python3
"""
REAL-WORLD DELETE TEST
Testing the actual CMS scenario: documents grouped by document_id, delete by metadata filter
"""

import requests
import time
import json

def test_real_world_delete(base_url="https://chroma-load-balancer.onrender.com"):
    """Test real-world DELETE scenario with document_id metadata"""
    
    print("🌍 REAL-WORLD DELETE TEST: CMS Document Management")
    print("="*70)
    
    # Step 1: Create test collection
    collection_name = f"REAL_DELETE_TEST_{int(time.time())}"
    print(f"\n📝 STEP 1: Creating collection: {collection_name}")
    
    create_response = requests.post(
        f"{base_url}/api/v2/tenants/default_tenant/databases/default_database/collections",
        headers={"Content-Type": "application/json"},
        json={"name": collection_name},
        timeout=30
    )
    
    print(f"   Create response: {create_response.status_code}")
    if create_response.status_code not in [200, 201]:
        print(f"   ❌ FAILED: {create_response.text}")
        return
    
    time.sleep(5)  # Wait for mapping
    
    # Step 2: Add first set of documents (document_id: "doc123")
    print(f"\n📄 STEP 2: Adding 4 documents for document_id='doc123'")
    
    doc123_ids = [f"chunk_{i}_doc123_{int(time.time())}" for i in range(4)]
    doc123_documents = {
        "ids": doc123_ids,
        "documents": [
            "First document chunk 1: Introduction to the topic",
            "First document chunk 2: Main content and analysis", 
            "First document chunk 3: Supporting evidence and examples",
            "First document chunk 4: Conclusion and summary"
        ],
        "metadatas": [
            {"document_id": "doc123", "chunk": 1, "type": "introduction"},
            {"document_id": "doc123", "chunk": 2, "type": "content"},
            {"document_id": "doc123", "chunk": 3, "type": "evidence"},
            {"document_id": "doc123", "chunk": 4, "type": "conclusion"}
        ],
        "embeddings": [
            [0.1, 0.1, 0.1, 0.1, 0.1],
            [0.2, 0.2, 0.2, 0.2, 0.2],
            [0.3, 0.3, 0.3, 0.3, 0.3],
            [0.4, 0.4, 0.4, 0.4, 0.4]
        ]
    }
    
    add_doc123_response = requests.post(
        f"{base_url}/api/v2/tenants/default_tenant/databases/default_database/collections/{collection_name}/add",
        headers={"Content-Type": "application/json"},
        json=doc123_documents,
        timeout=30
    )
    
    print(f"   Add doc123 response: {add_doc123_response.status_code}")
    if add_doc123_response.status_code not in [200, 201]:
        print(f"   ❌ FAILED: {add_doc123_response.text}")
        return
        
    print(f"   ✅ Added 4 chunks for document_id='doc123'")
    
    # Step 3: Add second set of documents (document_id: "doc456")
    print(f"\n📄 STEP 3: Adding 4 documents for document_id='doc456'")
    
    doc456_ids = [f"chunk_{i}_doc456_{int(time.time())}" for i in range(4)]
    doc456_documents = {
        "ids": doc456_ids,
        "documents": [
            "Second document chunk 1: Different topic introduction",
            "Second document chunk 2: Alternative analysis approach", 
            "Second document chunk 3: Contrasting evidence and data",
            "Second document chunk 4: Different conclusions reached"
        ],
        "metadatas": [
            {"document_id": "doc456", "chunk": 1, "type": "introduction"},
            {"document_id": "doc456", "chunk": 2, "type": "content"},
            {"document_id": "doc456", "chunk": 3, "type": "evidence"},
            {"document_id": "doc456", "chunk": 4, "type": "conclusion"}
        ],
        "embeddings": [
            [0.5, 0.5, 0.5, 0.5, 0.5],
            [0.6, 0.6, 0.6, 0.6, 0.6],
            [0.7, 0.7, 0.7, 0.7, 0.7],
            [0.8, 0.8, 0.8, 0.8, 0.8]
        ]
    }
    
    add_doc456_response = requests.post(
        f"{base_url}/api/v2/tenants/default_tenant/databases/default_database/collections/{collection_name}/add",
        headers={"Content-Type": "application/json"},
        json=doc456_documents,
        timeout=30
    )
    
    print(f"   Add doc456 response: {add_doc456_response.status_code}")
    if add_doc456_response.status_code not in [200, 201]:
        print(f"   ❌ FAILED: {add_doc456_response.text}")
        return
        
    print(f"   ✅ Added 4 chunks for document_id='doc456'")
    
    # Step 4: Verify initial state
    print(f"\n⏳ STEP 4: Waiting 30 seconds for sync, then checking initial state...")
    time.sleep(30)
    
    # Check total documents via load balancer
    lb_get_initial = requests.post(
        f"{base_url}/api/v2/tenants/default_tenant/databases/default_database/collections/{collection_name}/get",
        headers={"Content-Type": "application/json"},
        json={"include": ["documents", "metadatas"]},
        timeout=15
    )
    
    if lb_get_initial.status_code == 200:
        lb_result_initial = lb_get_initial.json()
        total_docs = len(lb_result_initial.get('ids', []))
        metadatas = lb_result_initial.get('metadatas', [])
        
        # Count by document_id
        doc123_count = sum(1 for meta in metadatas if meta.get('document_id') == 'doc123')
        doc456_count = sum(1 for meta in metadatas if meta.get('document_id') == 'doc456')
        
        print(f"   📊 Initial state via Load Balancer:")
        print(f"      Total documents: {total_docs}")
        print(f"      Documents with document_id='doc123': {doc123_count}")
        print(f"      Documents with document_id='doc456': {doc456_count}")
        
        if total_docs != 8:
            print(f"   ⚠️  WARNING: Expected 8 total documents, got {total_docs}")
        if doc123_count != 4:
            print(f"   ⚠️  WARNING: Expected 4 doc123 documents, got {doc123_count}")
        if doc456_count != 4:
            print(f"   ⚠️  WARNING: Expected 4 doc456 documents, got {doc456_count}")
    else:
        print(f"   ❌ Initial state check failed: {lb_get_initial.status_code}")
        return
    
    # Step 5: Delete documents by document_id="doc123"
    print(f"\n🗑️  STEP 5: Deleting all documents with document_id='doc123'")
    
    # First, let's check what DELETE endpoints are available
    print(f"   🔍 Attempting metadata-based deletion...")
    
    # Method 1: Try deletion by metadata filter (if supported)
    delete_by_metadata_response = requests.post(
        f"{base_url}/api/v2/tenants/default_tenant/databases/default_database/collections/{collection_name}/delete",
        headers={"Content-Type": "application/json"},
        json={"where": {"document_id": "doc123"}},
        timeout=30
    )
    
    print(f"   DELETE by metadata response: {delete_by_metadata_response.status_code}")
    
    if delete_by_metadata_response.status_code in [200, 201]:
        try:
            delete_result = delete_by_metadata_response.json()
            print(f"   DELETE result: {json.dumps(delete_result, indent=2)}")
        except:
            print(f"   DELETE result: {delete_by_metadata_response.text}")
        deletion_method = "metadata_filter"
    else:
        print(f"   ❌ Metadata deletion failed: {delete_by_metadata_response.text}")
        
        # Method 2: Fallback to deletion by specific IDs
        print(f"   🔄 Fallback: Deleting by specific document IDs...")
        
        delete_by_ids_response = requests.post(
            f"{base_url}/api/v2/tenants/default_tenant/databases/default_database/collections/{collection_name}/delete",
            headers={"Content-Type": "application/json"},
            json={"ids": doc123_ids},
            timeout=30
        )
        
        print(f"   DELETE by IDs response: {delete_by_ids_response.status_code}")
        
        if delete_by_ids_response.status_code in [200, 201]:
            try:
                delete_result = delete_by_ids_response.json()
                print(f"   DELETE result: {json.dumps(delete_result, indent=2)}")
            except:
                print(f"   DELETE result: {delete_by_ids_response.text}")
            deletion_method = "specific_ids"
        else:
            print(f"   ❌ ID-based deletion also failed: {delete_by_ids_response.text}")
            return
    
    # Step 6: Immediate post-delete check
    print(f"\n🔍 STEP 6: Immediate post-delete state (before sync)")
    
    lb_get_immediate = requests.post(
        f"{base_url}/api/v2/tenants/default_tenant/databases/default_database/collections/{collection_name}/get",
        headers={"Content-Type": "application/json"},
        json={"include": ["documents", "metadatas"]},
        timeout=15
    )
    
    if lb_get_immediate.status_code == 200:
        lb_result_immediate = lb_get_immediate.json()
        immediate_total = len(lb_result_immediate.get('ids', []))
        immediate_metadatas = lb_result_immediate.get('metadatas', [])
        
        # Count remaining documents by document_id
        immediate_doc123_count = sum(1 for meta in immediate_metadatas if meta.get('document_id') == 'doc123')
        immediate_doc456_count = sum(1 for meta in immediate_metadatas if meta.get('document_id') == 'doc456')
        
        print(f"   📊 Immediate state via Load Balancer:")
        print(f"      Total documents: {immediate_total}")
        print(f"      Documents with document_id='doc123': {immediate_doc123_count}")
        print(f"      Documents with document_id='doc456': {immediate_doc456_count}")
        
        if immediate_doc123_count == 0:
            print(f"   ✅ doc123 documents successfully deleted from load balancer")
        else:
            print(f"   ⚠️  WARNING: {immediate_doc123_count} doc123 documents still in load balancer")
            
        if immediate_doc456_count == 4:
            print(f"   ✅ doc456 documents preserved in load balancer")
        else:
            print(f"   ⚠️  WARNING: Only {immediate_doc456_count}/4 doc456 documents in load balancer")
    
    # Step 7: Wait for sync and final verification
    print(f"\n⏳ STEP 7: Waiting 60 seconds for DELETE sync...")
    time.sleep(60)
    
    print(f"   🔍 Final verification:")
    
    # Final state check via load balancer
    lb_get_final = requests.post(
        f"{base_url}/api/v2/tenants/default_tenant/databases/default_database/collections/{collection_name}/get",
        headers={"Content-Type": "application/json"},
        json={"include": ["documents", "metadatas"]},
        timeout=15
    )
    
    final_total = 0
    final_doc123_count = 0
    final_doc456_count = 0
    
    if lb_get_final.status_code == 200:
        lb_result_final = lb_get_final.json()
        final_total = len(lb_result_final.get('ids', []))
        final_metadatas = lb_result_final.get('metadatas', [])
        
        # Count final documents by document_id
        final_doc123_count = sum(1 for meta in final_metadatas if meta.get('document_id') == 'doc123')
        final_doc456_count = sum(1 for meta in final_metadatas if meta.get('document_id') == 'doc456')
        
        print(f"   📊 Final state via Load Balancer:")
        print(f"      Total documents: {final_total}")
        print(f"      Documents with document_id='doc123': {final_doc123_count}")
        print(f"      Documents with document_id='doc456': {final_doc456_count}")
    
    # Step 8: Analysis
    print(f"\n📊 REAL-WORLD DELETE TEST ANALYSIS:")
    print(f"   Expected final state: 0 doc123 documents, 4 doc456 documents")
    print(f"   Actual final state: {final_doc123_count} doc123, {final_doc456_count} doc456")
    
    if final_doc123_count == 0 and final_doc456_count == 4:
        print(f"\n✅ SUCCESS: Real-world DELETE functionality working correctly!")
        print(f"   - Document group deletion: ✅ (doc123 completely removed)")
        print(f"   - Selective preservation: ✅ (doc456 preserved)")
        print(f"   - Deletion method used: {deletion_method}")
    elif final_doc123_count > 0:
        print(f"\n❌ PARTIAL FAILURE: {final_doc123_count} doc123 documents still exist")
        print(f"   - Deletion method: {deletion_method}")
        print(f"   - Possible issue: DELETE operation not properly targeting document_id group")
    elif final_doc456_count != 4:
        print(f"\n❌ FAILURE: Wrong number of doc456 documents ({final_doc456_count}/4)")
        print(f"   - Possible issue: DELETE operation affected wrong documents")
    else:
        print(f"\n❌ UNKNOWN ISSUE: Unexpected final state")
    
    # Cleanup
    print(f"\n🧹 Cleaning up test collection...")
    cleanup_response = requests.delete(
        f"{base_url}/api/v2/tenants/default_tenant/databases/default_database/collections/{collection_name}",
        timeout=30
    )
    print(f"   Cleanup response: {cleanup_response.status_code}")

if __name__ == "__main__":
    test_real_world_delete() 