#!/usr/bin/env python3
"""
Test Real-Time Collection ID Mapping - Critical functionality for CMS integration
Tests that collection names properly map to UUIDs for document operations through load balancer
Enhanced with bulletproof cleanup system
"""

import requests
import json
import uuid
import time
import logging
from test_base_cleanup import BulletproofTestBase

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class RealTimeMappingTestSuite(BulletproofTestBase):
    """Test suite for real-time collection ID mapping with bulletproof cleanup"""
    
    def __init__(self, base_url="https://chroma-load-balancer.onrender.com"):
        super().__init__(base_url, test_prefix="AUTOTEST_mapping")

    def test_real_time_mapping(self):
        """Test that collection names properly map to UUIDs for document operations"""
        logger.info("🆔 Testing Real-Time Collection Name→UUID Mapping")
        
        start_time = time.time()
        collection_name = self.create_unique_collection_name("mapping")
        
        try:
            # Step 1: Create collection through load balancer
            logger.info(f"  Creating collection: {collection_name}")
            create_response = self.make_request(
                'POST',
                f"{self.base_url}/api/v2/tenants/default_tenant/databases/default_database/collections",
                json={"name": collection_name}
            )
            
            if create_response.status_code not in [200, 201]:
                return self.log_test_result(
                    "Real-Time Mapping Test",
                    False,
                    f"Collection creation failed: {create_response.status_code}",
                    time.time() - start_time
                )
                
            logger.info(f"  ✅ Collection created successfully")
            
            # Step 2: Test document ADD using collection NAME (tests real-time mapping)
            logger.info("  Testing document ADD with collection name...")
            doc_ids = [f"mapping_test_{uuid.uuid4().hex[:8]}"]
            doc_data = {
                "embeddings": [[0.1, 0.2, 0.3, 0.4, 0.5]],
                "documents": ["Test mapping document"],
                "metadatas": [{"test_type": "real_time_mapping", "session": self.test_session_id}],
                "ids": doc_ids
            }
            
            # Track documents for cleanup
            self.track_documents(collection_name, doc_ids)
            
            add_response = self.make_request(
                'POST',
                f"{self.base_url}/api/v2/tenants/default_tenant/databases/default_database/collections/{collection_name}/add",
                json=doc_data
            )
            
            if add_response.status_code not in [200, 201]:
                return self.log_test_result(
                    "Real-Time Mapping Test",
                    False,
                    f"Document ADD failed: {add_response.status_code} - {add_response.text[:300]}",
                    time.time() - start_time
                )
                
            logger.info("  ✅ Document ADD successful with collection name")
            
            # Step 3: Test document GET with collection name
            logger.info("  Testing document GET with collection name...")
            get_response = self.make_request(
                'POST',
                f"{self.base_url}/api/v2/tenants/default_tenant/databases/default_database/collections/{collection_name}/get",
                json={"include": ["documents", "metadatas"]}
            )
            
            if get_response.status_code != 200:
                return self.log_test_result(
                    "Real-Time Mapping Test",
                    False,
                    f"Document GET failed: {get_response.status_code} - {get_response.text[:300]}",
                    time.time() - start_time
                )
                
            get_result = get_response.json()
            doc_count = len(get_result.get('ids', []))
            
            if doc_count == 0:
                return self.log_test_result(
                    "Real-Time Mapping Test",
                    False,
                    "No documents retrieved - mapping may have failed",
                    time.time() - start_time
                )
                
            logger.info(f"  ✅ Document GET successful: {doc_count} documents retrieved")
            
            # Step 4: Test document QUERY with collection name
            logger.info("  Testing document QUERY with collection name...")
            query_response = self.make_request(
                'POST',
                f"{self.base_url}/api/v2/tenants/default_tenant/databases/default_database/collections/{collection_name}/query",
                json={
                    "query_embeddings": [[0.1, 0.2, 0.3, 0.4, 0.5]],
                    "n_results": 1,
                    "include": ["documents", "metadatas"]
                }
            )
            
            if query_response.status_code != 200:
                return self.log_test_result(
                    "Real-Time Mapping Test",
                    False,
                    f"Document QUERY failed: {query_response.status_code} - {query_response.text[:300]}",
                    time.time() - start_time
                )
                
            query_result = query_response.json()
            query_count = len(query_result.get('ids', [[]])[0]) if query_result.get('ids') else 0
            
            if query_count == 0:
                return self.log_test_result(
                    "Real-Time Mapping Test",
                    False,
                    "No query results - mapping may have failed",
                    time.time() - start_time
                )
                
            logger.info(f"  ✅ Document QUERY successful: {query_count} results")
            
            logger.info("🎉 Real-time collection ID mapping working perfectly!")
            return self.log_test_result(
                "Real-Time Mapping Test",
                True,
                "All collection name→UUID mapping operations successful",
                time.time() - start_time
            )
            
        except Exception as e:
            return self.log_test_result(
                "Real-Time Mapping Test",
                False,
                f"Exception: {str(e)}",
                time.time() - start_time
            )

def main():
    """Run real-time mapping tests with comprehensive cleanup"""
    import sys
    import argparse
    
    parser = argparse.ArgumentParser(description="Test Real-Time Collection ID Mapping")
    parser.add_argument("--url", default="https://chroma-load-balancer.onrender.com", help="Load balancer URL")
    args = parser.parse_args()
    
    suite = RealTimeMappingTestSuite(args.url)
    
    logger.info("🚀 Starting Real-Time Collection ID Mapping Test")
    logger.info("="*60)
    
    try:
        success = suite.test_real_time_mapping()
    finally:
        # Always perform cleanup, even if tests failed
        cleanup_results = suite.comprehensive_cleanup()
    
    # Print test summary
    overall_success = suite.print_test_summary()
    
    if overall_success:
        logger.info("🎉 Real-time mapping test PASSED!")
        logger.info("🧹 Test data isolation and cleanup completed successfully.")
    else:
        logger.error("❌ Real-time mapping test FAILED!")
        logger.info("🧹 Test data cleanup completed to prevent pollution.")
    
    return overall_success

if __name__ == "__main__":
    success = main()
    exit(0 if success else 1) 