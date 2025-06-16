#!/usr/bin/env python3
"""
Base Test Class with Bulletproof Cleanup System
Combines best practices from all test files for consistent data isolation and cleanup
"""

import requests
import json
import uuid
import time
import logging
import atexit

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class BulletproofTestBase:
    """Base class providing bulletproof cleanup and data isolation for all tests"""
    
    def __init__(self, base_url="https://chroma-load-balancer.onrender.com", test_prefix="AUTOTEST"):
        self.base_url = base_url.rstrip('/')
        self.test_prefix = test_prefix
        self.test_session_id = f"{int(time.time())}_{uuid.uuid4().hex[:8]}"
        self.created_collections = set()
        self.created_documents = {}
        self.test_results = []
        
        # Register emergency cleanup to run even if tests fail catastrophically
        atexit.register(self.emergency_cleanup)
        
        logger.info(f"🆔 Test Session ID: {self.test_session_id}")
        logger.info(f"🧹 Bulletproof cleanup system enabled")
        
    def create_unique_collection_name(self, suffix=""):
        """Create a unique collection name with proper test isolation"""
        if suffix:
            collection_name = f"{self.test_prefix}_{suffix}_{self.test_session_id}"
        else:
            collection_name = f"{self.test_prefix}_collection_{self.test_session_id}"
        
        self.track_collection(collection_name)
        return collection_name
        
    def track_collection(self, collection_name):
        """Track collection for cleanup"""
        self.created_collections.add(collection_name)
        logger.debug(f"📝 Tracking collection: {collection_name}")
        
    def track_documents(self, collection_name, doc_ids):
        """Track document IDs for cleanup"""
        if collection_name not in self.created_documents:
            self.created_documents[collection_name] = set()
        
        if isinstance(doc_ids, str):
            doc_ids = [doc_ids]
        
        self.created_documents[collection_name].update(doc_ids)
        logger.debug(f"📄 Tracking {len(doc_ids)} documents in {collection_name}")
        
    def log_test_result(self, test_name, success, details="", duration=0):
        """Log and track test results"""
        status = "✅ PASS" if success else "❌ FAIL"
        logger.info(f"{status} {test_name} ({duration:.2f}s)")
        if details:
            logger.info(f"   Details: {details}")
        
        self.test_results.append({
            'test_name': test_name,
            'success': success,
            'details': details,
            'duration': duration
        })
        
        return success
    
    def make_request(self, method, url, **kwargs):
        """Make HTTP request with error handling and logging"""
        try:
            response = requests.request(method, url, timeout=30, **kwargs)
            return response
        except Exception as e:
            logger.error(f"❌ Request failed: {method} {url} - {e}")
            raise
    
    def comprehensive_cleanup(self):
        """Comprehensive cleanup of all test data"""
        logger.info("🧹 Performing comprehensive test data cleanup...")
        
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
                    logger.info(f"  Cleaning {len(doc_ids)} documents from {collection_name}")
                    delete_payload = {"ids": list(doc_ids)}
                    response = self.make_request(
                        'POST',
                        f"{self.base_url}/api/v2/tenants/default_tenant/databases/default_database/collections/{collection_name}/delete",
                        headers={"Content-Type": "application/json"},
                        json=delete_payload
                    )
                    
                    if response.status_code == 200:
                        cleanup_results['documents_deleted'] += len(doc_ids)
                        logger.info(f"  ✅ Deleted {len(doc_ids)} documents from {collection_name}")
                    else:
                        cleanup_results['failed_document_cleanups'] += 1
                        logger.warning(f"  ⚠️ Failed to delete documents from {collection_name}: {response.status_code}")
                        
                except Exception as e:
                    cleanup_results['failed_document_cleanups'] += 1
                    logger.warning(f"  ⚠️ Error deleting documents from {collection_name}: {e}")
        
        # Clean up collections
        for collection_name in self.created_collections:
            try:
                logger.info(f"  Cleaning collection: {collection_name}")
                response = self.make_request(
                    'DELETE',
                    f"{self.base_url}/api/v2/tenants/default_tenant/databases/default_database/collections/{collection_name}"
                )
                
                if response.status_code in [200, 404]:
                    cleanup_results['collections_deleted'] += 1
                    logger.info(f"  ✅ Deleted test collection: {collection_name}")
                else:
                    cleanup_results['failed_collection_cleanups'] += 1
                    logger.warning(f"  ⚠️ Failed to delete collection {collection_name}: {response.status_code}")
                    
            except Exception as e:
                cleanup_results['failed_collection_cleanups'] += 1
                logger.warning(f"  ⚠️ Error deleting collection {collection_name}: {e}")
        
        # Report cleanup results
        logger.info(f"🧹 Cleanup Summary:")
        logger.info(f"   Documents deleted: {cleanup_results['documents_deleted']}")
        logger.info(f"   Collections deleted: {cleanup_results['collections_deleted']}")
        if cleanup_results['failed_document_cleanups'] > 0:
            logger.warning(f"   Failed document cleanups: {cleanup_results['failed_document_cleanups']}")
        if cleanup_results['failed_collection_cleanups'] > 0:
            logger.warning(f"   Failed collection cleanups: {cleanup_results['failed_collection_cleanups']}")
        
        # Clear tracking after cleanup
        self.created_collections.clear()
        self.created_documents.clear()
        
        return cleanup_results

    def emergency_cleanup(self):
        """Emergency cleanup that runs on exit"""
        if hasattr(self, 'created_collections') and self.created_collections:
            logger.warning(f"🚨 Emergency cleanup: Removing {len(self.created_collections)} test collections")
            try:
                self.comprehensive_cleanup()
            except Exception as e:
                logger.error(f"❌ Emergency cleanup failed: {e}")
    
    def get_test_summary(self):
        """Get summary of test results"""
        if not self.test_results:
            return {"total": 0, "passed": 0, "failed": 0, "success_rate": 0.0}
        
        total = len(self.test_results)
        passed = sum(1 for result in self.test_results if result['success'])
        failed = total - passed
        success_rate = (passed / total) * 100 if total > 0 else 0.0
        
        return {
            "total": total,
            "passed": passed,
            "failed": failed,
            "success_rate": success_rate,
            "results": self.test_results
        }
    
    def print_test_summary(self):
        """Print comprehensive test summary"""
        summary = self.get_test_summary()
        
        logger.info("="*60)
        logger.info(f"📊 Test Summary for Session {self.test_session_id}")
        logger.info(f"   Total Tests: {summary['total']}")
        logger.info(f"   Passed: {summary['passed']}")
        logger.info(f"   Failed: {summary['failed']}")
        logger.info(f"   Success Rate: {summary['success_rate']:.1f}%")
        
        if summary['failed'] > 0:
            logger.info("\n❌ Failed Tests:")
            for result in summary['results']:
                if not result['success']:
                    logger.info(f"   - {result['test_name']}: {result['details']}")
        
        logger.info("="*60)
        
        return summary['success_rate'] == 100.0 