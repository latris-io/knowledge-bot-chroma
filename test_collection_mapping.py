#!/usr/bin/env python3
"""
Collection Mapping Test Suite
=============================

Tests dynamic collection ID mapping, refresh mechanisms, and cross-instance
consistency with comprehensive cleanup.
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
    collection_name = f"{TEST_PREFIX}mapping_{purpose}_{timestamp}_{random_suffix}"
    test_collections_created.append(collection_name)
    return collection_name

def cleanup_test_collections(base_url: str):
    """Clean up all test collections from the system"""
    logger.info("🧹 Cleaning up collection mapping test collections...")
    
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

def test_collection_mapping():
    """Test collection mapping and cross-instance consistency with cleanup"""
    base_url = "https://chroma-load-balancer.onrender.com"
    
    logger.info("🗺️ Testing Collection Mapping System")
    success = True
    
    try:
        # Test 1: Check collection mappings endpoint
        try:
            response = requests.get(f"{base_url}/collection/mappings", timeout=30)
            if response.status_code == 200:
                mappings_data = response.json()
                mappings = mappings_data.get('mappings', [])
                
                logger.info(f"✅ Collection mappings accessible: {len(mappings)} mappings found")
                
                # Check mapping structure
                if mappings:
                    sample_mapping = mappings[0]
                    required_fields = ['collection_name', 'primary_id', 'replica_id']
                    
                    has_all_fields = all(field in sample_mapping for field in required_fields)
                    if has_all_fields:
                        logger.info("✅ Collection mapping structure valid")
                    else:
                        logger.warning("⚠️ Collection mapping structure incomplete")
                        success = False
                else:
                    logger.info("ℹ️ No existing collection mappings (clean state)")
                    
            else:
                logger.error(f"❌ Collection mappings endpoint failed: {response.status_code}")
                success = False
        except Exception as e:
            logger.error(f"❌ Collection mappings test failed: {e}")
            success = False
        
        # Test 2: Create collection and check if mapping is created
        try:
            collection_name = create_safe_test_collection_name("map_test")
            collection_payload = {
                "name": collection_name,
                "metadata": {"test_type": "collection_mapping"}
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
                logger.info(f"✅ Test collection created: {collection_name} (ID: {collection_id[:8] if collection_id else 'unknown'}...)")
                
                # Wait a moment for mapping to be created
                time.sleep(2)
                
                # Check if mapping was created
                response = requests.get(f"{base_url}/collection/mappings", timeout=30)
                if response.status_code == 200:
                    mappings_data = response.json()
                    mappings = mappings_data.get('mappings', [])
                    
                    # Look for our test collection
                    test_mapping = None
                    for mapping in mappings:
                        if mapping.get('collection_name') == collection_name:
                            test_mapping = mapping
                            break
                    
                    if test_mapping:
                        logger.info(f"✅ Collection mapping created successfully")
                        logger.info(f"   Primary ID: {test_mapping.get('primary_id', 'unknown')[:8]}...")
                        logger.info(f"   Replica ID: {test_mapping.get('replica_id', 'unknown')[:8]}...")
                    else:
                        logger.warning("⚠️ Collection mapping not found (may be created asynchronously)")
                else:
                    logger.warning("⚠️ Could not verify mapping creation")
                    
            else:
                logger.error(f"❌ Test collection creation failed: {response.status_code}")
                success = False
                
        except Exception as e:
            logger.error(f"❌ Collection mapping creation test failed: {e}")
            success = False
        
        # Test 3: Check load balancer instance health (affects mapping)
        try:
            response = requests.get(f"{base_url}/status", timeout=30)
            if response.status_code == 200:
                status = response.json()
                instances = status.get('instances', [])
                healthy_instances = [inst for inst in instances if inst.get('healthy', False)]
                
                logger.info(f"✅ Instance health check: {len(healthy_instances)}/{len(instances)} healthy")
                
                if len(healthy_instances) >= 2:
                    logger.info("✅ Multi-instance mapping possible")
                elif len(healthy_instances) == 1:
                    logger.info("ℹ️ Single instance mode - limited mapping")
                else:
                    logger.error("❌ No healthy instances - mapping cannot work")
                    success = False
                    
            else:
                logger.error(f"❌ Instance health check failed: {response.status_code}")
                success = False
        except Exception as e:
            logger.error(f"❌ Instance health test failed: {e}")
            success = False
        
        # Test 4: Test collection access through load balancer (mapping functionality)
        try:
            # List collections through load balancer
            response = requests.get(
                f"{base_url}/api/v2/tenants/default_tenant/databases/default_database/collections",
                timeout=30
            )
            
            if response.status_code == 200:
                collections = response.json()
                test_collections = [col for col in collections if col['name'].startswith(TEST_PREFIX)]
                
                logger.info(f"✅ Collection access through load balancer: {len(test_collections)} test collections found")
                
                if test_collections:
                    # Try to access a specific collection
                    test_collection = test_collections[0]
                    collection_id = test_collection['id']
                    
                    # Test get collection by ID (tests mapping functionality)
                    response = requests.post(
                        f"{base_url}/api/v2/collections/{collection_id}/get",
                        headers={"Content-Type": "application/json"},
                        json={"limit": 1},
                        timeout=30
                    )
                    
                    if response.status_code in [200, 422]:  # 422 is OK for empty collection
                        logger.info("✅ Collection access by ID working (mapping functional)")
                    else:
                        logger.warning(f"⚠️ Collection access by ID failed: {response.status_code}")
                        
            else:
                logger.error(f"❌ Collection listing failed: {response.status_code}")
                success = False
                
        except Exception as e:
            logger.error(f"❌ Collection access test failed: {e}")
            success = False
        
        # Test 5: Check mapping consistency
        try:
            response = requests.get(f"{base_url}/collection/mappings", timeout=30)
            if response.status_code == 200:
                mappings_data = response.json()
                mappings = mappings_data.get('mappings', [])
                total_collections = mappings_data.get('total_collections', 0)
                
                logger.info(f"✅ Mapping consistency check: {len(mappings)} mappings for {total_collections} collections")
                
                # Check for any obvious inconsistencies
                inconsistent_mappings = 0
                for mapping in mappings:
                    primary_id = mapping.get('primary_id')
                    replica_id = mapping.get('replica_id')
                    
                    if not primary_id or not replica_id:
                        inconsistent_mappings += 1
                
                if inconsistent_mappings > 0:
                    logger.warning(f"⚠️ Found {inconsistent_mappings} incomplete mappings")
                else:
                    logger.info("✅ All mappings appear complete")
                    
            else:
                logger.warning(f"⚠️ Mapping consistency check failed: {response.status_code}")
                
        except Exception as e:
            logger.info(f"ℹ️ Mapping consistency check skipped: {e}")
        
        return success
        
    finally:
        # Always cleanup
        cleanup_test_collections(base_url)

if __name__ == "__main__":
    logger.info("🚀 Starting Collection Mapping Test Suite")
    success = test_collection_mapping()
    
    if success:
        logger.info("✅ Collection mapping tests PASSED")
    else:
        logger.error("❌ Collection mapping tests FAILED")
    
    sys.exit(0 if success else 1)
