#!/usr/bin/env python3
"""
Enhanced Test Base Class with Comprehensive Cleanup System
Only cleans up data from successful tests, preserves failed test data for debugging
NOW INCLUDES POSTGRESQL CLEANUP - removes ALL test data everywhere
"""

import requests
import json
import uuid
import time
import logging
import atexit
import os
from collections import defaultdict

# PostgreSQL support
try:
    import psycopg2
    POSTGRESQL_AVAILABLE = True
except ImportError:
    POSTGRESQL_AVAILABLE = False

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class EnhancedTestBase:
    """Enhanced base class with comprehensive cleanup - preserves failed test data for debugging
    NOW INCLUDES POSTGRESQL CLEANUP for complete test data removal"""
    
    def __init__(self, base_url="https://chroma-load-balancer.onrender.com", test_prefix="AUTOTEST"):
        self.base_url = base_url.rstrip('/')
        self.test_prefix = test_prefix
        self.test_session_id = f"{int(time.time())}_{uuid.uuid4().hex[:8]}"
        
        # PostgreSQL connection setup
        self.database_url = os.getenv('DATABASE_URL', 
            'postgresql://unified_wal_user:wal_secure_2024@dpg-cu5l49bv2p9s73c7l1u0-a.oregon-postgres.render.com/unified_wal_db')
        self.postgresql_enabled = POSTGRESQL_AVAILABLE
        
        # Test data tracking - organized by test name
        self.test_data = defaultdict(lambda: {
            'collections': set(),
            'documents': defaultdict(set),
            'success': None,  # None = not finished, True = passed, False = failed
            'details': '',
            'duration': 0
        })
        
        # Overall test tracking
        self.test_results = []
        self.current_test = None
        
        # Register emergency cleanup
        atexit.register(self.emergency_cleanup)
        
        logger.info(f"🆔 Test Session ID: {self.test_session_id}")
        logger.info(f"🧹 Enhanced comprehensive cleanup system enabled")
        logger.info(f"🔍 Failed test data will be preserved for debugging")
        if self.postgresql_enabled:
            logger.info(f"🗄️ PostgreSQL cleanup enabled - all test data will be removed")
        else:
            logger.warning(f"⚠️ PostgreSQL cleanup disabled - install psycopg2 for complete cleanup")
    
    def get_db_connection(self):
        """Get PostgreSQL database connection"""
        if not self.postgresql_enabled:
            raise Exception("PostgreSQL not available - install psycopg2")
        try:
            return psycopg2.connect(self.database_url)
        except Exception as e:
            logger.error(f"❌ Database connection failed: {e}")
            raise
    
    def cleanup_postgresql_test_data(self, test_collections, is_selective=True):
        """Clean up PostgreSQL test data with selective or comprehensive approach"""
        if not self.postgresql_enabled:
            logger.warning("⚠️ PostgreSQL cleanup skipped - psycopg2 not available")
            return {'mappings_deleted': 0, 'wal_entries_deleted': 0, 'success': False}
        
        try:
            with self.get_db_connection() as conn:
                with conn.cursor() as cur:
                    mappings_deleted = 0
                    wal_entries_deleted = 0
                    
                    if is_selective:
                        # Selective cleanup - only remove specific test collections
                        logger.debug("🗄️ PostgreSQL selective cleanup...")
                        for collection_name in test_collections:
                            # Delete collection mappings
                            cur.execute(
                                "DELETE FROM collection_id_mapping WHERE collection_name = %s",
                                (collection_name,)
                            )
                            mappings_deleted += cur.rowcount
                            
                            # Delete WAL entries
                            cur.execute(
                                "DELETE FROM unified_wal_writes WHERE collection_name = %s",
                                (collection_name,)
                            )
                            wal_entries_deleted += cur.rowcount
                    else:
                        # Comprehensive cleanup - remove all test data
                        logger.debug("🗄️ PostgreSQL comprehensive cleanup...")
                        
                        # Delete all test collection mappings
                        cur.execute(
                            "DELETE FROM collection_id_mapping WHERE collection_name LIKE %s",
                            (f"{self.test_prefix}_%",)
                        )
                        mappings_deleted = cur.rowcount
                        
                        # Delete all test WAL entries
                        cur.execute(
                            "DELETE FROM unified_wal_writes WHERE collection_name LIKE %s OR collection_name LIKE %s",
                            (f"{self.test_prefix}_%", "test_%")
                        )
                        wal_entries_deleted = cur.rowcount
                        
                        # Also clean by session ID pattern
                        cur.execute(
                            "DELETE FROM collection_id_mapping WHERE collection_name LIKE %s",
                            (f"%{self.test_session_id}%",)
                        )
                        mappings_deleted += cur.rowcount
                        
                        cur.execute(
                            "DELETE FROM unified_wal_writes WHERE collection_name LIKE %s",
                            (f"%{self.test_session_id}%",)
                        )
                        wal_entries_deleted += cur.rowcount
                    
                    conn.commit()
                    
                    if mappings_deleted > 0 or wal_entries_deleted > 0:
                        logger.debug(f"     🗄️ PostgreSQL cleanup: {mappings_deleted} mappings, {wal_entries_deleted} WAL entries deleted")
                    
                    return {
                        'mappings_deleted': mappings_deleted,
                        'wal_entries_deleted': wal_entries_deleted,
                        'success': True
                    }
                    
        except Exception as e:
            logger.error(f"❌ PostgreSQL cleanup failed: {e}")
            return {'mappings_deleted': 0, 'wal_entries_deleted': 0, 'success': False, 'error': str(e)}
    
    def start_test(self, test_name):
        """Start tracking a new test"""
        self.current_test = test_name
        logger.debug(f"🧪 Starting test: {test_name}")
        
    def create_unique_collection_name(self, suffix=""):
        """Create a unique collection name with proper test isolation"""
        if suffix:
            collection_name = f"{self.test_prefix}_{suffix}_{self.test_session_id}"
        else:
            collection_name = f"{self.test_prefix}_collection_{self.test_session_id}"
        
        self.track_collection(collection_name)
        return collection_name
        
    def track_collection(self, collection_name):
        """Track collection for the current test"""
        if self.current_test:
            self.test_data[self.current_test]['collections'].add(collection_name)
            logger.debug(f"📝 Tracking collection {collection_name} for test {self.current_test}")
        else:
            # Fallback for collections created outside test context
            self.test_data['_global']['collections'].add(collection_name)
            logger.debug(f"📝 Tracking collection {collection_name} globally")
        
    def track_documents(self, collection_name, doc_ids):
        """Track document IDs for the current test"""
        if isinstance(doc_ids, str):
            doc_ids = [doc_ids]
        
        test_key = self.current_test if self.current_test else '_global'
        self.test_data[test_key]['documents'][collection_name].update(doc_ids)
        logger.debug(f"📄 Tracking {len(doc_ids)} documents in {collection_name} for test {test_key}")
        
    def log_test_result(self, test_name, success, details="", duration=0):
        """Log and track test results with selective cleanup planning"""
        status = "✅ PASS" if success else "❌ FAIL"
        logger.info(f"{status} {test_name} ({duration:.2f}s)")
        if details:
            logger.info(f"   Details: {details}")
        
        # Record test result
        self.test_data[test_name]['success'] = success
        self.test_data[test_name]['details'] = details
        self.test_data[test_name]['duration'] = duration
        
        self.test_results.append({
            'test_name': test_name,
            'success': success,
            'details': details,
            'duration': duration
        })
        
        # Plan cleanup action
        if success:
            logger.debug(f"📋 Test {test_name} passed - data will be cleaned everywhere")
        else:
            logger.debug(f"🔍 Test {test_name} failed - data will be preserved for debugging")
        
        return success
    
    def make_request(self, method, url, **kwargs):
        """Make HTTP request with error handling and logging"""
        try:
            response = requests.request(method, url, timeout=30, **kwargs)
            return response
        except Exception as e:
            logger.error(f"❌ Request failed: {method} {url} - {e}")
            raise
    
    def selective_cleanup(self):
        """Selective cleanup - only clean up data from successful tests (INCLUDING POSTGRESQL)"""
        logger.info("🧹 Performing comprehensive selective test data cleanup...")
        logger.info("   ✅ Cleaning data from PASSED tests (ChromaDB + PostgreSQL)")
        logger.info("   🔍 Preserving data from FAILED tests for debugging")
        
        cleanup_results = {
            'tests_cleaned': 0,
            'tests_preserved': 0,
            'documents_deleted': 0,
            'collections_deleted': 0,
            'postgresql_mappings_deleted': 0,
            'postgresql_wal_deleted': 0,
            'preserved_collections': [],
            'preserved_documents': {},
            'failed_cleanups': 0
        }
        
        collections_to_clean = []  # For PostgreSQL cleanup
        
        for test_name, test_info in self.test_data.items():
            if test_info['success'] is None:
                logger.warning(f"   ⚠️ Test {test_name} has no recorded result - preserving data")
                cleanup_results['tests_preserved'] += 1
                continue
                
            if test_info['success']:
                # Clean up successful test data
                logger.info(f"   🧹 Cleaning data from PASSED test: {test_name}")
                cleanup_results['tests_cleaned'] += 1
                
                # Collect collections for PostgreSQL cleanup
                collections_to_clean.extend(test_info['collections'])
                
                # Clean documents first (ChromaDB)
                for collection_name, doc_ids in test_info['documents'].items():
                    if doc_ids:
                        try:
                            logger.debug(f"     Deleting {len(doc_ids)} documents from {collection_name}")
                            delete_payload = {"ids": list(doc_ids)}
                            response = self.make_request(
                                'POST',
                                f"{self.base_url}/api/v2/tenants/default_tenant/databases/default_database/collections/{collection_name}/delete",
                                headers={"Content-Type": "application/json"},
                                json=delete_payload
                            )
                            
                            if response.status_code == 200:
                                cleanup_results['documents_deleted'] += len(doc_ids)
                                logger.debug(f"     ✅ Deleted {len(doc_ids)} documents from {collection_name}")
                            else:
                                cleanup_results['failed_cleanups'] += 1
                                logger.warning(f"     ⚠️ Failed to delete documents from {collection_name}: {response.status_code}")
                                
                        except Exception as e:
                            cleanup_results['failed_cleanups'] += 1
                            logger.warning(f"     ⚠️ Error deleting documents from {collection_name}: {e}")
                
                # Clean collections (ChromaDB)
                for collection_name in test_info['collections']:
                    try:
                        logger.debug(f"     Deleting collection: {collection_name}")
                        response = self.make_request(
                            'DELETE',
                            f"{self.base_url}/api/v2/tenants/default_tenant/databases/default_database/collections/{collection_name}"
                        )
                        
                        if response.status_code in [200, 404]:
                            cleanup_results['collections_deleted'] += 1
                            logger.debug(f"     ✅ Deleted collection: {collection_name}")
                        else:
                            cleanup_results['failed_cleanups'] += 1
                            logger.warning(f"     ⚠️ Failed to delete collection {collection_name}: {response.status_code}")
                            
                    except Exception as e:
                        cleanup_results['failed_cleanups'] += 1
                        logger.warning(f"     ⚠️ Error deleting collection {collection_name}: {e}")
                        
            else:
                # Preserve failed test data
                logger.info(f"   🔍 Preserving data from FAILED test: {test_name}")
                cleanup_results['tests_preserved'] += 1
                
                # Record preserved data for debugging report
                preserved_collections = list(test_info['collections'])
                preserved_docs = {k: list(v) for k, v in test_info['documents'].items() if v}
                
                if preserved_collections:
                    cleanup_results['preserved_collections'].extend(preserved_collections)
                    logger.info(f"     📚 Preserved collections: {preserved_collections}")
                
                if preserved_docs:
                    cleanup_results['preserved_documents'].update(preserved_docs)
                    for coll, docs in preserved_docs.items():
                        logger.info(f"     📄 Preserved {len(docs)} documents in collection {coll}")
        
        # Clean PostgreSQL data for successful tests
        if collections_to_clean:
            logger.debug(f"   🗄️ Cleaning PostgreSQL data for {len(collections_to_clean)} collections...")
            pg_result = self.cleanup_postgresql_test_data(collections_to_clean, is_selective=True)
            cleanup_results['postgresql_mappings_deleted'] = pg_result.get('mappings_deleted', 0)
            cleanup_results['postgresql_wal_deleted'] = pg_result.get('wal_entries_deleted', 0)
            
            if not pg_result.get('success', False):
                cleanup_results['failed_cleanups'] += 1
        
        # Report cleanup results
        logger.info(f"🧹 Comprehensive Selective Cleanup Summary:")
        logger.info(f"   Tests cleaned: {cleanup_results['tests_cleaned']}")
        logger.info(f"   Tests preserved: {cleanup_results['tests_preserved']}")
        logger.info(f"   ChromaDB documents deleted: {cleanup_results['documents_deleted']}")
        logger.info(f"   ChromaDB collections deleted: {cleanup_results['collections_deleted']}")
        logger.info(f"   PostgreSQL mappings deleted: {cleanup_results['postgresql_mappings_deleted']}")
        logger.info(f"   PostgreSQL WAL entries deleted: {cleanup_results['postgresql_wal_deleted']}")
        
        if cleanup_results['failed_cleanups'] > 0:
            logger.warning(f"   Failed cleanups: {cleanup_results['failed_cleanups']}")
        
        # Report preserved data for debugging
        if cleanup_results['tests_preserved'] > 0:
            logger.info(f"\n🔍 DEBUGGING DATA PRESERVED:")
            logger.info(f"   Collections: {len(cleanup_results['preserved_collections'])}")
            logger.info(f"   Document sets: {len(cleanup_results['preserved_documents'])}")
            
            for collection in cleanup_results['preserved_collections']:
                logger.info(f"   📚 Collection: {collection}")
            
            for collection, doc_ids in cleanup_results['preserved_documents'].items():
                logger.info(f"   📄 Documents in {collection}: {len(doc_ids)} items")
        else:
            logger.info("   🎉 No failed tests - all data cleaned successfully!")
        
        return cleanup_results

    def comprehensive_cleanup(self):
        """Comprehensive cleanup - cleans everything (INCLUDING POSTGRESQL)"""
        logger.warning("🧹 Performing COMPREHENSIVE cleanup (all data will be removed from everywhere)...")
        
        cleanup_results = {
            'documents_deleted': 0,
            'collections_deleted': 0,
            'postgresql_mappings_deleted': 0,
            'postgresql_wal_deleted': 0,
            'failed_cleanups': 0
        }
        
        # Clean all tracked data regardless of test results
        all_collections = set()
        all_documents = defaultdict(set)
        
        for test_info in self.test_data.values():
            all_collections.update(test_info['collections'])
            for collection_name, doc_ids in test_info['documents'].items():
                all_documents[collection_name].update(doc_ids)
        
        # Clean documents (ChromaDB)
        for collection_name, doc_ids in all_documents.items():
            if doc_ids:
                try:
                    delete_payload = {"ids": list(doc_ids)}
                    response = self.make_request(
                        'POST',
                        f"{self.base_url}/api/v2/tenants/default_tenant/databases/default_database/collections/{collection_name}/delete",
                        json=delete_payload
                    )
                    
                    if response.status_code == 200:
                        cleanup_results['documents_deleted'] += len(doc_ids)
                        logger.info(f"  ✅ Deleted {len(doc_ids)} documents from {collection_name}")
                    else:
                        cleanup_results['failed_cleanups'] += 1
                        
                except Exception as e:
                    cleanup_results['failed_cleanups'] += 1
        
        # Clean collections (ChromaDB)
        for collection_name in all_collections:
            try:
                response = self.make_request(
                    'DELETE',
                    f"{self.base_url}/api/v2/tenants/default_tenant/databases/default_database/collections/{collection_name}"
                )
                
                if response.status_code in [200, 404]:
                    cleanup_results['collections_deleted'] += 1
                    logger.info(f"  ✅ Deleted collection: {collection_name}")
                else:
                    cleanup_results['failed_cleanups'] += 1
                    
            except Exception as e:
                cleanup_results['failed_cleanups'] += 1
        
        # Clean PostgreSQL data (comprehensive)
        logger.info("  🗄️ Cleaning PostgreSQL data...")
        pg_result = self.cleanup_postgresql_test_data([], is_selective=False)
        cleanup_results['postgresql_mappings_deleted'] = pg_result.get('mappings_deleted', 0)
        cleanup_results['postgresql_wal_deleted'] = pg_result.get('wal_entries_deleted', 0)
        
        if pg_result.get('success', False):
            logger.info(f"  ✅ PostgreSQL cleanup: {cleanup_results['postgresql_mappings_deleted']} mappings, {cleanup_results['postgresql_wal_deleted']} WAL entries")
        else:
            cleanup_results['failed_cleanups'] += 1
            logger.warning(f"  ⚠️ PostgreSQL cleanup failed: {pg_result.get('error', 'Unknown error')}")
        
        # Clear all tracking
        self.test_data.clear()
        
        return cleanup_results

    def emergency_cleanup(self):
        """Emergency cleanup that runs on exit"""
        if hasattr(self, 'test_data') and self.test_data:
            total_collections = sum(len(test_info['collections']) for test_info in self.test_data.values())
            if total_collections > 0:
                logger.warning(f"🚨 Emergency cleanup: Removing {total_collections} test collections from everywhere")
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
        """Print comprehensive test summary with cleanup strategy"""
        summary = self.get_test_summary()
        
        logger.info("="*60)
        logger.info(f"📊 Test Summary for Session {self.test_session_id}")
        logger.info(f"   Total Tests: {summary['total']}")
        logger.info(f"   Passed: {summary['passed']}")
        logger.info(f"   Failed: {summary['failed']}")
        logger.info(f"   Success Rate: {summary['success_rate']:.1f}%")
        
        if summary['failed'] > 0:
            logger.info(f"\n❌ Failed Tests ({summary['failed']}):")
            for result in summary['results']:
                if not result['success']:
                    logger.info(f"   • {result['test_name']}: {result['details']}")
            
            logger.info(f"\n🔍 Cleanup Strategy:")
            logger.info(f"   ✅ Data from {summary['passed']} passed tests will be cleaned everywhere")
            logger.info(f"   🔍 Data from {summary['failed']} failed tests will be preserved for debugging")
            logger.info(f"   🗄️ PostgreSQL data for passed tests will be removed")
        else:
            logger.info(f"\n🎉 All tests passed!")
            logger.info(f"   ✅ All test data will be cleaned up everywhere")
            logger.info(f"   🗄️ All PostgreSQL test data will be removed")
        
        logger.info("="*60)
        
        return summary['success_rate'] == 100.0

    def force_cleanup_all(self):
        """Force cleanup of all data everywhere (for manual cleanup scenarios)"""
        logger.warning("🧹 FORCED CLEANUP: Removing all test data from everywhere regardless of test results")
        return self.comprehensive_cleanup() 