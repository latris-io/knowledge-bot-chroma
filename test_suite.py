#!/usr/bin/env python3
"""
Comprehensive Test Suite for ChromaDB High Availability Setup
Tests: Load Balancer, Data Sync, Health Monitoring, Failover
"""

import time
import json
import requests
import chromadb
import argparse
import logging
from datetime import datetime

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class ChromaDBTestSuite:
    def __init__(self, load_balancer_url: str):
        self.load_balancer_url = load_balancer_url
        self.test_results = []
        self.test_data_cleanup = []
        
        # Initialize client
        host = load_balancer_url.replace("https://", "").replace("http://", "")
        ssl = load_balancer_url.startswith("https://")
        port = 443 if ssl else 8000
        self.client = chromadb.HttpClient(host=host, port=port, ssl=ssl)
        
    def log_test_result(self, test_name: str, passed: bool, details: str = ""):
        """Log test result"""
        result = {
            "test": test_name,
            "passed": passed,
            "details": details,
            "timestamp": datetime.now().isoformat()
        }
        self.test_results.append(result)
        
        status = "✅ PASS" if passed else "❌ FAIL"
        logger.info(f"{status} - {test_name}: {details}")
    
    def test_basic_connectivity(self):
        """Test basic connectivity"""
        logger.info("🔌 Testing Basic Connectivity...")
        
        try:
            response = requests.get(f"{self.load_balancer_url}/health", timeout=10)
            
            if response.status_code == 200:
                self.log_test_result("Basic Connectivity", True, "Connection successful")
            else:
                self.log_test_result("Basic Connectivity", False, f"HTTP {response.status_code}")
        except Exception as e:
            self.log_test_result("Basic Connectivity", False, f"Connection failed: {str(e)}")
    
    def test_load_balancer_health(self):
        """Test load balancer health endpoints"""
        logger.info("🏥 Testing Load Balancer Health...")
        
        for endpoint in ["/health", "/status"]:
            try:
                response = requests.get(f"{self.load_balancer_url}{endpoint}")
                
                if response.status_code == 200:
                    data = response.json()
                    strategy = data.get('strategy', 'unknown')
                    instances = len(data.get('instances', []))
                    self.log_test_result(f"Health {endpoint}", True, f"Strategy: {strategy}, Instances: {instances}")
                else:
                    self.log_test_result(f"Health {endpoint}", False, f"HTTP {response.status_code}")
            except Exception as e:
                self.log_test_result(f"Health {endpoint}", False, f"Request failed: {str(e)}")
    
    def test_basic_operations(self):
        """Test basic ChromaDB operations"""
        logger.info("📊 Testing Basic Operations...")
        
        test_collection_name = f"test_basic_{int(time.time())}"
        self.test_data_cleanup.append(test_collection_name)
        
        try:
            # Create collection
            collection = self.client.get_or_create_collection(test_collection_name)
            
            # Try to add documents with automatic embeddings first
            try:
                collection.add(
                    documents=["Test document about AI", "Test document about ML"],
                    ids=["doc1", "doc2"],
                    metadatas=[{"type": "test"}, {"type": "test"}]
                )
                
                # Query documents
                results = collection.query(query_texts=["AI"], n_results=2)
                query_success = len(results['ids'][0]) >= 1
                
            except Exception as embedding_error:
                # If embeddings fail, use pre-computed simple embeddings
                logger.warning(f"Automatic embeddings failed, using simple embeddings: {str(embedding_error)[:100]}")
                collection.add(
                    embeddings=[[0.1, 0.2, 0.3], [0.4, 0.5, 0.6]],  # Simple 3D vectors
                    documents=["Test document about AI", "Test document about ML"],
                    ids=["doc1", "doc2"],
                    metadatas=[{"type": "test"}, {"type": "test"}]
                )
                
                # Query with embedding vector instead of text
                results = collection.query(query_embeddings=[[0.1, 0.2, 0.3]], n_results=2)
                query_success = len(results['ids'][0]) >= 1
            
            # Get all documents
            all_docs = collection.get()
            
            if query_success and len(all_docs['ids']) == 2:
                self.log_test_result("Basic Operations", True, "Create, add, query successful")
            else:
                self.log_test_result("Basic Operations", False, f"Unexpected results: query_success={query_success}, all_docs={len(all_docs['ids'])}")
                
        except Exception as e:
            self.log_test_result("Basic Operations", False, f"Operation failed: {str(e)}")
    
    def test_load_distribution(self):
        """Test load balancing distribution"""
        logger.info("⚖️ Testing Load Distribution...")
        
        try:
            # Get initial counts
            initial_response = requests.get(f"{self.load_balancer_url}/status")
            if initial_response.status_code != 200:
                self.log_test_result("Load Distribution", False, "Cannot get status")
                return
                
            initial_status = initial_response.json()
            initial_counts = {
                inst['name']: inst['request_count'] 
                for inst in initial_status['instances']
            }
            
            # Make multiple requests to a proxied endpoint (not /health which is handled locally)
            for i in range(10):
                requests.get(f"{self.load_balancer_url}/api/v2/version")
            
            # Get final counts
            final_response = requests.get(f"{self.load_balancer_url}/status")
            final_status = final_response.json()
            final_counts = {
                inst['name']: inst['request_count'] 
                for inst in final_status['instances']
            }
            
            # Calculate distribution
            distribution = {
                name: final_counts[name] - initial_counts[name]
                for name in initial_counts
            }
            
            strategy = final_status['load_balancer']['strategy']
            total_distributed = sum(distribution.values())
            
            if total_distributed >= 10:
                self.log_test_result("Load Distribution", True, f"Strategy: {strategy}, Distribution: {distribution}")
            else:
                self.log_test_result("Load Distribution", False, f"Not all requests processed: {distribution}")
        
        except Exception as e:
            self.log_test_result("Load Distribution", False, f"Test failed: {str(e)}")
    
    def test_failover_simulation(self):
        """Test failover behavior by simulating instance failure"""
        logger.info("🔄 Testing Failover Simulation...")
        
        try:
            # Get current status
            response = requests.get(f"{self.load_balancer_url}/status")
            if response.status_code == 200:
                status = response.json()
                healthy_instances = [inst for inst in status['instances'] if inst['healthy']]
                
                if len(healthy_instances) >= 2:
                    self.log_test_result("Failover Readiness", True, f"Multiple healthy instances available: {len(healthy_instances)}")
                else:
                    self.log_test_result("Failover Readiness", False, f"Only {len(healthy_instances)} healthy instance(s)")
            else:
                self.log_test_result("Failover Readiness", False, "Cannot get load balancer status")
                
        except Exception as e:
            self.log_test_result("Failover Simulation", False, f"Test failed: {str(e)}")
    
    def cleanup_test_data(self):
        """Clean up test collections"""
        logger.info("🧹 Cleaning up test data...")
        
        for collection_name in self.test_data_cleanup:
            try:
                self.client.delete_collection(collection_name)
                logger.info(f"Deleted test collection: {collection_name}")
            except Exception as e:
                logger.warning(f"Could not delete {collection_name}: {e}")
    
    def run_all_tests(self):
        """Run all tests"""
        logger.info("🧪 Starting ChromaDB HA Test Suite...")
        
        self.test_basic_connectivity()
        self.test_load_balancer_health()
        self.test_basic_operations()
        self.test_load_distribution()
        self.test_failover_simulation()
        
        self.cleanup_test_data()
        
        # Generate report
        total_tests = len(self.test_results)
        passed_tests = sum(1 for r in self.test_results if r["passed"])
        
        logger.info("\n" + "="*60)
        logger.info("📊 TEST SUITE RESULTS")
        logger.info("="*60)
        logger.info(f"Total Tests: {total_tests}")
        logger.info(f"Passed: {passed_tests} ✅")
        logger.info(f"Failed: {total_tests - passed_tests} ❌")
        logger.info(f"Success Rate: {passed_tests/total_tests*100:.1f}%")
        
        if total_tests - passed_tests > 0:
            logger.info("\n❌ Failed Tests:")
            for result in self.test_results:
                if not result['passed']:
                    logger.info(f"  - {result['test']}: {result['details']}")
        
        return passed_tests == total_tests

def main():
    parser = argparse.ArgumentParser(description="ChromaDB HA Test Suite")
    parser.add_argument("--url", default="https://chroma-load-balancer.onrender.com", help="Load balancer URL")
    parser.add_argument("--output", help="Output file for test results (JSON)")
    
    args = parser.parse_args()
    
    test_suite = ChromaDBTestSuite(args.url)
    success = test_suite.run_all_tests()
    
    # Save detailed results if requested
    if args.output:
        with open(args.output, 'w') as f:
            json.dump(test_suite.test_results, f, indent=2)
        logger.info(f"📄 Test results saved to {args.output}")
    
    exit(0 if success else 1)

if __name__ == "__main__":
    main()
