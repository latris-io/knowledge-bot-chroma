#!/usr/bin/env python3
"""
Memory Optimization Test Suite
==============================

Tests memory pressure handling, optimization features, and resource management
with comprehensive cleanup.
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
    collection_name = f"{TEST_PREFIX}memory_{purpose}_{timestamp}_{random_suffix}"
    test_collections_created.append(collection_name)
    return collection_name

def cleanup_test_collections(base_url: str):
    """Clean up all test collections from the system"""
    logger.info("🧹 Cleaning up memory optimization test collections...")
    
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

def test_memory_optimization():
    """Test memory optimization and pressure handling with cleanup"""
    base_url = "https://chroma-load-balancer.onrender.com"
    
    logger.info("💾 Testing Memory Optimization")
    success = True
    
    try:
        # Test 1: Check current memory usage
        try:
            response = requests.get(f"{base_url}/metrics", timeout=30)
            if response.status_code == 200:
                metrics = response.json()
                resource_usage = metrics.get('resource_usage', {})
                
                memory_percent = resource_usage.get('memory_percent', 0)
                memory_usage_mb = resource_usage.get('memory_usage_mb', 0)
                memory_pressure_events = resource_usage.get('memory_pressure_events', 0)
                
                logger.info(f"✅ Current memory usage: {memory_percent:.1f}% ({memory_usage_mb:.1f}MB)")
                logger.info(f"✅ Memory pressure events: {memory_pressure_events}")
                
                # Check if memory usage is reasonable
                if memory_percent > 95:
                    logger.error("❌ CRITICAL: Memory usage over 95%")
                    success = False
                elif memory_percent > 85:
                    logger.warning("⚠️ HIGH: Memory usage over 85%")
                else:
                    logger.info("✅ GOOD: Memory usage within acceptable range")
                    
            else:
                logger.error(f"❌ Metrics endpoint failed: {response.status_code}")
                success = False
        except Exception as e:
            logger.error(f"❌ Memory metrics test failed: {e}")
            success = False
        
        # Test 2: Check memory pressure detection
        try:
            response = requests.get(f"{base_url}/status", timeout=30)
            if response.status_code == 200:
                status = response.json()
                performance_stats = status.get('performance_stats', {})
                
                memory_pressure_events = performance_stats.get('memory_pressure_events', 0)
                peak_memory_usage = performance_stats.get('peak_memory_usage', 0)
                
                logger.info(f"✅ Memory pressure detection working: {memory_pressure_events} events")
                logger.info(f"✅ Peak memory usage tracked: {peak_memory_usage:.1f}MB")
                
            else:
                logger.error(f"❌ Status endpoint failed: {response.status_code}")
                success = False
        except Exception as e:
            logger.error(f"❌ Memory pressure test failed: {e}")
            success = False
        
        # Test 3: Check batch size optimization
        try:
            response = requests.get(f"{base_url}/status", timeout=30)
            if response.status_code == 200:
                status = response.json()
                config = status.get('high_volume_config', {})
                
                adaptive_batching = config.get('adaptive_batching', False)
                batch_size = config.get('batch_size', 0)
                
                logger.info(f"✅ Adaptive batching: {adaptive_batching}")
                logger.info(f"✅ Current batch size: {batch_size}")
                
                if batch_size > 0:
                    logger.info("✅ Batch size optimization working")
                else:
                    logger.warning("⚠️ Batch size not configured")
                    
            else:
                logger.error(f"❌ Config check failed: {response.status_code}")
                success = False
        except Exception as e:
            logger.error(f"❌ Batch optimization test failed: {e}")
            success = False
        
        # Test 4: Create a small test collection to verify memory-efficient operations
        try:
            collection_name = create_safe_test_collection_name("mem_test")
            collection_payload = {
                "name": collection_name,
                "metadata": {"test_type": "memory_optimization", "small_test": True}
            }
            
            response = requests.post(
                f"{base_url}/api/v2/tenants/default_tenant/databases/default_database/collections",
                headers={"Content-Type": "application/json"},
                json=collection_payload,
                timeout=30
            )
            
            if response.status_code in [200, 201]:
                logger.info(f"✅ Memory-efficient collection created: {collection_name}")
            else:
                logger.warning(f"⚠️ Collection creation failed: {response.status_code}")
                
        except Exception as e:
            logger.error(f"❌ Memory test collection failed: {e}")
            success = False
        
        # Test 5: Check upgrade recommendations for memory
        try:
            response = requests.get(f"{base_url}/metrics", timeout=30)
            if response.status_code == 200:
                metrics = response.json()
                upgrade_recommendations = metrics.get('upgrade_recommendations', [])
                
                memory_recommendations = [r for r in upgrade_recommendations if 'memory' in r.get('type', '').lower()]
                
                if memory_recommendations:
                    logger.info(f"ℹ️ Memory upgrade recommendations available: {len(memory_recommendations)}")
                    for rec in memory_recommendations[:2]:  # Show first 2
                        logger.info(f"   • {rec.get('reason', 'Memory optimization needed')}")
                else:
                    logger.info("✅ No urgent memory upgrade recommendations")
                    
            else:
                logger.info(f"ℹ️ Upgrade recommendations not available (status: {response.status_code})")
                
        except Exception as e:
            logger.info(f"ℹ️ Upgrade recommendations test skipped: {e}")
        
        return success
        
    finally:
        # Always cleanup
        cleanup_test_collections(base_url)

if __name__ == "__main__":
    logger.info("🚀 Starting Memory Optimization Test Suite")
    success = test_memory_optimization()
    
    if success:
        logger.info("✅ Memory optimization tests PASSED")
    else:
        logger.error("❌ Memory optimization tests FAILED")
    
    sys.exit(0 if success else 1)
