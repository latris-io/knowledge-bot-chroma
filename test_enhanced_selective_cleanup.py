#!/usr/bin/env python3
"""
Enhanced Selective Cleanup Test Demo
Demonstrates preserving failed test data while cleaning successful test data
"""

import uuid
import time
import logging
from enhanced_test_base_cleanup import EnhancedTestBase

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class SelectiveCleanupTest(EnhancedTestBase):
    """Test class demonstrating selective cleanup functionality"""
    
    def __init__(self, base_url="https://chroma-load-balancer.onrender.com"):
        super().__init__(base_url, test_prefix="AUTOTEST_selective")

    def test_successful_operation(self):
        """Test that should succeed - data will be cleaned up"""
        logger.info("🧪 Testing Successful Operation (data will be cleaned)")
        
        self.start_test("Successful Operation")
        start_time = time.time()
        
        try:
            # Create collection
            collection_name = self.create_unique_collection_name("success")
            
            create_response = self.make_request(
                'POST',
                f"{self.base_url}/api/v2/tenants/default_tenant/databases/default_database/collections",
                json={"name": collection_name}
            )
            
            if create_response.status_code not in [200, 201]:
                return self.log_test_result(
                    "Successful Operation",
                    False,
                    f"Collection creation failed: {create_response.status_code}",
                    time.time() - start_time
                )
            
            # Add test document
            doc_ids = [f"success_doc_{uuid.uuid4().hex[:8]}"]
            doc_data = {
                "embeddings": [[0.1, 0.2, 0.3, 0.4, 0.5]],
                "documents": ["This is a successful test document"],
                "metadatas": [{"test_type": "success", "cleanup_expected": True}],
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
                    "Successful Operation",
                    False,
                    f"Document add failed: {add_response.status_code}",
                    time.time() - start_time
                )
            
            # This test succeeds - data will be cleaned up
            return self.log_test_result(
                "Successful Operation",
                True,
                "Document operations completed successfully",
                time.time() - start_time
            )
            
        except Exception as e:
            return self.log_test_result(
                "Successful Operation",
                False,
                f"Exception: {str(e)}",
                time.time() - start_time
            )

    def test_simulated_failure(self):
        """Test that simulates a failure - data will be preserved for debugging"""
        logger.info("🧪 Testing Simulated Failure (data will be preserved)")
        
        self.start_test("Simulated Failure")
        start_time = time.time()
        
        try:
            # Create collection
            collection_name = self.create_unique_collection_name("failure")
            
            create_response = self.make_request(
                'POST',
                f"{self.base_url}/api/v2/tenants/default_tenant/databases/default_database/collections",
                json={"name": collection_name}
            )
            
            if create_response.status_code not in [200, 201]:
                return self.log_test_result(
                    "Simulated Failure",
                    False,
                    f"Collection creation failed: {create_response.status_code}",
                    time.time() - start_time
                )
            
            # Add test document
            doc_ids = [f"failure_doc_{uuid.uuid4().hex[:8]}", f"debug_doc_{uuid.uuid4().hex[:8]}"]
            doc_data = {
                "embeddings": [[0.6, 0.7, 0.8, 0.9, 1.0], [0.2, 0.3, 0.4, 0.5, 0.6]],
                "documents": ["This document should be preserved", "This is debugging data"],
                "metadatas": [
                    {"test_type": "failure", "preserve_for_debug": True}, 
                    {"test_type": "failure", "debug_info": "connection_timeout"}
                ],
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
                    "Simulated Failure",
                    False,
                    f"Document add failed: {add_response.status_code}",
                    time.time() - start_time
                )
            
            # Simulate a test failure - this data will be preserved
            return self.log_test_result(
                "Simulated Failure",
                False,  # ← Simulated failure
                "Simulated connection timeout during validation phase",
                time.time() - start_time
            )
            
        except Exception as e:
            return self.log_test_result(
                "Simulated Failure",
                False,
                f"Exception: {str(e)}",
                time.time() - start_time
            )

    def test_another_success(self):
        """Another successful test - data will be cleaned up"""
        logger.info("🧪 Testing Another Success (data will be cleaned)")
        
        self.start_test("Another Success")
        start_time = time.time()
        
        try:
            # Create collection
            collection_name = self.create_unique_collection_name("success2")
            
            create_response = self.make_request(
                'POST',
                f"{self.base_url}/api/v2/tenants/default_tenant/databases/default_database/collections",
                json={"name": collection_name}
            )
            
            if create_response.status_code not in [200, 201]:
                return self.log_test_result(
                    "Another Success",
                    False,
                    f"Collection creation failed: {create_response.status_code}",
                    time.time() - start_time
                )
            
            # Add multiple test documents
            doc_ids = [f"success2_doc_{i}_{uuid.uuid4().hex[:8]}" for i in range(3)]
            doc_data = {
                "embeddings": [[0.1*i, 0.2*i, 0.3*i, 0.4*i, 0.5*i] for i in range(1, 4)],
                "documents": [f"Success document {i+1}" for i in range(3)],
                "metadatas": [{"test_type": "success2", "doc_num": i+1} for i in range(3)],
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
                    "Another Success",
                    False,
                    f"Document add failed: {add_response.status_code}",
                    time.time() - start_time
                )
            
            # Test query operation
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
                    "Another Success",
                    False,
                    f"Query failed: {query_response.status_code}",
                    time.time() - start_time
                )
            
            query_result = query_response.json()
            result_count = len(query_result.get('ids', [[]])[0]) if query_result.get('ids') else 0
            
            # This test succeeds - data will be cleaned up
            return self.log_test_result(
                "Another Success",
                True,
                f"Added 3 documents, queried {result_count} results successfully",
                time.time() - start_time
            )
            
        except Exception as e:
            return self.log_test_result(
                "Another Success",
                False,
                f"Exception: {str(e)}",
                time.time() - start_time
            )

