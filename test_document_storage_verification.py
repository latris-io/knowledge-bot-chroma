#!/usr/bin/env python3
"""
Document Storage Verification Test
Tests that documents can actually be stored and retrieved properly.
"""

import requests
import json
import time
import sys
import argparse
from datetime import datetime

class DocumentStorageVerifier:
    def __init__(self, base_url):
        self.base_url = base_url.rstrip('/')
        self.test_collections = []
        
    def test_document_storage_cycle(self):
        """Test complete document storage and retrieval cycle"""
        print("🔍 TESTING: Complete Document Storage and Retrieval Cycle")
        
        # Step 1: Create test collection
        timestamp = int(time.time())
        collection_name = f"DOC_STORAGE_TEST_{timestamp}"
        
        print(f"   Creating collection: {collection_name}")
        create_response = requests.post(
            f"{self.base_url}/api/v2/tenants/default_tenant/databases/default_database/collections",
            headers={"Content-Type": "application/json"},
            json={"name": collection_name}
        )
        
        if create_response.status_code != 200:
            print(f"   ❌ Collection creation failed: {create_response.status_code}")
            return False
            
        collection_id = create_response.json()["id"]
        self.test_collections.append(collection_name)
        print(f"   ✅ Collection created with ID: {collection_id}")
        
        # Step 2: Add documents with proper structure
        test_documents = [
            "This is a test document about machine learning",
            "Another test document about artificial intelligence", 
            "A third document about data science and analytics"
        ]
        
        test_ids = ["doc_1", "doc_2", "doc_3"]
        test_metadatas = [
            {"topic": "ml", "type": "test", "timestamp": timestamp},
            {"topic": "ai", "type": "test", "timestamp": timestamp},
            {"topic": "data", "type": "test", "timestamp": timestamp}
        ]
        
        print(f"   Adding {len(test_documents)} documents...")
        # Include embeddings (required for proper ChromaDB storage)
        test_embeddings = [
            [0.1, 0.2, 0.3, 0.4, 0.5],
            [0.2, 0.3, 0.4, 0.5, 0.6], 
            [0.3, 0.4, 0.5, 0.6, 0.7]
        ]
        
        add_response = requests.post(
            f"{self.base_url}/api/v2/tenants/default_tenant/databases/default_database/collections/{collection_name}/add",
            headers={"Content-Type": "application/json"},
            json={
                "documents": test_documents,
                "ids": test_ids,
                "metadatas": test_metadatas,
                "embeddings": test_embeddings
            }
        )
        
        print(f"   Add response status: {add_response.status_code}")
        if add_response.status_code != 201:
            print(f"   ❌ Document add failed: {add_response.text}")
            return False
            
        print(f"   ✅ Documents added successfully")
        
        # Step 3: Wait a moment for indexing
        print("   Waiting 2 seconds for document indexing...")
        time.sleep(2)
        
        # Step 4: Verify documents can be retrieved
        print("   Retrieving all documents...")
        get_response = requests.post(
            f"{self.base_url}/api/v2/tenants/default_tenant/databases/default_database/collections/{collection_name}/get",
            headers={"Content-Type": "application/json"},
            json={"include": ["documents", "metadatas"]}
        )
        
        if get_response.status_code != 200:
            print(f"   ❌ Document retrieval failed: {get_response.status_code}")
            return False
            
        retrieved_data = get_response.json()
        retrieved_docs = retrieved_data.get("documents", [])
        retrieved_ids = retrieved_data.get("ids", [])
        
        print(f"   Retrieved {len(retrieved_docs)} documents")
        print(f"   Retrieved IDs: {retrieved_ids}")
        
        # Step 5: Verify document content
        if len(retrieved_docs) != len(test_documents):
            print(f"   ❌ Document count mismatch: expected {len(test_documents)}, got {len(retrieved_docs)}")
            return False
            
        for i, expected_doc in enumerate(test_documents):
            if i < len(retrieved_docs) and expected_doc == retrieved_docs[i]:
                print(f"   ✅ Document {i+1} matches expected content")
            else:
                print(f"   ❌ Document {i+1} content mismatch")
                print(f"       Expected: {expected_doc}")
                print(f"       Got: {retrieved_docs[i] if i < len(retrieved_docs) else 'MISSING'}")
                return False
        
        # Step 6: Test specific document retrieval by ID
        print("   Testing retrieval by specific IDs...")
        specific_get_response = requests.post(
            f"{self.base_url}/api/v2/tenants/default_tenant/databases/default_database/collections/{collection_name}/get",
            headers={"Content-Type": "application/json"},
            json={
                "ids": ["doc_1", "doc_3"],
                "include": ["documents", "metadatas"]
            }
        )
        
        if specific_get_response.status_code != 200:
            print(f"   ❌ Specific document retrieval failed: {specific_get_response.status_code}")
            return False
            
        specific_data = specific_get_response.json()
        specific_docs = specific_data.get("documents", [])
        specific_ids = specific_data.get("ids", [])
        
        if len(specific_docs) == 2 and "doc_1" in specific_ids and "doc_3" in specific_ids:
            print(f"   ✅ Specific document retrieval successful")
        else:
            print(f"   ❌ Specific document retrieval failed")
            print(f"       Expected 2 docs with IDs [doc_1, doc_3]")
            print(f"       Got {len(specific_docs)} docs with IDs {specific_ids}")
            return False
            
        print(f"   🎉 Complete document storage cycle SUCCESSFUL")
        return True
        
    def test_document_update_cycle(self):
        """Test document update and retrieval"""
        print("🔍 TESTING: Document Update and Retrieval Cycle")
        
        # Use existing collection if available
        if not self.test_collections:
            print("   ❌ No test collection available")
            return False
            
        collection_name = self.test_collections[0]
        
        # Update a document
        print("   Updating document with ID 'doc_2'...")
        update_response = requests.post(
            f"{self.base_url}/api/v2/tenants/default_tenant/databases/default_database/collections/{collection_name}/upsert",
            headers={"Content-Type": "application/json"},
            json={
                "documents": ["Updated document about machine learning and AI"],
                "ids": ["doc_2"],
                "metadatas": [{"topic": "ml_ai", "type": "updated_test", "updated": True}],
                "embeddings": [[0.25, 0.35, 0.45, 0.55, 0.65]]
            }
        )
        
        if update_response.status_code not in [200, 201]:
            print(f"   ❌ Document update failed: {update_response.status_code}")
            return False
            
        print("   ✅ Document updated successfully")
        
        # Verify update
        time.sleep(1)
        get_response = requests.post(
            f"{self.base_url}/api/v2/tenants/default_tenant/databases/default_database/collections/{collection_name}/get",
            headers={"Content-Type": "application/json"},
            json={
                "ids": ["doc_2"],
                "include": ["documents", "metadatas"]
            }
        )
        
        if get_response.status_code != 200:
            print(f"   ❌ Updated document retrieval failed: {get_response.status_code}")
            return False
            
        updated_data = get_response.json()
        updated_docs = updated_data.get("documents", [])
        updated_metadata = updated_data.get("metadatas", [])
        
        if (len(updated_docs) == 1 and 
            "Updated document about machine learning and AI" in updated_docs[0] and
            len(updated_metadata) == 1 and 
            updated_metadata[0].get("updated") == True):
            print("   ✅ Document update verification successful")
            return True
        else:
            print("   ❌ Document update verification failed")
            print(f"       Documents: {updated_docs}")
            print(f"       Metadata: {updated_metadata}")
            return False
            
    def test_document_query_search(self):
        """Test document querying and search functionality"""
        print("🔍 TESTING: Document Query and Search")
        
        if not self.test_collections:
            print("   ❌ No test collection available")
            return False
            
        collection_name = self.test_collections[0]
        
        # Test query by metadata
        print("   Querying documents by metadata...")
        query_response = requests.post(
            f"{self.base_url}/api/v2/tenants/default_tenant/databases/default_database/collections/{collection_name}/get",
            headers={"Content-Type": "application/json"},
            json={
                "where": {"topic": "ml"},
                "include": ["documents", "metadatas"]
            }
        )
        
        if query_response.status_code != 200:
            print(f"   ❌ Metadata query failed: {query_response.status_code}")
            return False
            
        query_data = query_response.json()
        query_docs = query_data.get("documents", [])
        query_metadata = query_data.get("metadatas", [])
        
        # Should find at least one document with topic "ml"
        ml_docs = [m for m in query_metadata if m.get("topic") == "ml"]
        if len(ml_docs) > 0:
            print(f"   ✅ Metadata query successful: found {len(ml_docs)} documents")
            return True
        else:
            print(f"   ❌ Metadata query failed: no documents found with topic 'ml'")
            print(f"       Available metadata: {query_metadata}")
            return False
    
    def cleanup(self):
        """Clean up test collections"""
        print("🧹 Cleaning up test collections...")
        for collection_name in self.test_collections:
            try:
                delete_response = requests.delete(
                    f"{self.base_url}/api/v2/tenants/default_tenant/databases/default_database/collections/{collection_name}"
                )
                if delete_response.status_code == 200:
                    print(f"   ✅ Cleaned up collection: {collection_name}")
                else:
                    print(f"   ⚠️ Failed to clean up collection: {collection_name}")
            except Exception as e:
                print(f"   ⚠️ Error cleaning up {collection_name}: {e}")
    
    def run_all_tests(self):
        """Run all document storage verification tests"""
        print("🔬 DOCUMENT STORAGE VERIFICATION TEST SUITE")
        print("=" * 60)
        
        tests = [
            ("Document Storage Cycle", self.test_document_storage_cycle),
            ("Document Update Cycle", self.test_document_update_cycle),
            ("Document Query Search", self.test_document_query_search)
        ]
        
        passed = 0
        total = len(tests)
        
        for test_name, test_func in tests:
            print(f"\n{test_name}:")
            try:
                if test_func():
                    passed += 1
                    print(f"✅ {test_name} PASSED")
                else:
                    print(f"❌ {test_name} FAILED")
            except Exception as e:
                print(f"❌ {test_name} ERROR: {e}")
        
        print("\n" + "=" * 60)
        print(f"📊 DOCUMENT STORAGE TEST RESULTS:")
        print(f"✅ Passed: {passed}/{total}")
        print(f"❌ Failed: {total - passed}/{total}")
        print(f"📈 Success Rate: {(passed/total)*100:.1f}%")
        
        if passed == total:
            print("🎉 ALL DOCUMENT STORAGE TESTS PASSED!")
            return True
        else:
            print("🚨 DOCUMENT STORAGE ISSUES DETECTED!")
            return False

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='Document Storage Verification Test')
    parser.add_argument('--url', default='https://chroma-load-balancer.onrender.com',
                        help='Load balancer URL')
    args = parser.parse_args()
    
    verifier = DocumentStorageVerifier(args.url)
    
    try:
        success = verifier.run_all_tests()
        sys.exit(0 if success else 1)
    finally:
        verifier.cleanup() 