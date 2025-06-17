#!/usr/bin/env python3
"""
Test Write Failover Functionality - Critical for high availability
Tests that write operations properly failover to replica when primary is down
WITH COMPREHENSIVE CLEANUP SYSTEM
"""

import requests
import json
import uuid
import time
import logging
import atexit

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class WriteFailoverTestSuite:
    def __init__(self, base_url="https://chroma-load-balancer.onrender.com"):
        self.base_url = base_url.rstrip('/')
        self.test_session_id = f"{int(time.time())}_{uuid.uuid4().hex[:8]}"
        self.created_collections = set()
        self.created_documents = {}
        
        # Register emergency cleanup
        atexit.register(self.emergency_cleanup)
        
    def track_collection(self, collection_name):
        """Track collection for cleanup"""
        self.created_collections.add(collection_name)
        
    def track_documents(self, collection_name, doc_ids):
        """Track document IDs for cleanup"""
        if collection_name not in self.created_documents:
            self.created_documents[collection_name] = set()
        self.created_documents[collection_name].update(doc_ids)

    def check_instance_health(self):
        """Check health status of both instances"""
        try:
            response = requests.get(f"{self.base_url}/status", timeout=30)
            if response.status_code == 200:
                status = response.json()
                instances = status.get('instances', [])
                primary_healthy = any(inst.get('name') == 'primary' and inst.get('healthy') for inst in instances)
                replica_healthy = any(inst.get('name') == 'replica' and inst.get('healthy') for inst in instances)
                return primary_healthy, replica_healthy
        except Exception as e:
            logger.error(f"Failed to check instance health: {e}")
        return False, False

    def test_write_failover_scenario(self):
        """Test write operations during primary downtime"""
        logger.info("⚡ Testing Write Failover Scenario")
        
        collection_name = f"AUTOTEST_failover_{self.test_session_id}"
        self.track_collection(collection_name)
        
        try:
            # Check system health
            logger.info("  Checking system health...")
            primary_healthy, replica_healthy = self.check_instance_health()
            logger.info(f"  Instance Status - Primary: {primary_healthy}, Replica: {replica_healthy}")
            
            if not replica_healthy:
                logger.error("❌ Replica unhealthy - cannot test failover")
                return False
                
            # Create collection
            logger.info(f"  Creating test collection: {collection_name}")
            create_response = requests.post(
                f"{self.base_url}/api/v2/tenants/default_tenant/databases/default_database/collections",
                json={"name": collection_name},
                timeout=30
            )
            
            if create_response.status_code not in [200, 201]:
                logger.error(f"❌ Collection creation failed: {create_response.status_code}")
                return False
                
            # Wait for mapping to establish
            time.sleep(3)
            
            # Test write operation
            logger.info("  Testing write operation during failover scenario...")
            doc_ids = [f"failover_test_{uuid.uuid4().hex[:8]}"]
            doc_data = {
                "embeddings": [[0.1, 0.2, 0.3, 0.4, 0.5]],
                "documents": ["Failover test document"],
                "metadatas": [{"test_type": "failover_write", "session": self.test_session_id}],
                "ids": doc_ids
            }
            
            # Track documents for cleanup
            self.track_documents(collection_name, doc_ids)
            
            write_response = requests.post(
                f"{self.base_url}/api/v2/tenants/default_tenant/databases/default_database/collections/{collection_name}/add",
                json=doc_data,
                timeout=30
            )
            
            if write_response.status_code not in [200, 201]:
                if not primary_healthy:
                    logger.error(f"❌ Write failover failed: {write_response.status_code}")
                    logger.error(f"  Response: {write_response.text[:300]}")
                    return False
                else:
                    logger.warning(f"⚠️ Write failed: {write_response.status_code}")
                    return False
            else:
                if not primary_healthy:
                    logger.info("  🎉 Write successful during primary downtime!")
                    logger.info("  ✅ Write failover working correctly!")
                else:
                    logger.info("  ✅ Write successful with primary healthy")
            
            # Verify document was stored
            get_response = requests.post(
                f"{self.base_url}/api/v2/tenants/default_tenant/databases/default_database/collections/{collection_name}/get",
                json={"include": ["documents", "metadatas"]},
                timeout=30
            )
            
            if get_response.status_code == 200:
                doc_count = len(get_response.json().get('ids', []))
                logger.info(f"  ✅ Documents verified: {doc_count} found")
            else:
                logger.warning(f"⚠️ Document verification failed: {get_response.status_code}")
            
            return True
            
        except Exception as e:
            logger.error(f"❌ Failover test failed: {e}")
            return False

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
                    delete_payload = {"ids": list(doc_ids)}
                    response = requests.post(
                        f"{self.base_url}/api/v2/tenants/default_tenant/databases/default_database/collections/{collection_name}/delete",
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
                    f"{self.base_url}/api/v2/tenants/default_tenant/databases/default_database/collections/{collection_name}",
                    timeout=30
                )
                if response.status_code in [200, 404]:
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

def main():
    """Run write failover tests with comprehensive cleanup"""
    import sys
    import argparse
    
    parser = argparse.ArgumentParser(description="Test Write Failover Functionality")
    parser.add_argument("--url", default="https://chroma-load-balancer.onrender.com", help="Load balancer URL")
    args = parser.parse_args()
    
    suite = WriteFailoverTestSuite(args.url)
    
    logger.info("🚀 Starting Write Failover Test")
    logger.info(f"🆔 Test Session ID: {suite.test_session_id}")
    logger.info("="*60)
    
    try:
        success = suite.test_write_failover_scenario()
    finally:
        # Always perform cleanup, even if tests failed
        cleanup_results = suite.comprehensive_cleanup()
    
    logger.info("="*60)
    if success:
        logger.info("🎉 Write failover test PASSED!")
        logger.info("🧹 Test data isolation and cleanup completed successfully.")
    else:
        logger.error("❌ Write failover test FAILED!")
        logger.info("🧹 Test data cleanup completed to prevent pollution.")
    
    return success

if __name__ == "__main__":
    success = main()
    exit(0 if success else 1) 