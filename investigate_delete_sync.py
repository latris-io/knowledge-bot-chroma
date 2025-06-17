#!/usr/bin/env python3
"""
DELETE Sync Investigation - Comprehensive analysis of deletion sync failures
"""

import requests
import json
import uuid
import time
import logging
from test_base_cleanup import BulletproofTestBase

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class DeleteSyncInvestigation(BulletproofTestBase):
    """Investigation class for DELETE sync issues"""
    
    def __init__(self, base_url="https://chroma-load-balancer.onrender.com"):
        super().__init__(base_url, test_prefix="AUTOTEST_delete_investigation")
        self.primary_url = "https://chroma-primary.onrender.com"
        self.replica_url = "https://chroma-replica.onrender.com"

    def check_instance_collections(self, instance_url, instance_name, collection_name=None):
        """Check collections on a specific instance"""
        try:
            response = requests.get(
                f"{instance_url}/api/v2/tenants/default_tenant/databases/default_database/collections",
                timeout=10
            )
            
            if response.status_code == 200:
                collections = response.json()
                count = len(collections)
                logger.info(f"  📚 {instance_name}: {count} total collections")
                
                if collection_name:
                    found = any(c.get('name') == collection_name for c in collections)
                    logger.info(f"  🔍 {instance_name}: Collection '{collection_name}' {'✅ EXISTS' if found else '❌ NOT FOUND'}")
                    return found
                return True
            else:
                logger.error(f"  ❌ {instance_name}: Failed to list collections ({response.status_code})")
                return False
                
        except Exception as e:
            logger.error(f"  ❌ {instance_name}: Exception checking collections - {e}")
            return False

    def check_collection_by_uuid(self, instance_url, instance_name, collection_uuid):
        """Check if collection exists by UUID on specific instance"""
        try:
            response = requests.get(
                f"{instance_url}/api/v2/tenants/default_tenant/databases/default_database/collections/{collection_uuid}",
                timeout=10
            )
            
            exists = response.status_code == 200
            logger.info(f"  🔍 {instance_name}: UUID {collection_uuid[:8]}... {'✅ EXISTS' if exists else '❌ NOT FOUND'}")
            return exists
            
        except Exception as e:
            logger.error(f"  ❌ {instance_name}: Exception checking UUID - {e}")
            return False

    def get_collection_mapping(self, collection_name):
        """Get collection mapping details"""
        try:
            response = self.make_request('GET', f"{self.base_url}/collection/mappings")
            if response.status_code == 200:
                mappings_data = response.json()
                for mapping in mappings_data.get('mappings', []):
                    if mapping['collection_name'] == collection_name:
                        return mapping
            return None
        except Exception as e:
            logger.error(f"Error getting mapping for {collection_name}: {e}")
            return None

    def check_wal_entries_for_collection(self, collection_name):
        """Check WAL entries related to specific collection"""
        try:
            # Get recent WAL entries
            response = self.make_request('GET', f"{self.base_url}/wal/status")
            if response.status_code == 200:
                status = response.json()
                logger.info(f"  📊 WAL Status: {status.get('failed', 0)} failed, {status.get('pending', 0)} pending")
                
                # Check if there are specific entries for our collection
                logger.info(f"  🔍 Checking for DELETE operations in WAL...")
                return True
            return False
        except Exception as e:
            logger.error(f"Error checking WAL entries: {e}")
            return False

    def test_delete_sync_step_by_step(self):
        """Step-by-step DELETE sync investigation"""
        logger.info("🔍 STEP-BY-STEP DELETE SYNC INVESTIGATION")
        
        start_time = time.time()
        collection_name = self.create_unique_collection_name("step_by_step")
        
        try:
            # Step 1: Create collection via load balancer
            logger.info(f"📚 Step 1: Creating collection via load balancer")
            logger.info(f"   Collection: {collection_name}")
            
            create_response = self.make_request(
                'POST',
                f"{self.base_url}/api/v2/tenants/default_tenant/databases/default_database/collections",
                json={"name": collection_name}
            )
            
            if create_response.status_code not in [200, 201]:
                return self.log_test_result(
                    "DELETE Sync Investigation - Step 1",
                    False,
                    f"Collection creation failed: {create_response.status_code}",
                    time.time() - start_time
                )
            
            collection_data = create_response.json()
            primary_uuid = collection_data.get('id')
            logger.info(f"   ✅ Collection created with primary UUID: {primary_uuid}")
            
            # Step 2: Wait for initial sync and verify presence on both instances
            logger.info(f"⏳ Step 2: Waiting 15s for initial sync...")
            time.sleep(15)
            
            logger.info(f"🔍 Step 2a: Checking collection presence on both instances")
            primary_exists = self.check_instance_collections(self.primary_url, "Primary", collection_name)
            replica_exists = self.check_instance_collections(self.replica_url, "Replica", collection_name)
            
            # Get mapping details
            mapping = self.get_collection_mapping(collection_name)
            if mapping:
                replica_uuid = mapping.get('replica_collection_id')
                logger.info(f"   📋 Mapping: Primary {primary_uuid[:8]}... ↔ Replica {replica_uuid[:8]}...")
                
                # Verify UUIDs exist on instances
                logger.info(f"🔍 Step 2b: Verifying UUIDs on instances")
                primary_uuid_exists = self.check_collection_by_uuid(self.primary_url, "Primary", primary_uuid)
                replica_uuid_exists = self.check_collection_by_uuid(self.replica_url, "Replica", replica_uuid)
                
                if not (primary_exists and replica_exists and primary_uuid_exists and replica_uuid_exists):
                    return self.log_test_result(
                        "DELETE Sync Investigation - Step 2",
                        False,
                        f"Initial sync failed: P={primary_exists}, R={replica_exists}",
                        time.time() - start_time
                    )
            else:
                return self.log_test_result(
                    "DELETE Sync Investigation - Step 2",
                    False,
                    "Collection mapping not found",
                    time.time() - start_time
                )
            
            logger.info(f"   ✅ Both instances have the collection")
            
            # Step 3: Execute DELETE via load balancer
            logger.info(f"🗑️ Step 3: Executing DELETE via load balancer")
            
            delete_response = self.make_request(
                'DELETE',
                f"{self.base_url}/api/v2/tenants/default_tenant/databases/default_database/collections/{collection_name}"
            )
            
            logger.info(f"   📊 DELETE Response: {delete_response.status_code}")
            if delete_response.status_code not in [200, 204]:
                return self.log_test_result(
                    "DELETE Sync Investigation - Step 3",
                    False,
                    f"DELETE request failed: {delete_response.status_code}",
                    time.time() - start_time
                )
            
            logger.info(f"   ✅ DELETE request successful")
            
            # Step 4: Check immediate state after DELETE
            logger.info(f"🔍 Step 4: Checking immediate state after DELETE")
            
            # Check if collection still exists via load balancer
            immediate_check = self.make_request(
                'GET',
                f"{self.base_url}/api/v2/tenants/default_tenant/databases/default_database/collections/{collection_name}"
            )
            logger.info(f"   📊 Load Balancer GET: {immediate_check.status_code}")
            
            # Check on both instances directly
            primary_after_delete = self.check_collection_by_uuid(self.primary_url, "Primary", primary_uuid)
            replica_after_delete = self.check_collection_by_uuid(self.replica_url, "Replica", replica_uuid)
            
            logger.info(f"   📋 After DELETE - Primary: {'EXISTS' if primary_after_delete else 'DELETED'}")
            logger.info(f"   📋 After DELETE - Replica: {'EXISTS' if replica_after_delete else 'DELETED'}")
            
            # Step 5: Check WAL for DELETE operations
            logger.info(f"🔍 Step 5: Checking WAL for DELETE operations")
            self.check_wal_entries_for_collection(collection_name)
            
            # Step 6: Wait for sync and verify final state
            logger.info(f"⏳ Step 6: Waiting 20s for DELETE sync...")
            time.sleep(20)
            
            logger.info(f"🔍 Step 6a: Final verification")
            
            # Final check via load balancer
            final_lb_check = self.make_request(
                'GET',
                f"{self.base_url}/api/v2/tenants/default_tenant/databases/default_database/collections/{collection_name}"
            )
            logger.info(f"   📊 Final Load Balancer GET: {final_lb_check.status_code}")
            
            # Final check on both instances
            final_primary = self.check_collection_by_uuid(self.primary_url, "Primary", primary_uuid)
            final_replica = self.check_collection_by_uuid(self.replica_url, "Replica", replica_uuid)
            
            logger.info(f"   📋 Final State - Primary: {'EXISTS' if final_primary else 'DELETED'}")
            logger.info(f"   📋 Final State - Replica: {'EXISTS' if final_replica else 'DELETED'}")
            
            # Check mapping still exists
            final_mapping = self.get_collection_mapping(collection_name)
            logger.info(f"   📋 Final Mapping: {'EXISTS' if final_mapping else 'DELETED'}")
            
            # Determine success
            delete_synced = not final_primary and not final_replica and final_lb_check.status_code == 404
            
            if delete_synced:
                return self.log_test_result(
                    "DELETE Sync Investigation - Complete",
                    True,
                    "DELETE properly synced to both instances",
                    time.time() - start_time
                )
            else:
                failure_details = []
                if final_primary:
                    failure_details.append("Primary still has collection")
                if final_replica:
                    failure_details.append("Replica still has collection")
                if final_lb_check.status_code != 404:
                    failure_details.append(f"Load balancer returns {final_lb_check.status_code}")
                
                return self.log_test_result(
                    "DELETE Sync Investigation - Complete",
                    False,
                    f"DELETE sync failed: {', '.join(failure_details)}",
                    time.time() - start_time
                )
            
        except Exception as e:
            return self.log_test_result(
                "DELETE Sync Investigation - Complete",
                False,
                f"Exception: {str(e)}",
                time.time() - start_time
            )

    def test_direct_delete_comparison(self):
        """Compare DELETE behavior: load balancer vs direct instances"""
        logger.info("🔍 DIRECT DELETE COMPARISON")
        
        start_time = time.time()
        
        try:
            # Test 1: DELETE via load balancer
            logger.info("  🧪 Test 1: DELETE via Load Balancer")
            lb_collection = self.create_unique_collection_name("lb_delete")
            
            # Create via LB
            create_resp = self.make_request(
                'POST',
                f"{self.base_url}/api/v2/tenants/default_tenant/databases/default_database/collections",
                json={"name": lb_collection}
            )
            
            if create_resp.status_code in [200, 201]:
                lb_uuid = create_resp.json().get('id')
                logger.info(f"    Created: {lb_collection} ({lb_uuid[:8]}...)")
                
                time.sleep(10)  # Wait for sync
                
                # DELETE via LB
                delete_resp = self.make_request(
                    'DELETE',
                    f"{self.base_url}/api/v2/tenants/default_tenant/databases/default_database/collections/{lb_collection}"
                )
                logger.info(f"    DELETE via LB: {delete_resp.status_code}")
                
                time.sleep(15)  # Wait for sync
                
                # Check if still exists
                check_resp = self.make_request(
                    'GET',
                    f"{self.base_url}/api/v2/tenants/default_tenant/databases/default_database/collections/{lb_collection}"
                )
                logger.info(f"    Post-DELETE check: {check_resp.status_code}")
                lb_delete_success = check_resp.status_code == 404
                logger.info(f"    LB Delete Success: {'✅' if lb_delete_success else '❌'}")
            
            # Test 2: DELETE directly on primary
            logger.info("  🧪 Test 2: DELETE directly on Primary")
            direct_collection = self.create_unique_collection_name("direct_delete")
            
            # Create via primary
            direct_create_resp = requests.post(
                f"{self.primary_url}/api/v2/tenants/default_tenant/databases/default_database/collections",
                json={"name": direct_collection},
                timeout=30
            )
            
            if direct_create_resp.status_code in [200, 201]:
                direct_uuid = direct_create_resp.json().get('id')
                logger.info(f"    Created: {direct_collection} ({direct_uuid[:8]}...)")
                
                # DELETE via primary
                direct_delete_resp = requests.delete(
                    f"{self.primary_url}/api/v2/tenants/default_tenant/databases/default_database/collections/{direct_uuid}",
                    timeout=30
                )
                logger.info(f"    DELETE via Primary: {direct_delete_resp.status_code}")
                
                # Check if still exists on primary
                direct_check_resp = requests.get(
                    f"{self.primary_url}/api/v2/tenants/default_tenant/databases/default_database/collections/{direct_uuid}",
                    timeout=30
                )
                logger.info(f"    Post-DELETE check: {direct_check_resp.status_code}")
                direct_delete_success = direct_check_resp.status_code == 404
                logger.info(f"    Direct Delete Success: {'✅' if direct_delete_success else '❌'}")
            
            # Analysis
            if lb_delete_success and direct_delete_success:
                analysis = "Both load balancer and direct deletes work - sync timing issue"
            elif lb_delete_success and not direct_delete_success:
                analysis = "Load balancer delete works, direct delete fails - LB has special logic"
            elif not lb_delete_success and direct_delete_success:
                analysis = "Direct delete works, LB delete fails - LB routing issue"
            else:
                analysis = "Both delete methods failing - fundamental DELETE issue"
            
            logger.info(f"  🎯 ANALYSIS: {analysis}")
            
            return self.log_test_result(
                "Direct DELETE Comparison",
                lb_delete_success or direct_delete_success,
                analysis,
                time.time() - start_time
            )
            
        except Exception as e:
            return self.log_test_result(
                "Direct DELETE Comparison",
                False,
                f"Exception: {str(e)}",
                time.time() - start_time
            )