def main():
    """Run selective cleanup demonstration"""
    import argparse
    
    parser = argparse.ArgumentParser(description="Enhanced Selective Cleanup Test")
    parser.add_argument("--url", default="https://chroma-load-balancer.onrender.com", help="Load balancer URL")
    parser.add_argument("--force-cleanup", action="store_true", help="Force cleanup all data regardless of results")
    args = parser.parse_args()
    
    tester = SelectiveCleanupTest(args.url)
    
    logger.info("🚀 Starting Enhanced Selective Cleanup Test")
    logger.info(f"🌐 Target URL: {args.url}")
    logger.info("="*70)
    
    try:
        # Run test suite
        logger.info("\n1️⃣ Running Successful Operation Test...")
        test1_success = tester.test_successful_operation()
        
        logger.info("\n2️⃣ Running Simulated Failure Test...")
        test2_success = tester.test_simulated_failure()
        
        logger.info("\n3️⃣ Running Another Success Test...")
        test3_success = tester.test_another_success()
        
    except Exception as e:
        logger.error(f"❌ Test execution failed: {e}")
    
    # Print test summary
    overall_success = tester.print_test_summary()
    
    # Perform selective cleanup
    if args.force_cleanup:
        logger.info("\n🧹 FORCED CLEANUP REQUESTED")
        cleanup_results = tester.force_cleanup_all()
    else:
        logger.info("\n🧹 SELECTIVE CLEANUP")
        cleanup_results = tester.selective_cleanup()
    
    logger.info("\n" + "="*70)
    logger.info("🎯 SELECTIVE CLEANUP DEMONSTRATION COMPLETE")
    logger.info("="*70)
    
    if cleanup_results.get('tests_preserved', 0) > 0:
        logger.info("🔍 DEBUGGING GUIDANCE:")
        logger.info("   - Failed test data has been preserved")
        logger.info("   - Check the collections and documents listed above")
        logger.info("   - Use the load balancer endpoints to inspect the data")
        logger.info("   - Run with --force-cleanup to remove all data when done")
    else:
        logger.info("✅ All tests passed - no debugging data preserved")
    
    return overall_success

if __name__ == "__main__":
    success = main()
    exit(0 if success else 1) 