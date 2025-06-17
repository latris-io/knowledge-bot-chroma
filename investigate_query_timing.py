#!/usr/bin/env python3
"""
Investigate Document QUERY Timing Issue
Systematic investigation of why QUERY returns 0 results when ADD/GET work
"""

import requests
import json
import uuid
import time
import logging
from test_base_cleanup import BulletproofTestBase

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class QueryTimingInvestigation(BulletproofTestBase):
    """Investigation class for document QUERY timing issues"""
    
    def __init__(self, base_url="https://chroma-load-balancer.onrender.com"):
        super().__init__(base_url, test_prefix="AUTOTEST_query_debug")

    def test_detailed_query_investigation(self):
        """Detailed investigation of query timing and behavior"""
        logger.info("🔍 DETAILED QUERY INVESTIGATION")
        
        start_time = time.time()
        collection_name = self.create_unique_collection_name("query_timing")
        
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
                    "Query Investigation - Collection Creation",
                    False,
                    f"Collection creation failed: {create_response.status_code}",
                    time.time() - start_time
                )
                
            collection_data = create_response.json()
            collection_uuid = collection_data.get('id')
            logger.info(f"  ✅ Collection created: {collection_uuid}")
            
            # Step 2: Add documents with detailed logging
            logger.info("  📄 Adding test documents...")
            doc_ids = [f"query_test_{uuid.uuid4().hex[:8]}", f"query_test_{uuid.uuid4().hex[:8]}"]
            embeddings = [[0.1, 0.2, 0.3, 0.4, 0.5], [0.6, 0.7, 0.8, 0.9, 1.0]]
            documents = ["First test document for query timing", "Second test document for query timing"]
            
            doc_data = {
                "embeddings": embeddings,
                "documents": documents,
                "metadatas": [
                    {"test_type": "query_timing", "doc_index": 1, "session": self.test_session_id},
                    {"test_type": "query_timing", "doc_index": 2, "session": self.test_session_id}
                ],
                "ids": doc_ids
            }
            
            self.track_documents(collection_name, doc_ids)
            
            add_start = time.time()
            add_response = self.make_request(
                'POST',
                f"{self.base_url}/api/v2/tenants/default_tenant/databases/default_database/collections/{collection_name}/add",
                json=doc_data
            )
            add_duration = time.time() - add_start
            
            logger.info(f"  📊 ADD Response: {add_response.status_code} (took {add_duration:.2f}s)")
            if add_response.status_code not in [200, 201]:
                logger.error(f"  ❌ ADD failed: {add_response.text[:300]}")
                return self.log_test_result(
                    "Query Investigation - Document ADD",
                    False,
                    f"Document ADD failed: {add_response.status_code}",
                    time.time() - start_time
                )
            
            # Step 3: Test GET immediately (baseline)
            logger.info("  📄 Testing GET immediately after ADD...")
            get_start = time.time()
            get_response = self.make_request(
                'POST',
                f"{self.base_url}/api/v2/tenants/default_tenant/databases/default_database/collections/{collection_name}/get",
                json={"include": ["documents", "metadatas", "embeddings"]}
            )
            get_duration = time.time() - get_start
            
            logger.info(f"  📊 GET Response: {get_response.status_code} (took {get_duration:.2f}s)")
            if get_response.status_code == 200:
                get_result = get_response.json()
                get_count = len(get_result.get('ids', []))
                logger.info(f"  ✅ GET successful: {get_count} documents retrieved")
                logger.info(f"  📋 GET IDs: {get_result.get('ids', [])}")
            else:
                logger.error(f"  ❌ GET failed: {get_response.text[:300]}")
            
            # Step 4: Test QUERY immediately (this should fail)
            logger.info("  📄 Testing QUERY immediately after ADD...")
            query_embedding = [0.1, 0.2, 0.3, 0.4, 0.5]  # Same as first document
            
            immediate_query_start = time.time()
            immediate_query_response = self.make_request(
                'POST',
                f"{self.base_url}/api/v2/tenants/default_tenant/databases/default_database/collections/{collection_name}/query",
                json={
                    "query_embeddings": [query_embedding],
                    "n_results": 2,
                    "include": ["documents", "metadatas", "embeddings"]
                }
            )
            immediate_query_duration = time.time() - immediate_query_start
            
            logger.info(f"  📊 IMMEDIATE QUERY Response: {immediate_query_response.status_code} (took {immediate_query_duration:.2f}s)")
            immediate_results = 0
            if immediate_query_response.status_code == 200:
                immediate_query_result = immediate_query_response.json()
                immediate_results = len(immediate_query_result.get('ids', [[]])[0]) if immediate_query_result.get('ids') else 0
                logger.info(f"  📋 IMMEDIATE QUERY results: {immediate_results}")
                if immediate_results > 0:
                    logger.info(f"  📋 IMMEDIATE QUERY IDs: {immediate_query_result.get('ids', [[]])[0]}")
                else:
                    logger.warning(f"  ⚠️ IMMEDIATE QUERY returned empty results")
                    logger.debug(f"  🔍 Full response: {json.dumps(immediate_query_result, indent=2)}")
            else:
                logger.error(f"  ❌ IMMEDIATE QUERY failed: {immediate_query_response.text[:300]}")
            
            # Step 5: Wait and test QUERY with delays
            delay_intervals = [2, 5, 10]
            for delay in delay_intervals:
                logger.info(f"  ⏳ Waiting {delay}s before QUERY retry...")
                time.sleep(delay)
                
                delayed_query_start = time.time()
                delayed_query_response = self.make_request(
                    'POST',
                    f"{self.base_url}/api/v2/tenants/default_tenant/databases/default_database/collections/{collection_name}/query",
                    json={
                        "query_embeddings": [query_embedding],
                        "n_results": 2,
                        "include": ["documents", "metadatas", "embeddings"]
                    }
                )
                delayed_query_duration = time.time() - delayed_query_start
                
                logger.info(f"  📊 QUERY after {delay}s: {delayed_query_response.status_code} (took {delayed_query_duration:.2f}s)")
                if delayed_query_response.status_code == 200:
                    delayed_query_result = delayed_query_response.json()
                    delayed_results = len(delayed_query_result.get('ids', [[]])[0]) if delayed_query_result.get('ids') else 0
                    logger.info(f"  📋 QUERY results after {delay}s: {delayed_results}")
                    
                    if delayed_results > 0:
                        logger.info(f"  🎉 SUCCESS! QUERY working after {delay}s delay")
                        logger.info(f"  📋 QUERY IDs: {delayed_query_result.get('ids', [[]])[0]}")
                        
                        return self.log_test_result(
                            "Query Investigation - Timing Analysis",
                            True,
                            f"QUERY works after {delay}s delay ({delayed_results} results)",
                            time.time() - start_time
                        )
                    else:
                        logger.warning(f"  ⚠️ QUERY still empty after {delay}s")
                else:
                    logger.error(f"  ❌ QUERY failed after {delay}s: {delayed_query_response.text[:300]}")
            
            # If we get here, queries failed even with delays
            return self.log_test_result(
                "Query Investigation - Timing Analysis",
                False,
                f"QUERY failed even after 17s total delay (immediate: {immediate_results} results)",
                time.time() - start_time
            )
            
        except Exception as e:
            return self.log_test_result(
                "Query Investigation - Timing Analysis",
                False,
                f"Exception: {str(e)}",
                time.time() - start_time
            )

    def test_direct_vs_load_balancer_query(self):
        """Compare query behavior: direct instance vs load balancer"""
        logger.info("🔍 DIRECT VS LOAD BALANCER QUERY COMPARISON")
        
        start_time = time.time()
        collection_name = self.create_unique_collection_name("query_comparison")
        
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
                    "Query Comparison",
                    False,
                    f"Collection creation failed: {create_response.status_code}",
                    time.time() - start_time
                )
            
            collection_data = create_response.json()
            collection_uuid = collection_data.get('id')
            logger.info(f"  ✅ Collection created: {collection_uuid}")
            
            # Add document via load balancer
            doc_id = f"comparison_test_{uuid.uuid4().hex[:8]}"
            test_embedding = [0.2, 0.3, 0.4, 0.5, 0.6]
            
            doc_data = {
                "embeddings": [test_embedding],
                "documents": ["Comparison test document"],
                "metadatas": [{"test_type": "comparison", "source": "load_balancer"}],
                "ids": [doc_id]
            }
            
            self.track_documents(collection_name, [doc_id])
            
            add_response = self.make_request(
                'POST',
                f"{self.base_url}/api/v2/tenants/default_tenant/databases/default_database/collections/{collection_name}/add",
                json=doc_data
            )
            
            if add_response.status_code not in [200, 201]:
                return self.log_test_result(
                    "Query Comparison",
                    False,
                    f"Document ADD failed: {add_response.status_code}",
                    time.time() - start_time
                )
            
            logger.info("  ✅ Document added via load balancer")
            
            # Wait for sync
            logger.info("  ⏳ Waiting 10s for sync...")
            time.sleep(10)
            
            # Test QUERY via load balancer using collection NAME
            logger.info("  🔄 Testing QUERY via LOAD BALANCER (collection name)...")
            lb_query_response = self.make_request(
                'POST',
                f"{self.base_url}/api/v2/tenants/default_tenant/databases/default_database/collections/{collection_name}/query",
                json={
                    "query_embeddings": [test_embedding],
                    "n_results": 1,
                    "include": ["documents", "metadatas"]
                }
            )
            
            lb_results = 0
            if lb_query_response.status_code == 200:
                lb_query_result = lb_query_response.json()
                lb_results = len(lb_query_result.get('ids', [[]])[0]) if lb_query_result.get('ids') else 0
                logger.info(f"    Load Balancer QUERY: {lb_results} results")
            else:
                logger.error(f"    Load Balancer QUERY failed: {lb_query_response.status_code}")
            
            # Test QUERY via direct primary using collection UUID
            logger.info("  🔄 Testing QUERY via DIRECT PRIMARY (collection UUID)...")
            primary_url = "https://chroma-primary.onrender.com"
            
            direct_query_response = requests.post(
                f"{primary_url}/api/v2/tenants/default_tenant/databases/default_database/collections/{collection_uuid}/query",
                json={
                    "query_embeddings": [test_embedding],
                    "n_results": 1,
                    "include": ["documents", "metadatas"]
                },
                timeout=30
            )
            
            direct_results = 0
            if direct_query_response.status_code == 200:
                direct_query_result = direct_query_response.json()
                direct_results = len(direct_query_result.get('ids', [[]])[0]) if direct_query_result.get('ids') else 0
                logger.info(f"    Direct Primary QUERY: {direct_results} results")
            else:
                logger.error(f"    Direct Primary QUERY failed: {direct_query_response.status_code}")
            
            # Test QUERY via direct replica using collection UUID
            logger.info("  🔄 Testing QUERY via DIRECT REPLICA (collection UUID)...")
            replica_url = "https://chroma-replica.onrender.com"
            
            # First need to get the replica collection UUID from mapping
            mappings_response = self.make_request('GET', f"{self.base_url}/collection/mappings")
            replica_uuid = None
            
            if mappings_response.status_code == 200:
                mappings_data = mappings_response.json()
                for mapping in mappings_data.get('mappings', []):
                    if mapping['collection_name'] == collection_name:
                        replica_uuid = mapping['replica_collection_id']
                        break
            
            if replica_uuid:
                logger.info(f"    Found replica UUID: {replica_uuid[:8]}...")
                replica_query_response = requests.post(
                    f"{replica_url}/api/v2/tenants/default_tenant/databases/default_database/collections/{replica_uuid}/query",
                    json={
                        "query_embeddings": [test_embedding],
                        "n_results": 1,
                        "include": ["documents", "metadatas"]
                    },
                    timeout=30
                )
                
                replica_results = 0
                if replica_query_response.status_code == 200:
                    replica_query_result = replica_query_response.json()
                    replica_results = len(replica_query_result.get('ids', [[]])[0]) if replica_query_result.get('ids') else 0
                    logger.info(f"    Direct Replica QUERY: {replica_results} results")
                else:
                    logger.error(f"    Direct Replica QUERY failed: {replica_query_response.status_code}")
            else:
                logger.error("    Could not find replica UUID in mappings")
                replica_results = -1
            
            # Analysis
            logger.info("  📊 QUERY COMPARISON RESULTS:")
            logger.info(f"    Load Balancer (name): {lb_results} results")
            logger.info(f"    Direct Primary (UUID): {direct_results} results")
            logger.info(f"    Direct Replica (UUID): {replica_results} results")
            
            # Determine issue pattern
            if direct_results > 0 and lb_results == 0:
                analysis = "Load balancer query routing issue - direct works but LB fails"
            elif direct_results > 0 and replica_results == 0:
                analysis = "Replica sync issue - primary has data but replica doesn't"
            elif direct_results == 0 and replica_results == 0:
                analysis = "Embedding indexing issue - data exists but not queryable"
            elif lb_results > 0:
                analysis = "Query working correctly through load balancer"
            else:
                analysis = "Systematic query failure across all access methods"
            
            logger.info(f"  🎯 ANALYSIS: {analysis}")
            
            success = lb_results > 0
            return self.log_test_result(
                "Query Comparison",
                success,
                analysis,
                time.time() - start_time
            )
            
        except Exception as e:
            return self.log_test_result(
                "Query Comparison",
                False,
                f"Exception: {str(e)}",
                time.time() - start_time
            )

def main():
    """Run query timing investigation"""
    import argparse
    
    parser = argparse.ArgumentParser(description="Investigate Query Timing Issues")
    parser.add_argument("--url", default="https://chroma-load-balancer.onrender.com", help="Load balancer URL")
    args = parser.parse_args()
    
    investigator = QueryTimingInvestigation(args.url)
    
    logger.info("🚀 Starting Query Timing Investigation")
    logger.info(f"🌐 Target URL: {args.url}")
    logger.info("="*80)
    
    try:
        # Run investigations
        logger.info("\n1️⃣ Detailed Query Timing Investigation...")
        test1_success = investigator.test_detailed_query_investigation()
        
        logger.info("\n2️⃣ Direct vs Load Balancer Query Comparison...")
        test2_success = investigator.test_direct_vs_load_balancer_query()
        
    finally:
        # Always cleanup
        investigator.comprehensive_cleanup()
    
    # Print results
    overall_success = investigator.print_test_summary()
    
    logger.info("\n" + "="*80)
    logger.info("🎯 QUERY TIMING INVESTIGATION COMPLETE")
    logger.info("="*80)
    
    return overall_success

if __name__ == "__main__":
    success = main()
    exit(0 if success else 1) 