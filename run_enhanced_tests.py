#!/usr/bin/env python3
"""
Enhanced Test Runner with Selective Cleanup
Uses the new selective cleanup system that preserves failed test data for debugging
"""

import uuid
import time
import logging
from enhanced_test_base_cleanup import EnhancedTestBase

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class EnhancedComprehensiveTest(EnhancedTestBase):
    """Enhanced comprehensive test suite with selective cleanup"""
    
    def __init__(self, base_url="https://chroma-load-balancer.onrender.com"):
        super().__init__(base_url, test_prefix="AUTOTEST_enhanced")

    def test_health_endpoints(self):
        """Test all health endpoints"""
        logger.info("🔍 Testing Health Endpoints")
        
        self.start_test("Health Endpoints")
        start_time = time.time()
        
        try:
            endpoints = [
                ("/health", "Health Check"),
                ("/status", "Status Check"), 
                ("/wal/status", "WAL Status"),
                ("/metrics", "Metrics"),
                ("/collection/mappings", "Collection Mappings")
            ]
            
            for endpoint, name in endpoints:
                response = self.make_request('GET', f"{self.base_url}{endpoint}")
                if response.status_code != 200:
                    return self.log_test_result(
                        "Health Endpoints",
                        False,
                        f"{name} failed: {response.status_code}",
                        time.time() - start_time
                    )
            
            return self.log_test_result(
                "Health Endpoints",
                True,
                "All health endpoints responding",
                time.time() - start_time
            )
            
        except Exception as e:
            return self.log_test_result(
                "Health Endpoints",
                False,
                f"Exception: {str(e)}",
                time.time() - start_time
            )

    def test_collection_operations(self):
        """Test collection operations with distributed architecture validation"""
        logger.info("📚 Testing Collection Operations & Distributed Mapping")
        
        self.start_test("Collection Operations")
        start_time = time.time()
        
        try:
            # List collections
            response = self.make_request('GET', f"{self.base_url}/api/v2/tenants/default_tenant/databases/default_database/collections")
            if response.status_code != 200:
                return self.log_test_result(
                    "Collection Operations",
                    False,
                    f"List collections failed: {response.status_code}",
                    time.time() - start_time
                )
            
            initial_count = len(response.json())
            
            # Create test collection
            collection_name = self.create_unique_collection_name("collections")
            create_response = self.make_request(
                'POST',
                f"{self.base_url}/api/v2/tenants/default_tenant/databases/default_database/collections",
                json={"name": collection_name}
            )
            
            if create_response.status_code not in [200, 201]:
                return self.log_test_result(
                    "Collection Operations",
                    False,
                    f"Collection creation failed: {create_response.status_code}",
                    time.time() - start_time
                )
            
            collection_data = create_response.json()
            collection_name_returned = collection_data.get('name')
            
            if collection_name_returned != collection_name:
                return self.log_test_result(
                    "Collection Operations",
                    False,
                    f"Collection name mismatch: expected {collection_name}, got {collection_name_returned}",
                    time.time() - start_time
                )
            
            # Wait for auto-mapping to complete
            logger.info("   Waiting for auto-mapping system...")
            time.sleep(5)
            
            # Verify collection exists on primary instance BY NAME
            primary_response = self.make_request('GET', "https://chroma-primary.onrender.com/api/v2/tenants/default_tenant/databases/default_database/collections")
            if primary_response.status_code != 200:
                return self.log_test_result(
                    "Collection Operations",
                    False,
                    f"Primary instance check failed: {primary_response.status_code}",
                    time.time() - start_time
                )
            
            primary_collections = primary_response.json()
            primary_collection = next((c for c in primary_collections if c['name'] == collection_name), None)
            
            if not primary_collection:
                return self.log_test_result(
                    "Collection Operations",
                    False,
                    f"Collection not found on primary by name",
                    time.time() - start_time
                )
            
            primary_uuid = primary_collection['id']
            logger.info(f"   ✅ Found on primary: {primary_uuid[:8]}... (name: {collection_name})")
            
            # Verify collection exists on replica instance BY NAME
            replica_response = self.make_request('GET', "https://chroma-replica.onrender.com/api/v2/tenants/default_tenant/databases/default_database/collections")
            if replica_response.status_code != 200:
                return self.log_test_result(
                    "Collection Operations",
                    False,
                    f"Replica instance check failed: {replica_response.status_code}",
                    time.time() - start_time
                )
            
            replica_collections = replica_response.json()
            replica_collection = next((c for c in replica_collections if c['name'] == collection_name), None)
            
            if not replica_collection:
                return self.log_test_result(
                    "Collection Operations",
                    False,
                    f"Collection not found on replica by name",
                    time.time() - start_time
                )
            
            replica_uuid = replica_collection['id']
            logger.info(f"   ✅ Found on replica: {replica_uuid[:8]}... (name: {collection_name})")
            
            # Verify UUIDs are different (correct distributed architecture)
            if primary_uuid == replica_uuid:
                return self.log_test_result(
                    "Collection Operations",
                    False,
                    f"Same UUID on both instances - violates distributed design",
                    time.time() - start_time
                )
            
            # Verify collection mapping exists
            mapping_response = self.make_request('GET', f"{self.base_url}/collection/mappings")
            if mapping_response.status_code != 200:
                return self.log_test_result(
                    "Collection Operations",
                    False,
                    f"Collection mapping check failed: {mapping_response.status_code}",
                    time.time() - start_time
                )
            
            mapping_data = mapping_response.json()
            test_mapping = next((m for m in mapping_data['mappings'] if m['collection_name'] == collection_name), None)
            
            if not test_mapping:
                return self.log_test_result(
                    "Collection Operations",
                    False,
                    f"No mapping found for collection {collection_name}",
                    time.time() - start_time
                )
            
            logger.info(f"   ✅ Mapping: P:{test_mapping['primary_collection_id'][:8]}..., R:{test_mapping['replica_collection_id'][:8]}...")
            
            return self.log_test_result(
                "Collection Operations",
                True,
                f"✅ Distributed collection created: different UUIDs (P:{primary_uuid[:8]}..., R:{replica_uuid[:8]}...), auto-mapped correctly",
                time.time() - start_time
            )
            
        except Exception as e:
            return self.log_test_result(
                "Collection Operations",
                False,
                f"Exception: {str(e)}",
                time.time() - start_time
            )

    def test_document_operations(self):
        """Test document operations with comprehensive validation"""
        logger.info("📄 Testing Document Operations")
        
        self.start_test("Document Operations")
        start_time = time.time()
        
        try:
            # Use existing collection or create new one
            collection_name = self.create_unique_collection_name("documents")
            
            # Create collection
            create_response = self.make_request(
                'POST',
                f"{self.base_url}/api/v2/tenants/default_tenant/databases/default_database/collections",
                json={"name": collection_name}
            )
            
            if create_response.status_code not in [200, 201]:
                return self.log_test_result(
                    "Document Operations",
                    False,
                    f"Collection creation failed: {create_response.status_code}",
                    time.time() - start_time
                )
            
            # Add documents
            doc_ids = [f"doc_{i}_{uuid.uuid4().hex[:8]}" for i in range(2)]
            doc_data = {
                "embeddings": [[0.1, 0.2, 0.3, 0.4, 0.5], [0.6, 0.7, 0.8, 0.9, 1.0]],
                "documents": ["Test document 1", "Test document 2"],
                "metadatas": [{"type": "test", "index": 1}, {"type": "test", "index": 2}],
                "ids": doc_ids
            }
            
            self.track_documents(collection_name, doc_ids)
            
            add_response = self.make_request(
                'POST',
                f"{self.base_url}/api/v2/tenants/default_tenant/databases/default_database/collections/{collection_name}/add",
                json=doc_data
            )
            
            if add_response.status_code not in [200, 201]:
                return self.log_test_result(
                    "Document Operations",
                    False,
                    f"Document add failed: {add_response.status_code}",
                    time.time() - start_time
                )
            
            # Get documents
            get_response = self.make_request(
                'POST',
                f"{self.base_url}/api/v2/tenants/default_tenant/databases/default_database/collections/{collection_name}/get",
                json={"include": ["documents", "metadatas"]}
            )
            
            if get_response.status_code != 200:
                return self.log_test_result(
                    "Document Operations",
                    False,
                    f"Document get failed: {get_response.status_code}",
                    time.time() - start_time
                )
            
            get_result = get_response.json()
            retrieved_count = len(get_result.get('ids', []))
            
            # Query documents
            query_response = self.make_request(
                'POST',
                f"{self.base_url}/api/v2/tenants/default_tenant/databases/default_database/collections/{collection_name}/query",
                json={
                    "query_embeddings": [[0.1, 0.2, 0.3, 0.4, 0.5]],
                    "n_results": 2,
                    "include": ["documents", "metadatas"]
                }
            )
            
            if query_response.status_code != 200:
                return self.log_test_result(
                    "Document Operations",
                    False,
                    f"Document query failed: {query_response.status_code}",
                    time.time() - start_time
                )
            
            query_result = query_response.json()
            query_count = len(query_result.get('ids', [[]])[0]) if query_result.get('ids') else 0
            
            return self.log_test_result(
                "Document Operations",
                True,
                f"Added 2, retrieved {retrieved_count}, queried {query_count} documents",
                time.time() - start_time
            )
            
        except Exception as e:
            return self.log_test_result(
                "Document Operations",
                False,
                f"Exception: {str(e)}",
                time.time() - start_time
            )

    def test_wal_functionality(self):
        """Test WAL system functionality"""
        logger.info("📝 Testing WAL System")
        
        self.start_test("WAL Functionality")
        start_time = time.time()
        
        try:
            # Check WAL status
            status_response = self.make_request('GET', f"{self.base_url}/wal/status")
            
            if status_response.status_code != 200:
                return self.log_test_result(
                    "WAL Functionality",
                    False,
                    f"WAL status check failed: {status_response.status_code}",
                    time.time() - start_time
                )
            
            status_data = status_response.json()
            pending = status_data.get('pending', 0)
            successful = status_data.get('successful', 0)
            
            # Test WAL cleanup
            cleanup_response = self.make_request(
                'POST',
                f"{self.base_url}/wal/cleanup",
                json={"max_age_hours": 24}
            )
            
            if cleanup_response.status_code != 200:
                return self.log_test_result(
                    "WAL Functionality", 
                    False,
                    f"WAL cleanup failed: {cleanup_response.status_code}",
                    time.time() - start_time
                )
            
            cleanup_data = cleanup_response.json()
            cleaned = cleanup_data.get('cleaned', 0)
            
            return self.log_test_result(
                "WAL Functionality",
                True, 
                f"Pending: {pending}, Successful: {successful}, Cleaned: {cleaned}",
                time.time() - start_time
            )
            
        except Exception as e:
            return self.log_test_result(
                "WAL Functionality",
                False,
                f"Exception: {str(e)}",
                time.time() - start_time
            )

    def test_load_balancer_features(self):
        """Test load balancer specific features"""
        logger.info("⚖️ Testing Load Balancer Features")
        
        self.start_test("Load Balancer Features")
        start_time = time.time()
        
        try:
            # Check instance health
            health_response = self.make_request('GET', f"{self.base_url}/status")
            
            if health_response.status_code != 200:
                return self.log_test_result(
                    "Load Balancer Features",
                    False,
                    f"Instance health check failed: {health_response.status_code}",
                    time.time() - start_time
                )
            
            health_data = health_response.json()
            healthy_instances = sum(1 for instance in health_data.get('instances', []) if instance.get('healthy'))
            total_instances = len(health_data.get('instances', []))
            
            # Check collection mappings
            mappings_response = self.make_request('GET', f"{self.base_url}/collection/mappings")
            
            if mappings_response.status_code != 200:
                return self.log_test_result(
                    "Load Balancer Features",
                    False,
                    f"Collection mappings check failed: {mappings_response.status_code}",
                    time.time() - start_time
                )
            
            mappings_data = mappings_response.json()
            mapping_count = mappings_data.get('count', 0)
            
            return self.log_test_result(
                "Load Balancer Features",
                True,
                f"Healthy instances: {healthy_instances}/{total_instances}, Mappings: {mapping_count}",
                time.time() - start_time
            )
            
        except Exception as e:
            return self.log_test_result(
                "Load Balancer Features",
                False,
                f"Exception: {str(e)}",
                time.time() - start_time
            )

    def test_delete_sync_functionality(self):
        """Test DELETE sync functionality with timing"""
        logger.info("🗑️ Testing DELETE Sync Functionality")
        
        self.start_test("DELETE Sync Functionality") 
        start_time = time.time()
        
        try:
            # Create test collection for deletion
            collection_name = self.create_unique_collection_name("delete_sync")
            
            create_response = self.make_request(
                'POST',
                f"{self.base_url}/api/v2/tenants/default_tenant/databases/default_database/collections",
                json={"name": collection_name}
            )
            
            if create_response.status_code not in [200, 201]:
                return self.log_test_result(
                    "DELETE Sync Functionality",
                    False,
                    f"Test collection creation failed: {create_response.status_code}",
                    time.time() - start_time
                )
            
            collection_data = create_response.json()
            collection_uuid = collection_data.get('id')
            
            logger.info(f"   Created collection: {collection_name} ({collection_uuid[:8]}...)")
            logger.info("   Waiting 15s for initial sync...")
            time.sleep(15)
            
            # Execute DELETE request
            delete_response = self.make_request(
                'DELETE',
                f"{self.base_url}/api/v2/tenants/default_tenant/databases/default_database/collections/{collection_name}"
            )
            
            if delete_response.status_code not in [200, 204]:
                return self.log_test_result(
                    "DELETE Sync Functionality",
                    False,
                    f"DELETE request failed: {delete_response.status_code}",
                    time.time() - start_time
                )
            
            logger.info("   DELETE request successful, waiting 15s for sync...")
            time.sleep(15)
            
            # CRITICAL FIX: Verify deletion on BOTH instances directly, not just through load balancer
            logger.info("   Verifying deletion on primary instance...")
            primary_verify = self.make_request(
                'GET',
                f"https://chroma-primary.onrender.com/api/v2/tenants/default_tenant/databases/default_database/collections/{collection_name}"
            )
            
            logger.info("   Verifying deletion on replica instance...")
            replica_verify = self.make_request(
                'GET', 
                f"https://chroma-replica.onrender.com/api/v2/tenants/default_tenant/databases/default_database/collections/{collection_name}"
            )
            
            # Both should return 404 if properly deleted and synced
            primary_deleted = primary_verify.status_code == 404
            replica_deleted = replica_verify.status_code == 404
            
            if primary_deleted and replica_deleted:
                return self.log_test_result(
                    "DELETE Sync Functionality",
                    True,
                    "Collection successfully deleted from both instances",
                    time.time() - start_time
                )
            else:
                failure_details = []
                if not primary_deleted:
                    failure_details.append(f"primary still has collection ({primary_verify.status_code})")
                if not replica_deleted:
                    failure_details.append(f"replica still has collection ({replica_verify.status_code})")
                
                return self.log_test_result(
                    "DELETE Sync Functionality",
                    False,
                    f"DELETE sync failed: {', '.join(failure_details)}",
                    time.time() - start_time
                )
            
        except Exception as e:
            return self.log_test_result(
                "DELETE Sync Functionality",
                False,
                f"Exception: {str(e)}",
                time.time() - start_time
            )

