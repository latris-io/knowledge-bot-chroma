#!/usr/bin/env python3
"""
Fix Stale Collection Mapping Drift - Root cause of 503 errors
"""

import requests
import json
import time
import logging

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def check_collection_exists_on_instance(instance_url, collection_id):
    """Check if collection actually exists on ChromaDB instance"""
    try:
        response = requests.get(
            f"{instance_url}/api/v2/tenants/default_tenant/databases/default_database/collections/{collection_id}",
            timeout=10
        )
        return response.status_code == 200
    except Exception as e:
        logger.error(f"Error checking collection {collection_id} on {instance_url}: {e}")
        return False

def get_all_mappings():
    """Get all collection mappings from load balancer"""
    try:
        response = requests.get("https://chroma-load-balancer.onrender.com/collection/mappings", timeout=10)
        if response.status_code == 200:
            return response.json().get('mappings', [])
        return []
    except Exception as e:
        logger.error(f"Error getting mappings: {e}")
        return []

def cleanup_stale_wal_entries():
    """Clean up failed WAL entries"""
    try:
        response = requests.post(
            "https://chroma-load-balancer.onrender.com/wal/cleanup",
            json={"max_age_hours": 1},  # Clean entries older than 1 hour
            timeout=30
        )
        logger.info(f"WAL cleanup: {response.status_code}")
        if response.status_code == 200:
            result = response.json()
            logger.info(f"Cleaned {result.get('cleaned', 0)} WAL entries")
        return response.status_code == 200
    except Exception as e:
        logger.error(f"Error cleaning WAL: {e}")
        return False

def delete_stale_mapping(collection_name):
    """Delete stale collection mapping"""
    try:
        response = requests.delete(
            f"https://chroma-load-balancer.onrender.com/collection/mappings/{collection_name}",
            timeout=10
        )
        logger.info(f"Delete mapping {collection_name}: {response.status_code}")
        return response.status_code in [200, 204, 404]
    except Exception as e:
        logger.error(f"Error deleting mapping {collection_name}: {e}")
        return False

def main():
    """Fix stale collection mapping drift causing 503 errors"""
    logger.info("🔧 FIXING STALE COLLECTION MAPPING DRIFT")
    logger.info("="*60)
    
    # Step 1: Get all current mappings
    logger.info("📋 Getting current collection mappings...")
    mappings = get_all_mappings()
    logger.info(f"Found {len(mappings)} collection mappings")
    
    if not mappings:
        logger.error("❌ Could not retrieve mappings")
        return False
    
    # Step 2: Check each mapping for stale collections
    logger.info("\n🔍 Checking for stale collection mappings...")
    stale_mappings = []
    primary_url = "https://chroma-primary.onrender.com"
    replica_url = "https://chroma-replica.onrender.com"
    
    for mapping in mappings:
        collection_name = mapping['collection_name']
        primary_id = mapping['primary_collection_id']
        replica_id = mapping['replica_collection_id']
        
        logger.info(f"  Checking: {collection_name}")
        
        # Check if collections actually exist on instances
        primary_exists = check_collection_exists_on_instance(primary_url, primary_id)
        replica_exists = check_collection_exists_on_instance(replica_url, replica_id)
        
        logger.info(f"    Primary {primary_id[:8]}...: {'✅' if primary_exists else '❌'}")
        logger.info(f"    Replica {replica_id[:8]}...: {'✅' if replica_exists else '❌'}")
        
        # If neither exists, it's stale
        if not primary_exists and not replica_exists:
            logger.warning(f"    ⚠️ STALE: Collection {collection_name} doesn't exist on either instance")
            stale_mappings.append(collection_name)
        elif not primary_exists or not replica_exists:
            logger.warning(f"    ⚠️ PARTIAL: Collection {collection_name} missing from one instance")
    
    # Step 3: Clean up stale mappings
    if stale_mappings:
        logger.info(f"\n🧹 Cleaning up {len(stale_mappings)} stale mappings...")
        for collection_name in stale_mappings:
            logger.info(f"  Deleting stale mapping: {collection_name}")
            success = delete_stale_mapping(collection_name)
            if success:
                logger.info(f"    ✅ Deleted mapping for {collection_name}")
            else:
                logger.error(f"    ❌ Failed to delete mapping for {collection_name}")
        
        # Wait for mapping updates to propagate
        logger.info("⏳ Waiting 5s for mapping updates to propagate...")
        time.sleep(5)
    else:
        logger.info("✅ No stale mappings found")
    
    # Step 4: Clean up failed WAL entries
    logger.info("\n🧹 Cleaning up failed WAL entries...")
    wal_cleaned = cleanup_stale_wal_entries()
    if wal_cleaned:
        logger.info("✅ WAL cleanup completed")
    else:
        logger.error("❌ WAL cleanup failed")
    
    # Step 5: Verify fix
    logger.info("\n🔍 Verifying fix by checking WAL status...")
    try:
        response = requests.get("https://chroma-load-balancer.onrender.com/wal/status", timeout=10)
        if response.status_code == 200:
            status = response.json()
            failed = status.get('failed', 0)
            pending = status.get('pending', 0)
            logger.info(f"📊 WAL Status: {failed} failed, {pending} pending")
            
            if failed == 0:
                logger.info("🎉 SUCCESS: All WAL failures resolved!")
                return True
            else:
                logger.warning(f"⚠️ Still have {failed} failed WAL entries")
                return False
        else:
            logger.error("❌ Could not verify WAL status")
            return False
    except Exception as e:
        logger.error(f"Error verifying status: {e}")
        return False

if __name__ == "__main__":
    success = main()
    if success:
        logger.info("\n✅ STALE MAPPING DRIFT FIXED")
        logger.info("🚀 503 errors should now be resolved")
    else:
        logger.error("\n❌ PARTIAL FIX - Some issues may remain")
    
    exit(0 if success else 1) 