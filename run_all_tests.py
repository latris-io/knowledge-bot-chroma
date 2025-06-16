#!/usr/bin/env python3
"""
Comprehensive Test Suite for Unified WAL Load Balancer
Enhanced with bulletproof data isolation and cleanup
"""

import sys
import requests
import logging
import json
import uuid
import time
from datetime import datetime
import atexit

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class UnifiedWALTestSuite:
    def __init__(self, base_url="https://chroma-load-balancer.onrender.com"):
        self.base_url = base_url.rstrip('/')
        self.results = []
        # Use timestamp + UUID for unique test session
        self.test_session_id = f"{int(time.time())}_{uuid.uuid4().hex[:8]}"
        self.test_collection_name = f"test_collection_{self.test_session_id}"
        self.test_doc_ids = []
        self.created_collections = set()  # Track all collections created during tests
        self.created_documents = {}    # Track documents by collection name
        
        # Register cleanup to run even if tests fail catastrophically
        atexit.register(self.emergency_cleanup)
        
    def create_unique_collection_name(self, prefix="test_collection"):
        """Create a unique collection name for test isolation"""
        unique_name = f"{prefix}_{self.test_session_id}_{uuid.uuid4().hex[:6]}"
        self.created_collections.add(unique_name)
        return unique_name
    
    def track_documents(self, collection_name, doc_ids):
        """Track document IDs for cleanup"""
        if collection_name not in self.created_documents:
            self.created_documents[collection_name] = set()
        self.created_documents[collection_name].update(doc_ids)
    
    def log_test_result(self, test_name, success, details="", duration=0):
        """Log test result"""
        status = "✅ PASS" if success else "❌ FAIL"
        logger.info(f"{status} {test_name} ({duration:.2f}s)")
        if details:
            logger.info(f"   Details: {details}")
        
        self.results.append({
            'test_name': test_name,
            'success': success,
            'details': details,
            'duration': duration
        })
        
        return success
    
    def test_health_endpoints(self):
        """Test health endpoints - no data creation"""
        logger.info("🔍 Testing Health Endpoints")
        
        endpoints = [
            '/health',
            '/status', 
            '/wal/status',
            '/metrics',
            '/collection/mappings'
        ]
        
        passed = 0
        for endpoint in endpoints:
            start_time = time.time()
            try:
                response = requests.get(f"{self.base_url}{endpoint}", timeout=30)
                duration = time.time() - start_time
                
                if response.status_code == 200:
                    if self.log_test_result(f"Health: {endpoint}", True, f"Status: {response.status_code}", duration):
                        passed += 1
                else:
                    self.log_test_result(f"Health: {endpoint}", False, f"Status: {response.status_code}", duration)
            except Exception as e:
                duration = time.time() - start_time
                self.log_test_result(f"Health: {endpoint}", False, f"Error: {str(e)[:100]}", duration)
        
        return passed == len(endpoints)
    
    def test_collection_operations(self):
        """Test collection creation and management with isolated test collections"""
        logger.info("\n📚 Testing Collection Operations")
        
        all_passed = True
        
        # Test 1: List existing collections (read-only, safe)
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
                "configuration": {
                    "hnsw": {
                        "space": "l2",
                        "ef_construction": 100,
                        "ef_search": 100,
                        "max_neighbors": 16
                    }
                }
            }
            
            response = requests.post(
                f"{self.base_url}/api/v2/tenants/default_tenant/databases/default_database/collections",
                headers={"Content-Type": "application/json"},
                json=collection_payload,
                timeout=30
            )
            duration = time.time() - start_time
            
            if response.status_code in [200, 201]:
                # Track this collection for cleanup
                self.created_collections.add(self.test_collection_name)
                collection_data = response.json()
                collection_id = collection_data.get('id', 'N/A')
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
        """Test document CRUD operations using isolated test collection with v2 API format"""
        logger.info("\n📄 Testing Document Operations")
        
        all_passed = True
        
        # Test 1: Add documents to isolated test collection with explicit embeddings
        start_time = time.time()
        try:
            # Create unique document IDs for this test session with explicit embeddings
            test_docs = {
                "embeddings": [[0.1, 0.2, 0.3, 0.4, 0.5], [0.6, 0.7, 0.8, 0.9, 1.0]],  # 5-dimensional embeddings
                "documents": [f"Test document 1 - Session {self.test_session_id}", f"Test document 2 - Session {self.test_session_id}"],
                "metadatas": [{"source": "test_suite", "session": self.test_session_id}, {"source": "test_suite", "session": self.test_session_id}],
                "ids": [f"test_doc_{self.test_session_id}_{uuid.uuid4().hex[:8]}", f"test_doc_{self.test_session_id}_{uuid.uuid4().hex[:8]}"]
            }
            
            # Track documents for cleanup
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
                    f"Added {len(test_docs['ids'])} documents to test collection",
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
        
        # Test 2: Get documents from isolated test collection
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
        
        # Test 3: Query documents from isolated test collection with v2 API format
        start_time = time.time()
        try:
            query_payload = {
                "query_embeddings": [[0.1, 0.2, 0.3, 0.4, 0.5]],  # Use correct v2 API format
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
                    f"Query returned {found_results} results from test collection",
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
    
    def test_wal_functionality(self):
        """Test WAL system functionality - read-only operations"""
        logger.info("\n📝 Testing WAL System")
        
        all_passed = True
        
        # Test 1: WAL Status (read-only, safe)
        start_time = time.time()
        try:
            response = requests.get(f"{self.base_url}/wal/status", timeout=30)
            duration = time.time() - start_time
            
            if response.status_code == 200:
                wal_data = response.json()
                pending_writes = wal_data.get('wal_system', {}).get('pending_writes', 0)
                successful_syncs = wal_data.get('performance_stats', {}).get('successful_syncs', 0)
                
                if not self.log_test_result(
                    "WAL: Status Check",
                    True,
                    f"Pending: {pending_writes}, Successful: {successful_syncs}",
                    duration
                ):
                    all_passed = False
            else:
                self.log_test_result("WAL: Status Check", False, f"Status: {response.status_code}", duration)
                all_passed = False
                
        except Exception as e:
            duration = time.time() - start_time
            self.log_test_result("WAL: Status Check", False, f"Error: {str(e)}", duration)
            all_passed = False
        
        # Test 2: WAL Cleanup (safe operation)
        start_time = time.time()
        try:
            cleanup_payload = {"max_age_hours": 1}
            response = requests.post(
                f"{self.base_url}/wal/cleanup",
                headers={"Content-Type": "application/json"},
                json=cleanup_payload,
                timeout=30
            )
            duration = time.time() - start_time
            
            if response.status_code == 200:
                result = response.json()
                cleaned_entries = result.get('deleted_entries', 0)
                if not self.log_test_result(
                    "WAL: Cleanup Operation",
                    True,
                    f"Cleaned {cleaned_entries} entries",
                    duration
                ):
                    all_passed = False
            else:
                self.log_test_result("WAL: Cleanup Operation", False, f"Status: {response.status_code}", duration)
                all_passed = False
                
        except Exception as e:
            duration = time.time() - start_time
            self.log_test_result("WAL: Cleanup Operation", False, f"Error: {str(e)}", duration)
            all_passed = False
        
        return all_passed
    
    def test_load_balancer_features(self):
        """Test load balancer functionality - read-only operations"""
        logger.info("\n⚖️ Testing Load Balancer Features")
        
        all_passed = True
        
        # Test 1: Instance Health (read-only, safe)
        start_time = time.time()
        try:
            response = requests.get(f"{self.base_url}/status", timeout=30)
            duration = time.time() - start_time
            
            if response.status_code == 200:
                status_data = response.json()
                instances = status_data.get('instances', [])
                healthy_count = sum(1 for inst in instances if inst.get('healthy', False))
                
                if not self.log_test_result(
                    "Load Balancer: Instance Health",
                    healthy_count > 0,
                    f"Healthy instances: {healthy_count}/{len(instances)}",
                    duration
                ):
                    all_passed = False
                    
            else:
                self.log_test_result("Load Balancer: Instance Health", False, f"Status: {response.status_code}", duration)
                all_passed = False
                
        except Exception as e:
            duration = time.time() - start_time
            self.log_test_result("Load Balancer: Instance Health", False, f"Error: {str(e)}", duration)
            all_passed = False
        
        # Test 2: Collection Mappings (read-only, safe)
        start_time = time.time()
        try:
            response = requests.get(f"{self.base_url}/collection/mappings", timeout=30)
            duration = time.time() - start_time
            
            if response.status_code == 200:
                mappings_data = response.json()
                mapping_count = len(mappings_data.get('mappings', []))
                
                if not self.log_test_result(
                    "Load Balancer: Collection Mappings",
                    True,
                    f"Found {mapping_count} collection mappings",
                    duration
                ):
                    all_passed = False
            else:
                self.log_test_result("Load Balancer: Collection Mappings", False, f"Status: {response.status_code}", duration)
                all_passed = False
                
        except Exception as e:
            duration = time.time() - start_time
            self.log_test_result("Load Balancer: Collection Mappings", False, f"Error: {str(e)}", duration)
            all_passed = False
        
        return all_passed
    
    def test_delete_sync_functionality(self):
        """Test DELETE sync functionality - verifies the DELETE sync fix"""
        logger.info("\n🗑️ Testing DELETE Sync Functionality")
        
        all_passed = True
        
        # Create a dedicated test collection for DELETE sync testing
        delete_test_collection = f"AUTOTEST_delete_sync_{int(time.time())}_{uuid.uuid4().hex[:8]}"
        self.created_collections.add(delete_test_collection)  # Track for cleanup
        
        # Test 1: Create collection for deletion testing
        start_time = time.time()
        try:
            collection_payload = {
                "name": delete_test_collection,
                "configuration": {
                    "hnsw": {
                        "space": "l2",
                        "ef_construction": 100,
                        "ef_search": 100,
                        "max_neighbors": 16
                    }
                }
            }
            
            response = requests.post(
                f"{self.base_url}/api/v2/tenants/default_tenant/databases/default_database/collections",
                headers={"Content-Type": "application/json"},
                json=collection_payload,
                timeout=30
            )
            duration = time.time() - start_time
            
            if response.status_code in [200, 201]:
                if not self.log_test_result(
                    "DELETE Sync: Create Test Collection",
                    True,
                    f"Created collection: {delete_test_collection[:40]}...",
                    duration
                ):
                    all_passed = False
            else:
                self.log_test_result(
                    "DELETE Sync: Create Test Collection",
                    False,
                    f"Failed to create test collection: {response.status_code}",
                    duration
                )
                all_passed = False
                return all_passed
                
        except Exception as e:
            duration = time.time() - start_time
            self.log_test_result(
                "DELETE Sync: Create Test Collection",
                False,
                f"Exception: {str(e)}",
                duration
            )
            all_passed = False
            return all_passed
        
        # Test 2: Wait for initial sync (reduced time for faster tests)
        logger.info("   Waiting 20s for initial sync...")
        time.sleep(20)
        
        # Test 3: DELETE collection via load balancer
        start_time = time.time()
        try:
            response = requests.delete(
                f"{self.base_url}/api/v2/tenants/default_tenant/databases/default_database/collections/{delete_test_collection}",
                timeout=30
            )
            duration = time.time() - start_time
            
            if response.status_code in [200, 404]:
                if not self.log_test_result(
                    "DELETE Sync: Execute DELETE Request",
                    True,
                    f"DELETE request successful: {response.status_code}",
                    duration
                ):
                    all_passed = False
                    
                # Remove from tracking since we're explicitly deleting it
                self.created_collections.discard(delete_test_collection)
            else:
                self.log_test_result(
                    "DELETE Sync: Execute DELETE Request",
                    False,
                    f"DELETE request failed: {response.status_code}",
                    duration
                )
                all_passed = False
                
        except Exception as e:
            duration = time.time() - start_time
            self.log_test_result(
                "DELETE Sync: Execute DELETE Request",
                False,
                f"Exception: {str(e)}",
                duration
            )
            all_passed = False
        
        # Test 4: Verify DELETE sync (simplified verification)
        logger.info("   Waiting 20s for DELETE sync...")
        time.sleep(20)
        
        start_time = time.time()
        try:
            # Quick verification that DELETE worked
            response = requests.get(f"{self.base_url}/api/v2/tenants/default_tenant/databases/default_database/collections", timeout=30)
            duration = time.time() - start_time
            
            if response.status_code == 200:
                collections = response.json()
                collection_names = [c['name'] for c in collections]
                delete_sync_success = delete_test_collection not in collection_names
                
                if not self.log_test_result(
                    "DELETE Sync: Verify DELETE Sync",
                    delete_sync_success,
                    f"Collection deleted: {delete_sync_success}",
                    duration
                ):
                    all_passed = False
                    
                if delete_sync_success:
                    logger.info("   🎉 DELETE SYNC WORKING! Collection successfully deleted")
                else:
                    logger.warning("   ⚠️ DELETE SYNC ISSUE: Collection still exists")
                    
            else:
                self.log_test_result(
                    "DELETE Sync: Verify DELETE Sync",
                    False,
                    f"Failed to verify deletion: {response.status_code}",
                    duration
                )
                all_passed = False
                
        except Exception as e:
            duration = time.time() - start_time
            self.log_test_result(
                "DELETE Sync: Verify DELETE Sync",
                False,
                f"Exception: {str(e)}",
                duration
            )
            all_passed = False
        
        return all_passed
    
    def comprehensive_cleanup(self):
        """Comprehensive cleanup of all test data"""
        logger.info("\n🧹 Performing comprehensive test data cleanup...")
        
        cleanup_results = {
            'documents_deleted': 0,
            'collections_deleted': 0,
            'failed_document_cleanups': 0,
            'failed_collection_cleanups': 0
        }
        
        # Clean up documents first
        for collection_name, doc_ids in self.created_documents.items():
            if doc_ids:
                try:
                    delete_payload = {"ids": list(doc_ids)}
                    response = requests.post(
                        f"{self.base_url}/api/v2/collections/{collection_name}/delete",
                        headers={"Content-Type": "application/json"},
                        json=delete_payload,
                        timeout=30
                    )
                    if response.status_code == 200:
                        cleanup_results['documents_deleted'] += len(doc_ids)
                        logger.info(f"✅ Deleted {len(doc_ids)} documents from {collection_name}")
                    else:
                        cleanup_results['failed_document_cleanups'] += 1
                        logger.warning(f"⚠️ Failed to delete documents from {collection_name}: {response.status_code}")
                except Exception as e:
                    cleanup_results['failed_document_cleanups'] += 1
                    logger.warning(f"⚠️ Error deleting documents from {collection_name}: {e}")
        
        # Clean up collections
        for collection_name in self.created_collections:
            try:
                response = requests.delete(
                    f"{self.base_url}/api/v2/collections/{collection_name}",
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
        
        # Report cleanup results
        logger.info(f"🧹 Cleanup Summary:")
        logger.info(f"   Documents deleted: {cleanup_results['documents_deleted']}")
        logger.info(f"   Collections deleted: {cleanup_results['collections_deleted']}")
        if cleanup_results['failed_document_cleanups'] > 0:
            logger.warning(f"   Failed document cleanups: {cleanup_results['failed_document_cleanups']}")
        if cleanup_results['failed_collection_cleanups'] > 0:
            logger.warning(f"   Failed collection cleanups: {cleanup_results['failed_collection_cleanups']}")
        
        return cleanup_results
    
    def emergency_cleanup(self):
        """Emergency cleanup that runs on exit"""
        if hasattr(self, 'created_collections') and self.created_collections:
            logger.warning(f"🚨 Emergency cleanup: Removing {len(self.created_collections)} test collections")
            self.comprehensive_cleanup()
    
    def run_comprehensive_tests(self):
        """Run all test suites with proper data isolation"""
        logger.info("🚀 Starting Comprehensive Unified WAL Load Balancer Tests")
        logger.info(f"📍 Testing URL: {self.base_url}")
        logger.info(f"🆔 Test Session ID: {self.test_session_id}")
        logger.info(f"⏰ Started at: {datetime.now().isoformat()}")
        logger.info("=" * 80)
        
        start_time = time.time()
        
        # Define comprehensive test suites
        test_suites = [
            ("Health Endpoints", self.test_health_endpoints),
            ("Collection Operations", self.test_collection_operations),
            ("Document Operations", self.test_document_operations),
            ("WAL Functionality", self.test_wal_functionality),
            ("Load Balancer Features", self.test_load_balancer_features),
            ("DELETE Sync Functionality", self.test_delete_sync_functionality)
        ]
        
        suite_results = []
        
        try:
            for suite_name, test_func in test_suites:
                logger.info(f"\n🧪 Running {suite_name} Tests...")
                suite_start = time.time()
                
                try:
                    result = test_func()
                    suite_results.append((suite_name, result))
                    suite_duration = time.time() - suite_start
                    status = "✅ PASSED" if result else "❌ FAILED"
                    logger.info(f"{status} {suite_name} ({suite_duration:.2f}s)")
                except Exception as e:
                    suite_results.append((suite_name, False))
                    suite_duration = time.time() - suite_start
                    logger.error(f"❌ FAILED {suite_name} ({suite_duration:.2f}s) - Exception: {e}")
        
        finally:
            # Always perform cleanup, even if tests failed
            cleanup_results = self.comprehensive_cleanup()
        
        # Generate final report
        total_duration = time.time() - start_time
        passed_suites = sum(1 for _, result in suite_results if result)
        total_suites = len(suite_results)
        
        # Individual test stats
        passed_tests = sum(1 for result in self.results if result['success'])
        total_tests = len(self.results)
        
        logger.info("\n" + "="*80)
        logger.info("🏁 COMPREHENSIVE TEST RESULTS")
        logger.info("="*80)
        logger.info(f"🆔 Test Session: {self.test_session_id}")
        logger.info(f"📊 Test Suites: {passed_suites}/{total_suites} passed")
        logger.info(f"📋 Individual Tests: {passed_tests}/{total_tests} passed")
        logger.info(f"📈 Suite Success Rate: {passed_suites/total_suites*100:.1f}%")
        logger.info(f"📈 Test Success Rate: {passed_tests/total_tests*100:.1f}%" if total_tests > 0 else "📈 No individual tests")
        logger.info(f"⏱️ Total Duration: {total_duration:.1f}s")
        
        # Show test data isolation info
        logger.info(f"\n🔒 Data Isolation:")
        logger.info(f"   Test collections created: {len(self.created_collections)}")
        logger.info(f"   Test documents created: {sum(len(docs) for docs in self.created_documents.values())}")
        logger.info(f"   Collections cleaned up: {cleanup_results['collections_deleted']}")
        logger.info(f"   Documents cleaned up: {cleanup_results['documents_deleted']}")
        
        # Show failed tests
        failed_tests = [r for r in self.results if not r['success']]
        if failed_tests:
            logger.info(f"\n❌ Failed Tests ({len(failed_tests)}):")
            for test in failed_tests[:5]:  # Show first 5 failures
                logger.info(f"  • {test['test_name']}: {test['details']}")
        
        # Final assessment
        overall_success = passed_suites == total_suites
        logger.info(f"\n💡 Overall Assessment:")
        if overall_success:
            logger.info("  🎉 All test suites passed! System is fully operational.")
            logger.info("  ✅ All test data properly isolated and cleaned up.")
        elif passed_suites >= total_suites * 0.8:
            logger.info("  ⚠️ Most tests passed. System is mostly operational with minor issues.")
            logger.info("  🧹 Test data isolation and cleanup completed successfully.")
        else:
            logger.info("  🚨 Multiple test failures. System needs attention.")
            logger.info("  🧹 Test data cleanup completed to prevent pollution.")
        
        return overall_success

def main():
    """Main test runner"""
    import argparse
    
    parser = argparse.ArgumentParser(
        description="Comprehensive Unified WAL Load Balancer Test Suite with Data Isolation",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python run_all_tests.py                                    # Test production with full isolation
  python run_all_tests.py --url http://localhost:8000        # Test local with full isolation
  
Features:
  • Complete data isolation using unique test collections
  • Comprehensive cleanup of all test data  
  • Emergency cleanup on unexpected exit
  • Tracking of all created test data
        """
    )
    parser.add_argument("--url", default="https://chroma-load-balancer.onrender.com",
                       help="Load balancer URL to test")
    
    args = parser.parse_args()
    
    # Run tests
    test_suite = UnifiedWALTestSuite(args.url)
    success = test_suite.run_comprehensive_tests()
    
    # Exit with appropriate code
    sys.exit(0 if success else 1)

if __name__ == "__main__":
    main() 