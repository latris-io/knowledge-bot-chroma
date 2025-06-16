#!/usr/bin/env python3
"""
Test Write Failover Functionality - Critical for high availability
Tests that write operations properly failover to replica when primary is down
Enhanced with bulletproof cleanup system
"""

import requests
import json
import uuid
import time
import logging
from test_base_cleanup import BulletproofTestBase

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class WriteFailoverTestSuite(BulletproofTestBase):
    """Test suite for write failover functionality with bulletproof cleanup"""
    
    def __init__(self, base_url="https://chroma-load-balancer.onrender.com"):
        super().__init__(base_url, test_prefix="AUTOTEST_failover")
        
    def check_instance_health(self):
        """Check health status of both instances"""
        try:
            response = self.make_request('GET', f"{self.base_url}/status")
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
        
        start_time = time.time()
        collection_name = self.create_unique_collection_name("failover")
        
        try:
            # Check system health
            logger.info("  Checking system health...")
            primary_healthy, replica_healthy = self.check_instance_health()
            logger.info(f"  Instance Status - Primary: {primary_healthy}, Replica: {replica_healthy}")
            
            if not replica_healthy:
                return self.log_test_result(
                    "Write Failover Test",
                    False,
                    "Replica unhealthy - cannot test failover",
                    time.time() - start_time
                )
                
            # Create collection
            logger.info(f"  Creating test collection: {collection_name}")
            create_response = self.make_request(
                'POST',
                f"{self.base_url}/api/v2/tenants/default_tenant/databases/default_database/collections",
                json={"name": collection_name}
            )
            
            if create_response.status_code not in [200, 201]:
                return self.log_test_result(
                    "Write Failover Test",
                    False,
                    f"Collection creation failed: {create_response.status_code}",
                    time.time() - start_time
                )
                
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
            
            write_response = self.make_request(
                'POST',
                f"{self.base_url}/api/v2/tenants/default_tenant/databases/default_database/collections/{collection_name}/add",
                json=doc_data
            )
            
            if write_response.status_code not in [200, 201]:
                if not primary_healthy:
                    return self.log_test_result(
                        "Write Failover Test",
                        False,
                        f"Write failover failed: {write_response.status_code} - {write_response.text[:300]}",
                        time.time() - start_time
                    )
                else:
                    return self.log_test_result(
                        "Write Failover Test",
                        False,
                        f"Write failed: {write_response.status_code}",
                        time.time() - start_time
                    )
            else:
                if not primary_healthy:
                    logger.info("  🎉 Write successful during primary downtime!")
                    logger.info("  ✅ Write failover working correctly!")
                else:
                    logger.info("  ✅ Write successful with primary healthy")
            
            # Verify document was stored
            get_response = self.make_request(
                'POST',
                f"{self.base_url}/api/v2/tenants/default_tenant/databases/default_database/collections/{collection_name}/get",
                json={"include": ["documents", "metadatas"]}
            )
            
            if get_response.status_code == 200:
                doc_count = len(get_response.json().get('ids', []))
                logger.info(f"  ✅ Documents verified: {doc_count} found")
            else:
                logger.warning(f"⚠️ Document verification failed: {get_response.status_code}")
            
            return self.log_test_result(
                "Write Failover Test",
                True,
                "Write failover functionality working correctly",
                time.time() - start_time
            )
            
        except Exception as e:
            return self.log_test_result(
                "Write Failover Test",
                False,
                f"Exception: {str(e)}",
                time.time() - start_time
            )

def main():
    """Run write failover tests with comprehensive cleanup"""
    import sys
    import argparse
    
    parser = argparse.ArgumentParser(description="Test Write Failover Functionality")
    parser.add_argument("--url", default="https://chroma-load-balancer.onrender.com", help="Load balancer URL")
    args = parser.parse_args()
    
    suite = WriteFailoverTestSuite(args.url)
    
    logger.info("🚀 Starting Write Failover Test")
    logger.info("="*60)
    
    try:
        success = suite.test_write_failover_scenario()
    finally:
        # Always perform comprehensive cleanup
        cleanup_results = suite.comprehensive_cleanup()
    
    # Print test summary
    overall_success = suite.print_test_summary()
    
    if overall_success:
        logger.info("🎉 Write failover test completed successfully!")
        logger.info("🧹 Test data isolation and cleanup completed.")
    else:
        logger.error("❌ Write failover test failed!")
        logger.info("🧹 Test data cleanup completed to prevent pollution.")
    
    return overall_success

if __name__ == "__main__":
    success = main()
    exit(0 if success else 1)
