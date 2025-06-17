#!/usr/bin/env python3
"""
Test Document Operations Only - Isolate 503 errors for analysis
"""

import requests
import json
import uuid
import time
import logging
from test_base_cleanup import BulletproofTestBase

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class DocumentOperationsTest(BulletproofTestBase):
    """Focused testing of document operations to isolate 503 errors"""
    
    def __init__(self, base_url="https://chroma-load-balancer.onrender.com"):
        super().__init__(base_url, test_prefix="AUTOTEST_docops")

    def test_document_operations_detailed(self):
        """Test document operations with detailed logging and error analysis"""
        logger.info("🔍 Testing Document Operations with Detailed Analysis")
        
        start_time = time.time()
        collection_name = self.create_unique_collection_name("detailed")
        
        try:
            # Step 1: Create collection
            logger.info(f"  📚 Creating collection: {collection_name}")
            create_response = self.make_request(
                'POST',
                f"{self.base_url}/api/v2/tenants/default_tenant/databases/default_database/collections",
                json={"name": collection_name}
            )
            
            if create_response.status_code not in [200, 201]:
                return self.log_test_result(
                    "Document Operations - Collection Creation",
                    False,
                    f"Collection creation failed: {create_response.status_code}",
                    time.time() - start_time
                )
                
            collection_data = create_response.json()
            collection_uuid = collection_data.get('id')
            logger.info(f"  ✅ Collection created with UUID: {collection_uuid}")
            
            # Step 2: Test document ADD 
            logger.info("  📄 Testing document ADD...")
            doc_ids = [f"docops_test_{uuid.uuid4().hex[:8]}"]
            doc_data = {
                "embeddings": [[0.1, 0.2, 0.3, 0.4, 0.5]],
                "documents": ["Document operations test"],
                "metadatas": [{"test_type": "document_operations", "session": self.test_session_id}],
                "ids": doc_ids
            }
            
            self.track_documents(collection_name, doc_ids)
            
            # Log the exact request details
            add_url = f"{self.base_url}/api/v2/tenants/default_tenant/databases/default_database/collections/{collection_name}/add"
            logger.info(f"  🌐 ADD URL: {add_url}")
            logger.info(f"  📋 Collection name used: {collection_name}")
            logger.info(f"  📋 Collection UUID: {collection_uuid}")
            
            add_response = self.make_request(
                'POST',
                add_url,
                json=doc_data
            )
            
            logger.info(f"  📊 ADD Response: {add_response.status_code}")
            if add_response.status_code not in [200, 201]:
                logger.error(f"  ❌ ADD Error: {add_response.text[:500]}")
                return self.log_test_result(
                    "Document Operations - ADD",
                    False,
                    f"Document ADD failed: {add_response.status_code} - {add_response.text[:200]}",
                    time.time() - start_time
                )
            else:
                logger.info("  ✅ Document ADD successful")
            
            # Step 3: Test document GET
            logger.info("  📄 Testing document GET...")
            get_url = f"{self.base_url}/api/v2/tenants/default_tenant/databases/default_database/collections/{collection_name}/get"
            logger.info(f"  🌐 GET URL: {get_url}")
            
            get_response = self.make_request(
                'POST',
                get_url,
                json={"include": ["documents", "metadatas"]}
            )
            
            logger.info(f"  📊 GET Response: {get_response.status_code}")
            if get_response.status_code != 200:
                logger.error(f"  ❌ GET Error: {get_response.text[:500]}")
                return self.log_test_result(
                    "Document Operations - GET",
                    False,
                    f"Document GET failed: {get_response.status_code} - {get_response.text[:200]}",
                    time.time() - start_time
                )
            else:
                get_result = get_response.json()
                doc_count = len(get_result.get('ids', []))
                logger.info(f"  ✅ Document GET successful: {doc_count} documents")
            
            # Step 4: Test document QUERY
            logger.info("  📄 Testing document QUERY...")
            query_url = f"{self.base_url}/api/v2/tenants/default_tenant/databases/default_database/collections/{collection_name}/query"
            logger.info(f"  🌐 QUERY URL: {query_url}")
            
            query_response = self.make_request(
                'POST',
                query_url,
                json={
                    "query_embeddings": [[0.1, 0.2, 0.3, 0.4, 0.5]],
                    "n_results": 1,
                    "include": ["documents", "metadatas"]
                }
            )
            
            logger.info(f"  📊 QUERY Response: {query_response.status_code}")
            if query_response.status_code != 200:
                logger.error(f"  ❌ QUERY Error: {query_response.text[:500]}")
                return self.log_test_result(
                    "Document Operations - QUERY",
                    False,
                    f"Document QUERY failed: {query_response.status_code} - {query_response.text[:200]}",
                    time.time() - start_time
                )
            else:
                query_result = query_response.json()
                query_count = len(query_result.get('ids', [[]])[0]) if query_result.get('ids') else 0
                logger.info(f"  ✅ Document QUERY successful: {query_count} results")
            
            return self.log_test_result(
                "Document Operations - Full Suite",
                True,
                "All document operations successful",
                time.time() - start_time
            )
            
        except Exception as e:
            return self.log_test_result(
                "Document Operations - Full Suite", 
                False,
                f"Exception: {str(e)}",
                time.time() - start_time
            )

    def test_direct_vs_load_balancer_comparison(self):
        """Compare document operations: direct instance vs load balancer"""
        logger.info("🔍 Comparing Direct Instance vs Load Balancer Access")
        
        start_time = time.time()
        collection_name = self.create_unique_collection_name("comparison")
        
        try:
            # Create collection via load balancer
            logger.info(f"  📚 Creating collection via load balancer: {collection_name}")
            create_response = self.make_request(
                'POST',
                f"{self.base_url}/api/v2/tenants/default_tenant/databases/default_database/collections",
                json={"name": collection_name}
            )
            
            if create_response.status_code not in [200, 201]:
                return self.log_test_result(
                    "Direct vs Load Balancer Comparison",
                    False,
                    f"Collection creation failed: {create_response.status_code}",
                    time.time() - start_time
                )
            
            collection_data = create_response.json()
            collection_uuid = collection_data.get('id')
            logger.info(f"  ✅ Collection created with UUID: {collection_uuid}")
            
            # Test document operations via LOAD BALANCER using collection NAME
            logger.info("  🔄 Testing via LOAD BALANCER with collection NAME...")
            lb_doc_data = {
                "embeddings": [[0.1, 0.2, 0.3, 0.4, 0.5]],
                "documents": ["Load balancer test via name"],
                "metadatas": [{"source": "load_balancer_name"}],
                "ids": [f"lb_name_test_{uuid.uuid4().hex[:8]}"]
            }
            
            self.track_documents(collection_name, lb_doc_data["ids"])
            
            lb_add_response = self.make_request(
                'POST',
                f"{self.base_url}/api/v2/tenants/default_tenant/databases/default_database/collections/{collection_name}/add",
                json=lb_doc_data
            )
            
            logger.info(f"    Load Balancer (name): {lb_add_response.status_code}")
            if lb_add_response.status_code not in [200, 201]:
                logger.error(f"    Error: {lb_add_response.text[:300]}")
            
            # Test document operations via DIRECT PRIMARY using collection UUID
            logger.info("  🔄 Testing via DIRECT PRIMARY with collection UUID...")
            primary_url = "https://chroma-primary.onrender.com"
            direct_doc_data = {
                "embeddings": [[0.6, 0.7, 0.8, 0.9, 1.0]],
                "documents": ["Direct primary test via UUID"],
                "metadatas": [{"source": "direct_primary_uuid"}],
                "ids": [f"direct_uuid_test_{uuid.uuid4().hex[:8]}"]
            }
            
            self.track_documents(collection_name, direct_doc_data["ids"])
            
            direct_add_response = requests.post(
                f"{primary_url}/api/v2/tenants/default_tenant/databases/default_database/collections/{collection_uuid}/add",
                json=direct_doc_data,
                timeout=30
            )
            
            logger.info(f"    Direct Primary (UUID): {direct_add_response.status_code}")
            if direct_add_response.status_code not in [200, 201]:
                logger.error(f"    Error: {direct_add_response.text[:300]}")
            
            # Test document operations via DIRECT PRIMARY using collection NAME  
            logger.info("  🔄 Testing via DIRECT PRIMARY with collection NAME...")
            direct_name_doc_data = {
                "embeddings": [[0.2, 0.3, 0.4, 0.5, 0.6]],
                "documents": ["Direct primary test via name"],
                "metadatas": [{"source": "direct_primary_name"}],
                "ids": [f"direct_name_test_{uuid.uuid4().hex[:8]}"]
            }
            
            self.track_documents(collection_name, direct_name_doc_data["ids"])
            
            direct_name_add_response = requests.post(
                f"{primary_url}/api/v2/tenants/default_tenant/databases/default_database/collections/{collection_name}/add",
                json=direct_name_doc_data,
                timeout=30
            )
            
            logger.info(f"    Direct Primary (name): {direct_name_add_response.status_code}")
            if direct_name_add_response.status_code not in [200, 201]:
                logger.error(f"    Error: {direct_name_add_response.text[:300]}")
            
            # Analysis
            lb_success = lb_add_response.status_code in [200, 201]
            direct_uuid_success = direct_add_response.status_code in [200, 201]
            direct_name_success = direct_name_add_response.status_code in [200, 201]
            
            logger.info("  📊 COMPARISON RESULTS:")
            logger.info(f"    Load Balancer (name): {'✅ SUCCESS' if lb_success else '❌ FAILED'}")
            logger.info(f"    Direct Primary (UUID): {'✅ SUCCESS' if direct_uuid_success else '❌ FAILED'}")
            logger.info(f"    Direct Primary (name): {'✅ SUCCESS' if direct_name_success else '❌ FAILED'}")
            
            # Determine the issue pattern
            if direct_uuid_success and not direct_name_success and not lb_success:
                analysis = "UUID mapping issue - only direct UUID access works"
            elif direct_uuid_success and direct_name_success and not lb_success:
                analysis = "Load balancer routing issue - direct access works"
            elif lb_success:
                analysis = "Load balancer working correctly"
            else:
                analysis = "Broader system issue affecting all access methods"
            
            logger.info(f"  🎯 ANALYSIS: {analysis}")
            
            return self.log_test_result(
                "Direct vs Load Balancer Comparison",
                lb_success,
                analysis,
                time.time() - start_time
            )
            
        except Exception as e:
            return self.log_test_result(
                "Direct vs Load Balancer Comparison",
                False,
                f"Exception: {str(e)}",
                time.time() - start_time
            )

