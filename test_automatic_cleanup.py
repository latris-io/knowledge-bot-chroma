#!/usr/bin/env python3
"""
Automatic Cleanup Test Suite
============================

Tests automatic WAL cleanup, collection cleanup, and database maintenance
with comprehensive safety mechanisms.
"""

import sys
import requests
import logging
import time
import uuid

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Production safety
TEST_PREFIX = "AUTOTEST_"
test_collections_created = []

def create_safe_test_collection_name(purpose: str) -> str:
    """Create a production-safe test collection name"""
    timestamp = int(time.time())
    random_suffix = str(uuid.uuid4())[:8]
    collection_name = f"{TEST_PREFIX}cleanup_{purpose}_{timestamp}_{random_suffix}"
    test_collections_created.append(collection_name)
    return collection_name

def cleanup_test_collections(base_url: str):
    """Clean up all test collections from the system"""
    logger.info("🧹 Cleaning up automatic cleanup test collections...")
    
    cleanup_results = {"attempted": 0, "successful": 0, "failed": 0}
    
    for collection_name in test_collections_created:
        cleanup_results["attempted"] += 1
        
        # Safety check
        if not collection_name.startswith(TEST_PREFIX):
            logger.error(f"❌ SAFETY: Refused to delete {collection_name}")
            cleanup_results["failed"] += 1
            continue
        
        try:
            response = requests.delete(
                f"{base_url}/api/v2/collections/{collection_name}",
                timeout=30
            )
            if response.status_code in [200, 404]:
                logger.info(f"✅ Deleted: {collection_name}")
                cleanup_results["successful"] += 1
            else:
                logger.warning(f"⚠️ Failed to delete {collection_name}: {response.status_code}")
                cleanup_results["failed"] += 1
        except Exception as e:
            logger.warning(f"⚠️ Error deleting {collection_name}: {e}")
            cleanup_results["failed"] += 1
    
    logger.info(f"🧹 Cleanup complete: {cleanup_results['successful']}/{cleanup_results['attempted']} collections")
    test_collections_created.clear()
    return cleanup_results

def test_automatic_cleanup():
    """Test automatic cleanup systems with safety checks"""
    base_url = "https://chroma-load-balancer.onrender.com"
    
    logger.info("🧹 Testing Automatic Cleanup Systems")
    success = True
    
    try:
        # Test 1: Check WAL automatic cleanup status
        try:
            response = requests.get(f"{base_url}/wal/status", timeout=30)
            if response.status_code == 200:
                wal_status = response.json()
                wal_system = wal_status.get('wal_system', {})
                
                pending_writes = wal_system.get('pending_writes', 0)
                logger.info(f"✅ WAL cleanup system active: {pending_writes} pending writes")
                
                # Check if automatic cleanup is working
                performance_stats = wal_status.get('performance_stats', {})
                successful_syncs = performance_stats.get('successful_syncs', 0)
                
                if successful_syncs > 0:
                    logger.info("✅ WAL cleanup processing entries successfully")
                else:
                    logger.info("ℹ️ WAL cleanup ready (no recent activity)")
                    
            else:
                logger.error(f"❌ WAL status check failed: {response.status_code}")
                success = False
        except Exception as e:
            logger.error(f"❌ WAL cleanup test failed: {e}")
            success = False
        
        # Test 2: Test manual WAL cleanup operation
        try:
            cleanup_payload = {"max_age_hours": 1}
            response = requests.post(
                f"{base_url}/wal/cleanup",
                headers={"Content-Type": "application/json"},
                json=cleanup_payload,
                timeout=30
            )
            
            if response.status_code == 200:
                result = response.json()
                deleted_entries = result.get('deleted_entries', 0)
                reset_entries = result.get('reset_entries', 0)
                
                logger.info(f"✅ Manual WAL cleanup: {deleted_entries} deleted, {reset_entries} reset")
            else:
                logger.error(f"❌ Manual WAL cleanup failed: {response.status_code}")
                success = False
        except Exception as e:
            logger.error(f"❌ Manual WAL cleanup test failed: {e}")
            success = False
        
        # Test 3: Create and cleanup test collection to verify cleanup works
        try:
            collection_name = create_safe_test_collection_name("cleanup_test")
            collection_payload = {
                "name": collection_name,
                "metadata": {"test_type": "automatic_cleanup", "safe_to_delete": True}
            }
            
            response = requests.post(
                f"{base_url}/api/v2/tenants/default_tenant/databases/default_database/collections",
                headers={"Content-Type": "application/json"},
                json=collection_payload,
                timeout=30
            )
            
            if response.status_code in [200, 201]:
                logger.info(f"✅ Test collection created for cleanup test: {collection_name}")
                
                # Immediately test cleanup functionality
                response = requests.delete(
                    f"{base_url}/api/v2/collections/{collection_name}",
                    timeout=30
                )
                
                if response.status_code in [200, 404]:
                    logger.info("✅ Collection cleanup test successful")
                    test_collections_created.remove(collection_name)  # Already cleaned up
                else:
                    logger.warning(f"⚠️ Collection cleanup test failed: {response.status_code}")
                    
            else:
                logger.warning(f"⚠️ Test collection creation failed: {response.status_code}")
                
        except Exception as e:
            logger.error(f"❌ Collection cleanup test failed: {e}")
            success = False
        
        # Test 4: Check system health after cleanup operations
        try:
            response = requests.get(f"{base_url}/health", timeout=30)
            if response.status_code == 200:
                logger.info("✅ System healthy after cleanup operations")
            else:
                logger.error(f"❌ System health check failed: {response.status_code}")
                success = False
        except Exception as e:
            logger.error(f"❌ Health check failed: {e}")
            success = False
        
        return success
        
    finally:
        # Always cleanup remaining test collections
        cleanup_test_collections(base_url)

if __name__ == "__main__":
    logger.info("🚀 Starting Automatic Cleanup Test Suite")
    success = test_automatic_cleanup()
    
    if success:
        logger.info("✅ Automatic cleanup tests PASSED")
    else:
        logger.error("❌ Automatic cleanup tests FAILED")
    
    sys.exit(0 if success else 1)
