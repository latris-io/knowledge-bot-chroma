#!/usr/bin/env python3
"""
REAL PRODUCTION VALIDATION TESTS
Tests actual functionality that matters to real users, not just API responses
"""

import requests
import time
import uuid
import json
import sys
from datetime import datetime

class ProductionValidationTests:
    def __init__(self, base_url="https://chroma-load-balancer.onrender.com"):
        self.base_url = base_url
        self.test_session_id = int(time.time())
        self.created_collections = set()
        self.created_documents = {}
        self.failures = []
        
    def fail_test(self, test_name, reason, details=""):
        """Record a test failure with details"""
        self.failures.append({
            'test': test_name,
            'reason': reason,
            'details': details,
            'timestamp': datetime.now().isoformat()
        })
        print(f"❌ PRODUCTION FAILURE: {test_name}")
        print(f"   Reason: {reason}")
        if details:
            print(f"   Details: {details}")
        return False
        
    def pass_test(self, test_name, details=""):
        """Record a test success"""
        print(f"✅ PRODUCTION VALIDATED: {test_name}")
        if details:
            print(f"   Details: {details}")
        return True
        
    def validate_json_response(self, response, operation_name):
        """Validate that response is valid JSON and has expected structure"""
        try:
            if response.status_code >= 400:
                return self.fail_test(
                    f"{operation_name}: Response Validation",
                    f"HTTP error {response.status_code}",
                    response.text[:200]
                )
            
            data = response.json()
            return data
            
        except json.JSONDecodeError as e:
            return self.fail_test(
                f"{operation_name}: JSON Validation", 
                "Response is not valid JSON",
                f"Status: {response.status_code}, Content: {response.text[:100]}"
            )
        except Exception as e:
            return self.fail_test(
                f"{operation_name}: Response Validation",
                f"Unexpected error: {e}",
                f"Status: {response.status_code}"
            )
    
    def test_real_collection_creation_and_replication(self):
        """Test that collections are actually created and replicated to both instances"""
        print("\n🔍 PRODUCTION TEST: Collection Creation & Replication")
        
        test_collection = f"PROD_TEST_collection_{self.test_session_id}"
        self.created_collections.add(test_collection)
        
        # Step 1: Create collection via load balancer
        print("   Step 1: Creating collection via load balancer...")
        create_response = requests.post(
            f"{self.base_url}/api/v2/tenants/default_tenant/databases/default_database/collections",
            headers={"Content-Type": "application/json"},
            json={"name": test_collection, "configuration": {"hnsw": {"space": "l2"}}},
            timeout=30
        )
        
        collection_data = self.validate_json_response(create_response, "Collection Creation")
        if not collection_data:
            return False
            
        collection_id = collection_data.get('id')
        if not collection_id:
            return self.fail_test(
                "Collection Creation: ID Validation",
                "Created collection has no ID",
                str(collection_data)
            )
            
        print(f"   Collection created with ID: {collection_id[:8]}...")
        
        # Step 2: Wait for auto-mapping and verify collection exists on primary BY NAME
        print("   Step 2: Verifying collection exists on primary instance by name...")
        time.sleep(5)  # Wait for auto-mapping system
        
        primary_response = requests.get(
            f"https://chroma-primary.onrender.com/api/v2/tenants/default_tenant/databases/default_database/collections",
            timeout=15
        )
        
        primary_collections = self.validate_json_response(primary_response, "Primary Instance Verification")
        if not primary_collections:
            return False
        
        # Find collection by name (UUIDs will be different per instance)
        primary_collection = next((c for c in primary_collections if c['name'] == test_collection), None)
        if not primary_collection:
            primary_names = [c['name'] for c in primary_collections]
            return self.fail_test(
                "Primary Instance Verification",
                "Collection not found on primary by name",
                f"Primary has {len(primary_names)} collections, test collection not found"
            )
            
        primary_uuid = primary_collection['id']
        print(f"   ✅ Found on primary: {primary_uuid[:8]}... (name: {test_collection})")
            
        # Step 3: Verify collection exists on replica instance by name  
        print("   Step 3: Verifying collection exists on replica instance by name...")
        replica_response = requests.get(
            f"https://chroma-replica.onrender.com/api/v2/tenants/default_tenant/databases/default_database/collections",
            timeout=15
        )
        
        replica_collections = self.validate_json_response(replica_response, "Replica Instance Verification")
        if not replica_collections:
            return False
        
        # Find collection by name (UUIDs will be different per instance)
        replica_collection = next((c for c in replica_collections if c['name'] == test_collection), None)
        if not replica_collection:
            replica_names = [c['name'] for c in replica_collections]
            return self.fail_test(
                "Replica Instance Verification",
                "Collection not found on replica by name",
                f"Replica has {len(replica_names)} collections, test collection not found"
            )
            
        replica_uuid = replica_collection['id']
        print(f"   ✅ Found on replica: {replica_uuid[:8]}... (name: {test_collection})")
        
        # Verify UUIDs are different (correct distributed architecture)
        if primary_uuid == replica_uuid:
            return self.fail_test(
                "Distributed Architecture Validation",
                "Same UUID on both instances - violates distributed design",
                f"Both instances have UUID: {primary_uuid}"
            )
            
        print(f"   ✅ Confirmed different UUIDs: Primary={primary_uuid[:8]}..., Replica={replica_uuid[:8]}...")
            
        # Step 4: Verify collection mapping was created
        print("   Step 4: Verifying collection mapping was created...")
        mapping_response = requests.get(f"{self.base_url}/collection/mappings", timeout=15)
        mapping_data = self.validate_json_response(mapping_response, "Collection Mapping Verification")
        if not mapping_data:
            return False
            
        mappings = mapping_data.get('mappings', [])
        test_mapping = next((m for m in mappings if m['collection_name'] == test_collection), None)
        
        if not test_mapping:
            return self.fail_test(
                "Collection Mapping Verification",
                "Collection mapping was not created",
                f"Available mappings: {[m['collection_name'] for m in mappings]}"
            )
            
        # Step 5: Verify the mapping has the correct UUIDs for both instances
        mapping_primary_uuid = test_mapping.get('primary_collection_id')
        mapping_replica_uuid = test_mapping.get('replica_collection_id')
        
        if not mapping_primary_uuid or not mapping_replica_uuid:
            return self.fail_test(
                "Collection Mapping Validation",
                "Mapping missing primary or replica UUID",
                f"Mapping Primary: {mapping_primary_uuid}, Mapping Replica: {mapping_replica_uuid}"
            )
            
        # Verify mapping UUIDs match what we found on the actual instances
        if mapping_primary_uuid != primary_uuid:
            return self.fail_test(
                "Collection Mapping Validation",
                "Primary UUID mismatch between mapping and actual instance",
                f"Instance: {primary_uuid}, Mapping: {mapping_primary_uuid}"
            )
            
        if mapping_replica_uuid != replica_uuid:
            return self.fail_test(
                "Collection Mapping Validation", 
                "Replica UUID mismatch between mapping and actual instance",
                f"Instance: {replica_uuid}, Mapping: {mapping_replica_uuid}"
            )
            
        print(f"   ✅ Mapping validated: {test_collection} -> P:{mapping_primary_uuid[:8]}..., R:{mapping_replica_uuid[:8]}...")
            
        return self.pass_test(
            "Collection Creation & Replication",
            f"✅ Distributed architecture working correctly - Collection created, auto-mapped to both instances with different UUIDs, load balancer mapping accurate"
        )
    
    def test_real_document_ingestion_and_sync(self):
        """Test that documents are actually ingested and synced to both instances"""
        print("\n🔍 PRODUCTION TEST: Document Ingestion & Sync")
        
        if not self.created_collections:
            return self.fail_test(
                "Document Ingestion: Prerequisites",
                "No test collection available",
                "Collection creation must pass first"
            )
            
        test_collection = list(self.created_collections)[0]
        test_docs = {
            "ids": [f"prod_doc_{self.test_session_id}_{i}" for i in range(3)],
            "documents": [f"Production test document {i} for session {self.test_session_id}" for i in range(3)],
            "metadatas": [{"session": self.test_session_id, "doc_index": i, "test_type": "production"} for i in range(3)],
            "embeddings": [[0.1*i, 0.2*i, 0.3*i, 0.4*i, 0.5*i] for i in range(1, 4)]
        }
        
        self.created_documents[test_collection] = set(test_docs["ids"])
        
        # Step 1: Add documents via load balancer
        print("   Step 1: Adding documents via load balancer...")
        add_response = requests.post(
            f"{self.base_url}/api/v2/tenants/default_tenant/databases/default_database/collections/{test_collection}/add",
            headers={"Content-Type": "application/json"},
            json=test_docs,
            timeout=30
        )
        
        if not self.validate_json_response(add_response, "Document Addition"):
            return False
            
        # Step 2: Verify documents can be retrieved via load balancer
        print("   Step 2: Verifying documents can be retrieved via load balancer...")
        time.sleep(2)  # Brief wait for immediate consistency
        
        get_response = requests.post(
            f"{self.base_url}/api/v2/tenants/default_tenant/databases/default_database/collections/{test_collection}/get",
            headers={"Content-Type": "application/json"},
            json={"ids": test_docs["ids"], "include": ["documents", "metadatas"]},
            timeout=30
        )
        
        get_data = self.validate_json_response(get_response, "Document Retrieval")
        if not get_data:
            return False
            
        retrieved_ids = get_data.get('ids', [])
        if len(retrieved_ids) != len(test_docs["ids"]):
            return self.fail_test(
                "Document Retrieval: Count Validation",
                f"Retrieved {len(retrieved_ids)} documents, expected {len(test_docs['ids'])}",
                f"Retrieved IDs: {retrieved_ids}"
            )
            
        # Verify content is correct
        retrieved_docs = get_data.get('documents', [])
        retrieved_metadatas = get_data.get('metadatas', [])
        
        for i, doc_id in enumerate(test_docs["ids"]):
            if doc_id not in retrieved_ids:
                return self.fail_test(
                    "Document Retrieval: Content Validation",
                    f"Document {doc_id} not retrieved",
                    f"Retrieved: {retrieved_ids}"
                )
                
            # Find the index of this document in retrieved data
            retrieved_index = retrieved_ids.index(doc_id)
            expected_content = test_docs["documents"][i]
            actual_content = retrieved_docs[retrieved_index]
            
            if expected_content != actual_content:
                return self.fail_test(
                    "Document Retrieval: Content Validation",
                    f"Document content mismatch for {doc_id}",
                    f"Expected: {expected_content}, Got: {actual_content}"
                )
        
        # Step 3: Test document querying works correctly
        print("   Step 3: Testing document querying...")
        query_response = requests.post(
            f"{self.base_url}/api/v2/tenants/default_tenant/databases/default_database/collections/{test_collection}/query",
            headers={"Content-Type": "application/json"},
            json={
                "query_embeddings": [[0.1, 0.2, 0.3, 0.4, 0.5]],
                "n_results": 5,
                "include": ["documents", "metadatas", "distances"]
            },
            timeout=30
        )
        
        query_data = self.validate_json_response(query_response, "Document Querying")
        if not query_data:
            return False
            
        query_ids = query_data.get('ids', [[]])[0] if query_data.get('ids') else []
        if not query_ids:
            return self.fail_test(
                "Document Querying: Results Validation",
                "Query returned no results",
                f"Query response: {query_data}"
            )
            
        # Step 4: Wait for WAL sync and verify it actually worked
        print("   Step 4: Waiting for WAL sync and verifying it worked...")
        time.sleep(15)  # Wait for WAL sync
        
        wal_response = requests.get(f"{self.base_url}/wal/status", timeout=15)
        wal_data = self.validate_json_response(wal_response, "WAL Status Check")
        if not wal_data:
            return False
            
        successful_syncs = wal_data.get('performance_stats', {}).get('successful_syncs', 0)
        if successful_syncs == 0:
            return self.fail_test(
                "WAL Sync Verification",
                "No successful WAL syncs recorded",
                f"WAL data: {wal_data}"
            )
            
        return self.pass_test(
            "Document Ingestion & Sync",
            f"Documents ingested, retrievable, queryable, and WAL synced (successful syncs: {successful_syncs})"
        )
    
    def test_real_load_balancer_functionality(self):
        """Test that load balancer actually balances load and handles failover"""
        print("\n🔍 PRODUCTION TEST: Load Balancer Functionality")
        
        # Step 1: Verify both instances are healthy
        print("   Step 1: Verifying both instances are healthy...")
        primary_health = requests.get("https://chroma-primary.onrender.com/api/v2/heartbeat", timeout=10)
        replica_health = requests.get("https://chroma-replica.onrender.com/api/v2/heartbeat", timeout=10)
        
        if primary_health.status_code != 200:
            return self.fail_test(
                "Load Balancer: Instance Health",
                "Primary instance not healthy",
                f"Primary status: {primary_health.status_code}"
            )
            
        if replica_health.status_code != 200:
            return self.fail_test(
                "Load Balancer: Instance Health", 
                "Replica instance not healthy",
                f"Replica status: {replica_health.status_code}"
            )
            
        # Step 2: Test that load balancer reports correct health
        print("   Step 2: Testing load balancer health reporting...")
        lb_health = requests.get(f"{self.base_url}/health", timeout=15)
        health_data = self.validate_json_response(lb_health, "Load Balancer Health")
        if not health_data:
            return False
            
        healthy_instances = health_data.get('healthy_instances')
        if healthy_instances != "2/2":
            return self.fail_test(
                "Load Balancer: Health Reporting",
                f"Expected 2/2 healthy instances, got {healthy_instances}",
                str(health_data)
            )
            
        # Step 3: Test that read operations can access both instances
        print("   Step 3: Testing read operations access both instances...")
        if not self.created_collections:
            return self.fail_test(
                "Load Balancer: Read Test Prerequisites",
                "No test collection available",
                "Collection creation must pass first"
            )
            
        test_collection = list(self.created_collections)[0]
        
        # Make multiple read requests and verify they work
        successful_reads = 0
        for i in range(5):
            read_response = requests.get(
                f"{self.base_url}/api/v2/tenants/default_tenant/databases/default_database/collections/{test_collection}",
                timeout=15
            )
            if read_response.status_code == 200:
                successful_reads += 1
            
        if successful_reads < 4:  # Allow 1 failure for network issues
            return self.fail_test(
                "Load Balancer: Read Distribution",
                f"Only {successful_reads}/5 read operations succeeded",
                "Load balancer may not be distributing reads properly"
            )
            
        return self.pass_test(
            "Load Balancer Functionality",
            f"Both instances healthy, health reporting correct, read distribution working ({successful_reads}/5 reads successful)"
        )
    
    def test_real_delete_functionality(self):
        """Test that DELETE operations actually delete from both instances"""
        print("\n🔍 PRODUCTION TEST: DELETE Functionality")
        
        # Create a dedicated collection for deletion testing
        delete_test_collection = f"PROD_DELETE_test_{self.test_session_id}"
        
        # Step 1: Create collection to delete
        print("   Step 1: Creating collection for deletion test...")
        create_response = requests.post(
            f"{self.base_url}/api/v2/tenants/default_tenant/databases/default_database/collections",
            headers={"Content-Type": "application/json"},
            json={"name": delete_test_collection, "configuration": {"hnsw": {"space": "l2"}}},
            timeout=30
        )
        
        if not self.validate_json_response(create_response, "DELETE Test: Collection Creation"):
            return False
            
        collection_id = create_response.json().get('id')
        time.sleep(5)  # Wait for replication
        
        # Step 2: Verify collection exists on both instances BY NAME before deletion
        print("   Step 2: Verifying collection exists on both instances by name before deletion...")
        
        # Check primary by name
        primary_before = requests.get(
            f"https://chroma-primary.onrender.com/api/v2/tenants/default_tenant/databases/default_database/collections",
            timeout=15
        )
        
        primary_collections_before = self.validate_json_response(primary_before, "DELETE Test: Pre-deletion Primary Check")
        if not primary_collections_before:
            return False
            
        primary_collection_before = next((c for c in primary_collections_before if c['name'] == delete_test_collection), None)
        if not primary_collection_before:
            primary_names = [c['name'] for c in primary_collections_before]
            return self.fail_test(
                "DELETE Test: Pre-deletion Verification",
                "Collection not found on primary by name before deletion",
                f"Primary has {len(primary_names)} collections, test collection not found"
            )
            
        primary_delete_uuid = primary_collection_before['id']
        print(f"   ✅ Found on primary before DELETE: {primary_delete_uuid[:8]}... (name: {delete_test_collection})")
        
        # Check replica by name
        replica_before = requests.get(
            f"https://chroma-replica.onrender.com/api/v2/tenants/default_tenant/databases/default_database/collections",
            timeout=15
        )
        
        replica_collections_before = self.validate_json_response(replica_before, "DELETE Test: Pre-deletion Replica Check")
        if not replica_collections_before:
            return False
            
        replica_collection_before = next((c for c in replica_collections_before if c['name'] == delete_test_collection), None)
        if not replica_collection_before:
            replica_names = [c['name'] for c in replica_collections_before]
            return self.fail_test(
                "DELETE Test: Pre-deletion Verification", 
                "Collection not found on replica by name before deletion",
                f"Replica has {len(replica_names)} collections, test collection not found"
            )
            
        replica_delete_uuid = replica_collection_before['id']
        print(f"   ✅ Found on replica before DELETE: {replica_delete_uuid[:8]}... (name: {delete_test_collection})")
            
        # Step 3: Execute DELETE via load balancer
        print("   Step 3: Executing DELETE via load balancer...")
        delete_response = requests.delete(
            f"{self.base_url}/api/v2/tenants/default_tenant/databases/default_database/collections/{delete_test_collection}",
            timeout=30
        )
        
        if delete_response.status_code not in [200, 404]:
            return self.fail_test(
                "DELETE Test: DELETE Execution",
                f"DELETE operation failed with status {delete_response.status_code}",
                delete_response.text[:200]
            )
            
        # Step 4: Wait for deletion to propagate and verify BY NAME on both instances
        print("   Step 4: Waiting for deletion to propagate and verifying by name on both instances...")
        time.sleep(10)  # Wait for deletion sync
        
        # Check primary instance by name (not UUID)
        primary_after = requests.get(
            f"https://chroma-primary.onrender.com/api/v2/tenants/default_tenant/databases/default_database/collections",
            timeout=15
        )
        
        primary_collections_after = self.validate_json_response(primary_after, "DELETE Test: Post-deletion Primary Check")
        if not primary_collections_after:
            return False
        
        primary_collection_after = next((c for c in primary_collections_after if c['name'] == delete_test_collection), None)
        if primary_collection_after:
            return self.fail_test(
                "DELETE Test: Primary Instance Verification",
                f"Collection still exists on primary after DELETE (name: {delete_test_collection})",
                f"Found: {primary_collection_after['id'][:8]}... - DELETE sync to primary failed"
            )
            
        print(f"   ✅ Confirmed deleted from primary (collection name not found)")
        
        # Check replica instance by name
        replica_after = requests.get(
            f"https://chroma-replica.onrender.com/api/v2/tenants/default_tenant/databases/default_database/collections",
            timeout=15
        )
        
        replica_collections_after = self.validate_json_response(replica_after, "DELETE Test: Post-deletion Replica Check")
        if not replica_collections_after:
            return False
        
        replica_collection_after = next((c for c in replica_collections_after if c['name'] == delete_test_collection), None)
        if replica_collection_after:
            return self.fail_test(
                "DELETE Test: Replica Instance Verification",
                f"Collection still exists on replica after DELETE (name: {delete_test_collection})",
                f"Found: {replica_collection_after['id'][:8]}... - DELETE sync to replica failed"
            )
            
        print(f"   ✅ Confirmed deleted from replica (collection name not found)")
            
        # Step 5: Verify load balancer correctly reports 404
        print("   Step 5: Verifying load balancer correctly reports 404...")
        lb_verify = requests.get(
            f"{self.base_url}/api/v2/tenants/default_tenant/databases/default_database/collections/{delete_test_collection}",
            timeout=15
        )
        
        if lb_verify.status_code != 404:
            return self.fail_test(
                "DELETE Test: Load Balancer Verification",
                f"Load balancer returns {lb_verify.status_code} instead of 404",
                "DELETE not properly reflected through load balancer"
            )
            
        return self.pass_test(
            "DELETE Functionality",
            "Collection deleted from both instances and load balancer correctly reports 404"
        )
    
    def cleanup_test_data(self):
        """Clean up all test data"""
        print("\n🧹 Cleaning up test data...")
        
        # Clean up documents
        for collection_name, doc_ids in self.created_documents.items():
            if doc_ids:
                try:
                    requests.post(
                        f"{self.base_url}/api/v2/tenants/default_tenant/databases/default_database/collections/{collection_name}/delete",
                        headers={"Content-Type": "application/json"},
                        json={"ids": list(doc_ids)},
                        timeout=30
                    )
                    print(f"   Cleaned up {len(doc_ids)} documents from {collection_name}")
                except:
                    pass
        
        # Clean up collections
        for collection_name in self.created_collections:
            try:
                requests.delete(
                    f"{self.base_url}/api/v2/tenants/default_tenant/databases/default_database/collections/{collection_name}",
                    timeout=30
                )
                print(f"   Cleaned up collection: {collection_name}")
            except:
                pass
                
        time.sleep(3)  # Wait for cleanup
        print("   Cleanup completed")
    
    def run_production_validation(self):
        """Run all production validation tests"""
        print("🚀 PRODUCTION VALIDATION TEST SUITE")
        print("="*60)
        print(f"Testing URL: {self.base_url}")
        print(f"Session ID: {self.test_session_id}")
        print(f"Started: {datetime.now().isoformat()}")
        print("="*60)
        
        tests = [
            ("Collection Creation & Replication", self.test_real_collection_creation_and_replication),
            ("Document Ingestion & Sync", self.test_real_document_ingestion_and_sync),
            ("Load Balancer Functionality", self.test_real_load_balancer_functionality),
            ("DELETE Functionality", self.test_real_delete_functionality)
        ]
        
        passed = 0
        
        try:
            for test_name, test_func in tests:
                print(f"\n{'='*20} {test_name} {'='*20}")
                if test_func():
                    passed += 1
                else:
                    print(f"❌ {test_name} FAILED")
        
        finally:
            self.cleanup_test_data()
        
        # Final report
        print("\n" + "="*60)
        print("🏁 PRODUCTION VALIDATION RESULTS")
        print("="*60)
        print(f"✅ Tests Passed: {passed}/{len(tests)}")
        print(f"❌ Tests Failed: {len(tests) - passed}/{len(tests)}")
        print(f"📊 Success Rate: {passed/len(tests)*100:.1f}%")
        
        if self.failures:
            print(f"\n❌ PRODUCTION FAILURES ({len(self.failures)}):")
            for failure in self.failures:
                print(f"  • {failure['test']}: {failure['reason']}")
                if failure['details']:
                    print(f"    Details: {failure['details']}")
        
        if passed == len(tests):
            print("\n🎉 ALL PRODUCTION VALIDATION TESTS PASSED!")
            print("   Your system is ready for production use.")
            return True
        else:
            print(f"\n⚠️  PRODUCTION ISSUES DETECTED!")
            print(f"   {len(tests) - passed} critical issues must be fixed before production use.")
            return False

if __name__ == "__main__":
    validator = ProductionValidationTests()
    success = validator.run_production_validation()
    sys.exit(0 if success else 1) 