def main():
    """Run focused document operations tests"""
    import argparse
    
    parser = argparse.ArgumentParser(description="Test Document Operations Only")
    parser.add_argument("--url", default="https://chroma-load-balancer.onrender.com", help="Load balancer URL")
    args = parser.parse_args()
    
    tester = DocumentOperationsTest(args.url)
    
    logger.info("🚀 Starting Focused Document Operations Testing")
    logger.info(f"🌐 Target URL: {args.url}")
    logger.info("="*70)
    
    try:
        # Run focused tests
        logger.info("\n1️⃣ Detailed Document Operations Test...")
        test1_success = tester.test_document_operations_detailed()
        
        logger.info("\n2️⃣ Direct vs Load Balancer Comparison...")
        test2_success = tester.test_direct_vs_load_balancer_comparison()
        
    finally:
        # Always cleanup
        tester.comprehensive_cleanup()
    
    # Print results
    overall_success = tester.print_test_summary()
    
    logger.info("\n" + "="*70)
    logger.info("🎯 DOCUMENT OPERATIONS ANALYSIS COMPLETE")
    logger.info("="*70)
    
    if overall_success:
        logger.info("✅ All document operations working correctly")
    else:
        logger.error("❌ Document operations issues detected")
        logger.info("🔍 Check the detailed logs above for error patterns")
    
    return overall_success

if __name__ == "__main__":
    success = main()
    exit(0 if success else 1) 