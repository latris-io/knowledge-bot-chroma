#!/usr/bin/env python3
"""
V2 API Compatibility Test Suite
===============================

Tests V2 API path normalization, backward compatibility, and proper routing
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
    collection_name = f"{TEST_PREFIX}v2api_{purpose}_{timestamp}_{random_suffix}"
    test_collections_created.append(collection_name)
    return collection_name

def cleanup_test_collections(base_url: str):
    """Clean up all test collections from the system"""
    logger.info("🧹 Cleaning up V2 API test collections...")
    
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

def test_v2_api_compatibility():
    """Test V2 API compatibility and path normalization with cleanup"""
    base_url = "https://chroma-load-balancer.onrender.com"
    
    logger.info("🔄 Testing V2 API Compatibility")
    success = True
    
    try:
        # Test 1: V2 API endpoints are accessible
        try:
            # Test version endpoint
            response = requests.get(f"{base_url}/api/v2/version", timeout=30)
            if response.status_code == 200:
                logger.info("✅ V2 version endpoint accessible")
            else:
                logger.error(f"❌ V2 version endpoint failed: {response.status_code}")
                success = False
        except Exception as e:
            logger.error(f"❌ V2 version test failed: {e}")
            success = False
        
        # Test 2: V2 collections endpoint
        try:
            response = requests.get(
                f"{base_url}/api/v2/tenants/default_tenant/databases/default_database/collections",
                timeout=30
            )
            if response.status_code == 200:
                collections = response.json()
                logger.info(f"✅ V2 collections endpoint: {len(collections)} collections found")
            else:
                logger.error(f"❌ V2 collections endpoint failed: {response.status_code}")
                success = False
        except Exception as e:
            logger.error(f"❌ V2 collections test failed: {e}")
            success = False
        
        # Test 3: Create collection using V2 API
        try:
            collection_name = create_safe_test_collection_name("v2_compat")
            collection_payload = {
                "name": collection_name,
                "metadata": {"test_type": "v2_api_compatibility"}
            }
            
            response = requests.post(
                f"{base_url}/api/v2/tenants/default_tenant/databases/default_database/collections",
                headers={"Content-Type": "application/json"},
                json=collection_payload,
                timeout=30
            )
            
            if response.status_code in [200, 201]:
                collection_data = response.json()
                collection_id = collection_data.get('id')
                logger.info(f"✅ V2 collection created: {collection_name} (ID: {collection_id[:8] if collection_id else 'unknown'}...)")
            else:
                logger.error(f"❌ V2 collection creation failed: {response.status_code}")
                success = False
                
        except Exception as e:
            logger.error(f"❌ V2 collection creation test failed: {e}")
            success = False
        
        # Test 4: Test path normalization (if system has normalize_api_path_to_v2)
        try:
            # Test various path formats to ensure normalization works
            test_paths = [
                "/api/v2/collections",  # Legacy path
                "/api/v2/tenants/default_tenant/databases/default_database/collections"  # Full V2 path
            ]
            
            for path in test_paths:
                response = requests.get(f"{base_url}{path}", timeout=30)
                if response.status_code == 200:
                    logger.info(f"✅ Path '{path}' works correctly")
                else:
                    logger.warning(f"⚠️ Path '{path}' returned {response.status_code}")
                    
        except Exception as e:
            logger.error(f"❌ Path normalization test failed: {e}")
            success = False
        
        # Test 5: Test backward compatibility
        try:
            # Test that old API patterns still work (if supported)
            response = requests.get(f"{base_url}/api/v2/heartbeat", timeout=30)
            if response.status_code == 200:
                logger.info("✅ V2 heartbeat endpoint accessible")
            else:
                logger.info(f"ℹ️ V2 heartbeat endpoint not available (status: {response.status_code})")
                
        except Exception as e:
            logger.info(f"ℹ️ V2 heartbeat test skipped: {e}")
        
        return success
        
    finally:
        # Always cleanup
        cleanup_test_collections(base_url)

if __name__ == "__main__":
    logger.info("🚀 Starting V2 API Compatibility Test Suite")
    success = test_v2_api_compatibility()
    
    if success:
        logger.info("✅ V2 API compatibility tests PASSED")
    else:
        logger.error("❌ V2 API compatibility tests FAILED")
    
    sys.exit(0 if success else 1)
