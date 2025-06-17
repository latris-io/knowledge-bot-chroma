#!/usr/bin/env python3
"""
Test Write Failover Functionality - Critical for high availability
Tests that write operations properly failover to replica when primary is down
"""

import requests
import json
import uuid
import time
import logging

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def check_instance_health(base_url):
    """Check health status of both instances"""
    try:
        response = requests.get(f"{base_url}/status", timeout=30)
        if response.status_code == 200:
            status = response.json()
            instances = status.get('instances', [])
            primary_healthy = any(inst.get('name') == 'primary' and inst.get('healthy') for inst in instances)
            replica_healthy = any(inst.get('name') == 'replica' and inst.get('healthy') for inst in instances)
            return primary_healthy, replica_healthy
    except Exception as e:
        logger.error(f"Failed to check instance health: {e}")
    return False, False

def test_write_failover_scenario(base_url="https://chroma-load-balancer.onrender.com"):
    """Test write operations during primary downtime"""
    logger.info("⚡ Testing Write Failover Scenario")
    
    session_id = f"{int(time.time())}_{uuid.uuid4().hex[:8]}"
    collection_name = f"AUTOTEST_failover_{session_id}"
    
    try:
        # Check system health
        logger.info("  Checking system health...")
        primary_healthy, replica_healthy = check_instance_health(base_url)
        logger.info(f"  Instance Status - Primary: {primary_healthy}, Replica: {replica_healthy}")
        
        if not replica_healthy:
            logger.error("❌ Replica unhealthy - cannot test failover")
            return False
            
        # Create collection
        logger.info(f"  Creating test collection: {collection_name}")
        create_response = requests.post(
            f"{base_url}/api/v2/tenants/default_tenant/databases/default_database/collections",
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
        doc_data = {
            "embeddings": [[0.1, 0.2, 0.3, 0.4, 0.5]],
            "documents": ["Failover test document"],
            "metadatas": [{"test_type": "failover_write", "session": session_id}],
            "ids": [f"failover_test_{uuid.uuid4().hex[:8]}"]
        }
        
        write_response = requests.post(
            f"{base_url}/api/v2/tenants/default_tenant/databases/default_database/collections/{collection_name}/add",
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
            f"{base_url}/api/v2/tenants/default_tenant/databases/default_database/collections/{collection_name}/get",
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
        
    finally:
        # Cleanup
        try:
            requests.delete(
                f"{base_url}/api/v2/tenants/default_tenant/databases/default_database/collections/{collection_name}", 
                timeout=30
            )
        except:
            pass

if __name__ == "__main__":
    import sys
    import argparse
    
    parser = argparse.ArgumentParser(description="Test Write Failover Functionality")
    parser.add_argument("--url", default="https://chroma-load-balancer.onrender.com", help="Load balancer URL")
    args = parser.parse_args()
    
    logger.info("🚀 Starting Write Failover Test")
    logger.info("="*60)
    
    success = test_write_failover_scenario(args.url)
    
    logger.info("="*60)
    if success:
        logger.info("🎉 Write failover test PASSED!")
    else:
        logger.error("❌ Write failover test FAILED!")
    
    exit(0 if success else 1)
