#!/usr/bin/env python3
"""
Threading Performance Test Suite
================================

Tests multi-threading improvements, worker scaling, and parallel processing
capabilities with comprehensive cleanup.
"""

import sys
import requests
import logging
import time
import uuid
import concurrent.futures
from typing import List

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Production safety
TEST_PREFIX = "AUTOTEST_"
test_collections_created = []

def create_safe_test_collection_name(purpose: str) -> str:
    """Create a production-safe test collection name"""
    timestamp = int(time.time())
    random_suffix = str(uuid.uuid4())[:8]
    collection_name = f"{TEST_PREFIX}threading_{purpose}_{timestamp}_{random_suffix}"
    test_collections_created.append(collection_name)
    return collection_name

def cleanup_test_collections(base_url: str):
    """Clean up all test collections from the system"""
    logger.info("🧹 Cleaning up threading test collections...")
    
    cleanup_results = {"attempted": 0, "successful": 0, "failed": 0}
    
    for collection_name in test_collections_created:
        cleanup_results["attempted"] += 1
        
        # Safety check
        if not collection_name.startswith(TEST_PREFIX):
            logger.error(f"❌ SAFETY: Refused to delete {collection_name}")
            cleanup_results["failed"] += 1
            continue
        
        try:
            # Delete collection
            response = requests.delete(
                f"{base_url}/api/v2/collections/{collection_name}",
                timeout=30
            )
            if response.status_code in [200, 404]:  # 404 means already deleted
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

def test_threading_performance():
    """Test threading performance and worker configuration with cleanup"""
    base_url = "https://chroma-load-balancer.onrender.com"
    
    logger.info("🧵 Testing Threading Performance")
    success = True
    
    try:
        # Test 1: Worker configuration check
        try:
            response = requests.get(f"{base_url}/status", timeout=30)
            if response.status_code == 200:
                status = response.json()
                config = status.get('high_volume_config', {})
                max_workers = config.get('max_workers', 0)
                
                logger.info(f"✅ Worker configuration: {max_workers} workers")
                if max_workers >= 8:
                    logger.info("🚀 OPTIMIZED: Using 8+ workers")
                elif max_workers >= 3:
                    logger.info("⚠️ BASIC: Using 3+ workers (consider upgrading)")
                else:
                    logger.error("❌ INSUFFICIENT: < 3 workers")
                    success = False
            else:
                logger.error(f"❌ Status check failed: {response.status_code}")
                success = False
        except Exception as e:
            logger.error(f"❌ Worker config test failed: {e}")
            success = False
        
        # Test 2: Concurrent request handling
        try:
            def make_request(i):
                start = time.time()
                resp = requests.get(f"{base_url}/health", timeout=10)
                duration = time.time() - start
                return resp.status_code == 200, duration
            
            start_time = time.time()
            with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
                futures = [executor.submit(make_request, i) for i in range(10)]
                results = [future.result() for future in concurrent.futures.as_completed(futures)]
            
            total_time = time.time() - start_time
            successful = sum(1 for success_result, _ in results if success_result)
            avg_response = sum(duration for _, duration in results) / len(results)
            parallel_efficiency = (avg_response * 10) / total_time
            
            logger.info(f"✅ Concurrent requests: {successful}/10 successful")
            logger.info(f"✅ Average response time: {avg_response:.2f}s")
            logger.info(f"✅ Parallel efficiency: {parallel_efficiency:.1f}x")
            
            if successful < 8 or avg_response > 3.0:
                logger.warning("⚠️ Threading performance below optimal")
                success = False
                
        except Exception as e:
            logger.error(f"❌ Concurrent test failed: {e}")
            success = False
        
        # Test 3: Create a test collection to verify threading works under load
        try:
            collection_name = create_safe_test_collection_name("perf_test")
            collection_payload = {
                "name": collection_name,
                "metadata": {"test_type": "threading_performance"}
            }
            
            response = requests.post(
                f"{base_url}/api/v2/tenants/default_tenant/databases/default_database/collections",
                headers={"Content-Type": "application/json"},
                json=collection_payload,
                timeout=30
            )
            
            if response.status_code in [200, 201]:
                logger.info(f"✅ Test collection created: {collection_name}")
            else:
                logger.warning(f"⚠️ Collection creation failed: {response.status_code}")
                
        except Exception as e:
            logger.error(f"❌ Collection test failed: {e}")
            success = False
        
        return success
        
    finally:
        # Always cleanup
        cleanup_test_collections(base_url)

if __name__ == "__main__":
    logger.info("🚀 Starting Threading Performance Test Suite")
    success = test_threading_performance()
    
    if success:
        logger.info("✅ Threading performance tests PASSED")
    else:
        logger.error("❌ Threading performance tests FAILED")
    
    sys.exit(0 if success else 1) 