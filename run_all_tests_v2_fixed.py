#!/usr/bin/env python3
"""
Enhanced Unified WAL Load Balancer Test Suite for ChromaDB v2 API
Fixed to use correct v2 API endpoints and proper embedding handling
"""

import requests
import time
import uuid
import json
import logging
import argparse
from datetime import datetime
from typing import Dict, List

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class UnifiedWALTestSuite:
    def __init__(self, base_url="https://chroma-load-balancer.onrender.com"):
        self.base_url = base_url.rstrip('/')
        self.test_session_id = f"{int(time.time())}_{uuid.uuid4().hex[:8]}"
        self.test_collection_name = self.create_unique_collection_name()
        self.test_doc_ids = []
        self.results = []
        self.start_time = time.time()
        
        # Track created data for cleanup
        self.created_collections = set()
        self.created_documents = {}  # collection_name -> set of doc_ids
        
    def create_unique_collection_name(self, prefix="test_collection"):
        """Create unique collection name for this test session"""
        return f"{prefix}_{self.test_session_id}"
    
    def track_documents(self, collection_name, doc_ids):
        """Track document IDs for cleanup"""
        if collection_name not in self.created_documents:
            self.created_documents[collection_name] = set()
        self.created_documents[collection_name].update(doc_ids)
    
    def log_test_result(self, test_name, success, details="", duration=0):
        """Log test result with consistent formatting"""
        status = "✅ PASS" if success else "❌ FAIL"
        duration_str = f"({duration:.2f}s)" if duration > 0 else ""
        
        result_entry = {
            'test_name': test_name,
            'success': success,
            'details': details,
            'duration': duration
        }
        
        self.results.append(result_entry)
        logger.info(f"{status} {test_name}: {details} {duration_str}")
        
        return success
    
    def test_health_endpoints(self):
        """Test health and monitoring endpoints"""
        logger.info("\n🔍 Testing Health Endpoints")
        
        all_passed = True
        health_endpoints = [
            ("/health", "Health"),
            ("/status", "Status"),
            ("/wal/status", "WAL Status"),
            ("/metrics", "Metrics"),
            ("/collection/mappings", "Collection Mappings")
        ]
        
        for endpoint, name in health_endpoints:
            start_time = time.time()
            try:
                response = requests.get(f"{self.base_url}{endpoint}", timeout=30)
                duration = time.time() - start_time
                
                if response.status_code == 200:
                    if not self.log_test_result(f"Health: {name}", True, f"Status: {response.status_code}", duration):
                        all_passed = False
                else:
                    self.log_test_result(f"Health: {name}", False, f"Status: {response.status_code}", duration)
                    all_passed = False
                    
            except Exception as e:
                duration = time.time() - start_time
                self.log_test_result(f"Health: {name}", False, f"Error: {str(e)}", duration)
                all_passed = False
        
        return all_passed
    
    def test_collection_operations(self):
        """Test collection CRUD operations with v2 API"""
        logger.info("\n📚 Testing Collection Operations")
        
        all_passed = True
        
        # Test 1: List existing collections
        start_time = time.time()
        try:
            response = requests.get(
                f"{self.base_url}/api/v2/tenants/default_tenant/databases/default_database/collections", 
                timeout=30
            )
            duration = time.time() - start_time
            
            if response.status_code == 200:
                collections = response.json()
                if not self.log_test_result(
                    "Collections: List Collections", 
                    True, 
                    f"Found {len(collections)} collections", 
                    duration
                ):
                    all_passed = False
            else:
                self.log_test_result("Collections: List Collections", False, f"Status: {response.status_code}", duration)
                all_passed = False
                
        except Exception as e:
            duration = time.time() - start_time
            self.log_test_result("Collections: List Collections", False, f"Error: {str(e)}", duration)
            all_passed = False
        
        # Test 2: Create isolated test collection
        start_time = time.time()
        try:
            collection_payload = {
                "name": self.test_collection_name,
                "configuration_json": {
                    "hnsw": {
                        "space": "l2",
                        "ef_construction": 100,
                        "ef_search": 100,
                        "max_neighbors": 16,
                        "resize_factor": 1.2,
                        "sync_threshold": 1000
                    }
                },
                "metadata": {"test_session": self.test_session_id}
            }
            
            response = requests.post(
                f"{self.base_url}/api/v2/tenants/default_tenant/databases/default_database/collections",
                headers={"Content-Type": "application/json"},
                json=collection_payload,
                timeout=30
            )
            duration = time.time() - start_time
            
            if response.status_code in [200, 201]:
                result = response.json()
                collection_id = result.get('id', 'unknown')
                self.created_collections.add(self.test_collection_name)
                if not self.log_test_result(
                    "Collections: Create Test Collection", 
                    True, 
                    f"Created isolated test collection: {collection_id[:8]}...", 
                    duration
                ):
                    all_passed = False
            else:
                self.log_test_result("Collections: Create Test Collection", False, f"Status: {response.status_code}", duration)
                all_passed = False
                
        except Exception as e:
            duration = time.time() - start_time
            self.log_test_result("Collections: Create Test Collection", False, f"Error: {str(e)}", duration)
            all_passed = False
        
        return all_passed
    
    def test_document_operations(self):
        """Test document CRUD operations with correct v2 API format and embeddings"""
        logger.info("\n📄 Testing Document Operations")
        
        all_passed = True
        
        # Test 1: Add documents with explicit embeddings
        start_time = time.time()
        try:
            test_docs = {
                "embeddings": [[0.1, 0.2, 0.3, 0.4, 0.5], [0.6, 0.7, 0.8, 0.9, 1.0]],  # 5-dimensional
                "documents": [f"Test document 1 - Session {self.test_session_id}", f"Test document 2 - Session {self.test_session_id}"],
                "metadatas": [{"source": "test_suite", "session": self.test_session_id}, {"source": "test_suite", "session": self.test_session_id}],
                "ids": [f"test_doc_{self.test_session_id}_{uuid.uuid4().hex[:8]}", f"test_doc_{self.test_session_id}_{uuid.uuid4().hex[:8]}"]
            }
            
            self.track_documents(self.test_collection_name, test_docs["ids"])
            self.test_doc_ids = test_docs["ids"]
            
            response = requests.post(
                f"{self.base_url}/api/v2/tenants/default_tenant/databases/default_database/collections/{self.test_collection_name}/add",
                headers={"Content-Type": "application/json"},
                json=test_docs,
                timeout=30
            )
            duration = time.time() - start_time
            
            if response.status_code in [200, 201]:
                if not self.log_test_result(
                    "Documents: Add Isolated Test Documents",
                    True,
                    f"Added {len(test_docs['ids'])} documents with embeddings",
                    duration
                ):
                    all_passed = False
            else:
                self.log_test_result("Documents: Add Isolated Test Documents", False, f"Status: {response.status_code}", duration)
                all_passed = False
                
        except Exception as e:
            duration = time.time() - start_time
            self.log_test_result("Documents: Add Isolated Test Documents", False, f"Error: {str(e)}", duration)
            all_passed = False
        
        # Test 2: Get documents
        if self.test_doc_ids:
            start_time = time.time()
            try:
                get_payload = {"ids": self.test_doc_ids, "include": ["documents", "metadatas"]}
                response = requests.post(
                    f"{self.base_url}/api/v2/tenants/default_tenant/databases/default_database/collections/{self.test_collection_name}/get",
                    headers={"Content-Type": "application/json"},
                    json=get_payload,
                    timeout=30
                )
                duration = time.time() - start_time
                
                if response.status_code == 200:
                    result = response.json()
                    retrieved_count = len(result.get('ids', []))
                    if not self.log_test_result(
                        "Documents: Get Test Documents",
                        retrieved_count > 0,
                        f"Retrieved {retrieved_count} test documents",
                        duration
                    ):
                        all_passed = False
                else:
                    self.log_test_result("Documents: Get Test Documents", False, f"Status: {response.status_code}", duration)
                    all_passed = False
                    
            except Exception as e:
                duration = time.time() - start_time
                self.log_test_result("Documents: Get Test Documents", False, f"Error: {str(e)}", duration)
                all_passed = False
        
        # Test 3: Query documents with v2 API format
        start_time = time.time()
        try:
            query_payload = {
                "query_embeddings": [[0.1, 0.2, 0.3, 0.4, 0.5]],  # Correct v2 API format
                "n_results": 2,
                "include": ["documents", "metadatas", "distances"]
            }
            response = requests.post(
                f"{self.base_url}/api/v2/tenants/default_tenant/databases/default_database/collections/{self.test_collection_name}/query",
                headers={"Content-Type": "application/json"},
                json=query_payload,
                timeout=30
            )
            duration = time.time() - start_time
            
            if response.status_code == 200:
                result = response.json()
                found_results = len(result.get('ids', [[]])[0]) if result.get('ids') else 0
                if not self.log_test_result(
                    "Documents: Query Test Documents",
                    found_results > 0,
                    f"Query returned {found_results} results with distances",
                    duration
                ):
                    all_passed = False
            else:
                self.log_test_result("Documents: Query Test Documents", False, f"Status: {response.status_code}", duration)
                all_passed = False
                
        except Exception as e:
            duration = time.time() - start_time
            self.log_test_result("Documents: Query Test Documents", False, f"Error: {str(e)}", duration)
            all_passed = False
        
        return all_passed

    def comprehensive_cleanup(self):
        """Comprehensive cleanup with v2 API paths"""
        logger.info("\n🧹 Performing comprehensive test data cleanup...")
        
        cleanup_results = {
            'documents_deleted': 0,
            'collections_deleted': 0,
            'failed_document_cleanups': 0,
            'failed_collection_cleanups': 0
        }
        
        # Clean up collections only (simplified cleanup)
        for collection_name in self.created_collections:
            try:
                response = requests.delete(
                    f"{self.base_url}/api/v2/tenants/default_tenant/databases/default_database/collections/{collection_name}",
                    timeout=30
                )
                if response.status_code == 200:
                    cleanup_results['collections_deleted'] += 1
                    logger.info(f"✅ Deleted test collection: {collection_name}")
                else:
                    cleanup_results['failed_collection_cleanups'] += 1
                    logger.warning(f"⚠️ Failed to delete collection {collection_name}: {response.status_code}")
            except Exception as e:
                cleanup_results['failed_collection_cleanups'] += 1
                logger.warning(f"⚠️ Error deleting collection {collection_name}: {e}")
        
        logger.info(f"🧹 Cleanup Summary:")
        logger.info(f"   Collections deleted: {cleanup_results['collections_deleted']}")
        if cleanup_results['failed_collection_cleanups'] > 0:
            logger.warning(f"   Failed collection cleanups: {cleanup_results['failed_collection_cleanups']}")
        
        return cleanup_results