def main():
    """Run DELETE sync investigation"""
    import argparse
    
    parser = argparse.ArgumentParser(description="Investigate DELETE Sync Issues")
    parser.add_argument("--url", default="https://chroma-load-balancer.onrender.com", help="Load balancer URL")
    args = parser.parse_args()
    
    investigator = DeleteSyncInvestigation(args.url)
    
    logger.info("🚀 Starting DELETE Sync Investigation")
    logger.info(f"🌐 Target URL: {args.url}")
    logger.info("="*80)
    
    try:
        # Run investigations
        logger.info("\n1️⃣ Step-by-Step DELETE Sync Investigation...")
        test1_success = investigator.test_delete_sync_step_by_step()
        
        logger.info("\n2️⃣ Direct DELETE Comparison...")
        test2_success = investigator.test_direct_delete_comparison()
        
    finally:
        # Always cleanup - but carefully since we're testing deletes
        try:
            investigator.comprehensive_cleanup()
        except Exception as e:
            logger.warning(f"Cleanup had issues (expected with DELETE testing): {e}")
    
    # Print results
    overall_success = investigator.print_test_summary()
    
    logger.info("\n" + "="*80)
    logger.info("🎯 DELETE SYNC INVESTIGATION COMPLETE")
    logger.info("="*80)
    
    return overall_success

if __name__ == "__main__":
    success = main()
    exit(0 if success else 1) 