def main():
    """Run enhanced comprehensive tests with selective cleanup"""
    import argparse
    
    parser = argparse.ArgumentParser(description="Enhanced Test Runner with Selective Cleanup")
    parser.add_argument("--url", default="https://chroma-load-balancer.onrender.com", help="Load balancer URL")
    parser.add_argument("--force-cleanup", action="store_true", help="Force cleanup all data regardless of results")
    args = parser.parse_args()
    
    tester = EnhancedComprehensiveTest(args.url)
    
    logger.info("🚀 Starting Enhanced Comprehensive Tests with Selective Cleanup")
    logger.info(f"🌐 Target URL: {args.url}")
    logger.info(f"🆔 Test Session: {tester.test_session_id}")
    logger.info("="*80)
    
    try:
        # Run test suite
        logger.info("\n🧪 Running Health Endpoints Tests...")
        tester.test_health_endpoints()
        
        logger.info("\n🧪 Running Collection Operations Tests...")
        tester.test_collection_operations()
        
        logger.info("\n🧪 Running Document Operations Tests...")
        tester.test_document_operations()
        
        logger.info("\n🧪 Running WAL Functionality Tests...")
        tester.test_wal_functionality()
        
        logger.info("\n🧪 Running Load Balancer Features Tests...")
        tester.test_load_balancer_features()
        
        logger.info("\n🧪 Running DELETE Sync Functionality Tests...")
        tester.test_delete_sync_functionality()
        
    except Exception as e:
        logger.error(f"❌ Test execution failed: {e}")
    
    # Print test summary with cleanup strategy
    overall_success = tester.print_test_summary()
    
    # Perform selective cleanup
    if args.force_cleanup:
        logger.info("\n🧹 FORCED CLEANUP REQUESTED")
        cleanup_results = tester.force_cleanup_all()
    else:
        logger.info("\n🧹 SELECTIVE CLEANUP")
        cleanup_results = tester.selective_cleanup()
    
    logger.info("\n" + "="*80)
    logger.info("🎯 ENHANCED COMPREHENSIVE TESTING COMPLETE")
    logger.info("="*80)
    
    if cleanup_results.get('tests_preserved', 0) > 0:
        logger.info("🔍 DEBUGGING GUIDANCE:")
        logger.info("   - Failed test data has been preserved for investigation")
        logger.info("   - Check preserved collections and documents listed above")
        logger.info("   - Use these endpoints to inspect the data:")
        logger.info(f"     • Collection list: {args.url}/api/v2/tenants/default_tenant/databases/default_database/collections")
        logger.info(f"     • Collection mappings: {args.url}/collection/mappings")
        logger.info("   - Run with --force-cleanup to remove all data when done debugging")
    else:
        logger.info("✅ All tests passed - no debugging data needed")
    
    return overall_success

if __name__ == "__main__":
    success = main()
    exit(0 if success else 1) 