if __name__ == "__main__":
    # Quick test runner
    parser = argparse.ArgumentParser(description='Enhanced ChromaDB Test Suite')
    parser.add_argument('--url', default='https://chroma-load-balancer.onrender.com',
                        help='Base URL of the load balancer to test')
    
    args = parser.parse_args()
    
    test_suite = UnifiedWALTestSuite(args.url)
    
    logger.info("🚀 Running Enhanced Test Suite with v2 API")
    logger.info(f"📍 Testing URL: {args.url}")
    logger.info("=" * 60)
    
    # Run just the core tests for quick validation
    tests = [
        ("Health Endpoints", test_suite.test_health_endpoints),
        ("Collection Operations", test_suite.test_collection_operations), 
        ("Document Operations", test_suite.test_document_operations),
    ]
    
    all_passed = True
    
    try:
        for test_name, test_func in tests:
            logger.info(f"\n🧪 Running {test_name}...")
            result = test_func()
            if not result:
                all_passed = False
    finally:
        test_suite.comprehensive_cleanup()
    
    # Final report
    passed = sum(1 for r in test_suite.results if r['success'])
    total = len(test_suite.results)
    
    logger.info("\n" + "="*60)
    logger.info(f"🏁 Results: {passed}/{total} tests passed ({(passed/total)*100:.1f}%)")
    
    if all_passed:
        logger.info("🎉 All tests passed! System ready for production.")
    else:
        logger.info("⚠️ Some tests failed. Check logs above.")
        
    exit(0 if all_passed else 1) 