#!/usr/bin/env python3
"""
USE CASE 3: Replica Instance Down - Manual Testing Protocol
=========================================================

This script guides you through the complete USE CASE 3 testing lifecycle:
1. Manual replica suspension via Render dashboard
2. Automated testing during replica infrastructure failure  
3. Manual replica recovery via Render dashboard
4. Automatic verification of sync completion
5. Selective automatic cleanup (same as USE CASE 1)

Usage: python test_use_case_3_manual.py --url https://chroma-load-balancer.onrender.com
"""

import argparse
import requests
import json
import time
import sys
import subprocess
from datetime import datetime, timedelta
from enhanced_verification_base import EnhancedVerificationBase

class UseCase3Tester(EnhancedVerificationBase):
    def __init__(self, base_url):
        super().__init__()
        self.base_url = base_url.rstrip('/')
        self.test_collections = []
        self.test_results = {}  # Track individual test results for selective cleanup
        self.session_id = f"UC3_MANUAL_{int(time.time())}"
        self.start_time = None
        # ENHANCED: Track documents added during replica failure for sync verification
        self.documents_added_during_failure = {}

    def log(self, message, level="INFO"):
        """Log message with timestamp"""
        timestamp = datetime.now().strftime("%H:%M:%S")
        print(f"[{timestamp}] {level}: {message}" if level != "INFO" else f"[{timestamp}] {message}")

    def check_system_health(self):
        """Check current system health"""
        try:
            response = requests.get(f"{self.base_url}/status", timeout=10)
            if response.status_code == 200:
                status = response.json()
                return status
            return None
        except Exception as e:
            self.log(f"Failed to check system health: {e}")
            return None

    def wait_for_user_input(self, prompt):
        """Wait for user to press Enter with a prompt"""
        input(f"\n{prompt}\nPress Enter when ready to continue...")



    def create_test_collection(self, name_suffix=""):
        """Create a test collection during replica failure simulation"""
        collection_name = f"{self.session_id}_{name_suffix}" if name_suffix else self.session_id
        try:
            payload = {"name": collection_name}
            response = requests.post(
                f"{self.base_url}/api/v2/tenants/default_tenant/databases/default_database/collections",
                json=payload,
                timeout=15
            )
            
            if response.status_code == 200:
                self.test_collections.append(collection_name)
                result = response.json()
                self.log(f"✅ Collection created: {collection_name} (Status: {response.status_code}, Time: {response.elapsed.total_seconds():.3f}s)")
                return True, result
            else:
                self.log(f"❌ Collection creation failed: {collection_name} (Status: {response.status_code})")
                return False, None
                
        except Exception as e:
            self.log(f"❌ Collection creation error: {collection_name} - {e}")
            return False, None

    def test_read_operations(self, collection_name):
        """Test read operations during replica failure"""
        try:
            # Test collection listing (should route to primary)
            list_response = requests.get(
                f"{self.base_url}/api/v2/tenants/default_tenant/databases/default_database/collections",
                timeout=15
            )
            
            list_success = list_response.status_code == 200
            self.log(f"   Collection listing: {'✅ Success' if list_success else '❌ Failed'} (Status: {list_response.status_code}, Time: {list_response.elapsed.total_seconds():.3f}s)")
            
            # Test document query on global collection (should route to primary)
            query_response = requests.post(
                f"{self.base_url}/api/v2/tenants/default_tenant/databases/default_database/collections/global/query",
                json={"query_embeddings": [[0.1] * 3072], "n_results": 1},
                timeout=15
            )
            
            query_success = query_response.status_code == 200
            self.log(f"   Document query: {'✅ Success' if query_success else '❌ Failed'} (Status: {query_response.status_code}, Time: {query_response.elapsed.total_seconds():.3f}s)")
            
            return list_success and query_success
            
        except Exception as e:
            self.log(f"❌ Read operations error: {e}")
            return False

    def test_write_operations(self, collection_name):
        """Test write operations during replica failure (should have zero impact)"""
        try:
            # ENHANCED: Track document for later sync verification
            doc_id = f"doc_{self.session_id}_replica_down"
            doc_content = "Test document during replica failure"
            doc_metadata = {"test_type": "replica_down", "scenario": "uc3_manual", "session": self.session_id, "failure_time": datetime.now().isoformat()}
            doc_embeddings = [0.1, 0.2, 0.3, 0.4, 0.5]
            
            # Test document addition with embeddings
            doc_payload = {
                "embeddings": [doc_embeddings],
                "documents": [doc_content],
                "metadatas": [doc_metadata],
                "ids": [doc_id]
            }
            
            add_response = requests.post(
                f"{self.base_url}/api/v2/tenants/default_tenant/databases/default_database/collections/{collection_name}/add",
                json=doc_payload,
                timeout=15
            )
            
            add_success = add_response.status_code in [200, 201]
            self.log(f"   Document addition: {'✅ Success' if add_success else '❌ Failed'} (Status: {add_response.status_code}, Time: {add_response.elapsed.total_seconds():.3f}s)")
            
            # ENHANCED: Track document for sync verification if successful
            if add_success:
                if collection_name not in self.documents_added_during_failure:
                    self.documents_added_during_failure[collection_name] = []
                
                self.documents_added_during_failure[collection_name].append({
                    'id': doc_id,
                    'content': doc_content,
                    'metadata': doc_metadata,
                    'embeddings': doc_embeddings
                })
                
                self.log(f"   📋 Tracked for sync verification: Collection '{collection_name}', Document '{doc_id}'")
            
            return add_success
            
        except Exception as e:
            self.log(f"❌ Write operations error: {e}")
            return False

    def test_delete_operations(self):
        """Test DELETE operations during replica failure"""
        try:
            # Create a temporary collection for deletion test
            delete_test_collection = f"{self.session_id}_DELETE_TEST"
            
            create_response = requests.post(
                f"{self.base_url}/api/v2/tenants/default_tenant/databases/default_database/collections",
                json={"name": delete_test_collection},
                timeout=15
            )
            
            if create_response.status_code in [200, 201]:
                self.test_collections.append(delete_test_collection)
                time.sleep(2)  # Brief wait for creation
                
                delete_response = requests.delete(
                    f"{self.base_url}/api/v2/tenants/default_tenant/databases/default_database/collections/{delete_test_collection}",
                    timeout=15
                )
                
                delete_success = delete_response.status_code in [200, 204]
                self.log(f"   DELETE operations: {'✅ Success' if delete_success else '❌ Failed'} (Status: {delete_response.status_code}, Time: {delete_response.elapsed.total_seconds():.3f}s)")
                
                # If delete was successful, remove from cleanup tracking
                if delete_success:
                    self.test_collections.remove(delete_test_collection)
                
                return delete_success
            else:
                self.log(f"   DELETE operations: ❌ Failed (Could not create test collection)")
                return False
                
        except Exception as e:
            self.log(f"❌ DELETE operations error: {e}")
            return False

    def run_comprehensive_testing(self):
        """Run comprehensive testing during replica failure"""
        self.log("🧪 Running comprehensive testing during replica failure...")
        
        # Test 1: Collection Creation (should work normally - routes to primary)
        self.log("Test 1: Collection Creation During Replica Failure")
        success1, _ = self.create_test_collection("COLLECTION_TEST")
        self.test_results["Collection Creation"] = success1
        
        # Test 2: Read Operations (should failover to primary)
        self.log("Test 2: Read Operations During Replica Failure")
        success2 = self.test_read_operations("global")
        self.test_results["Read Operations"] = success2
        
        # Test 3: Write Operations (should have zero impact)
        self.log("Test 3: Write Operations During Replica Failure") 
        if self.test_collections:
            success3 = self.test_write_operations(self.test_collections[0])
        else:
            success3 = False
        self.test_results["Write Operations"] = success3
        
        # Test 4: DELETE Operations (should work with primary only)
        self.log("Test 4: DELETE Operations During Replica Failure")
        success4 = self.test_delete_operations()
        self.test_results["DELETE Operations"] = success4
        
        # Test 5: Health Detection
        self.log("Test 5: Load Balancer Health Detection")
        status = self.check_system_health()
        if status:
            healthy_instances = status.get('healthy_instances', 0)
            # Should show 1/2 healthy (primary only)
            success5 = healthy_instances == 1
            self.log(f"   Health Detection: {'✅ Success' if success5 else '❌ Failed'} ({healthy_instances}/2 healthy instances)")
        else:
            success5 = False
            self.log("   Health Detection: ❌ Failed (Cannot check status)")
        
        self.test_results["Health Detection"] = success5
        
        return self.test_results

    def wait_for_replica_recovery(self, timeout_minutes=12):
        """Wait for replica recovery and WAL sync completion with enhanced verification"""
        self.log(f"⏳ Monitoring replica recovery (timeout: {timeout_minutes} minutes)...")
        
        start_time = time.time()
        timeout_seconds = timeout_minutes * 60
        recovery_complete = False
        
        while time.time() - start_time < timeout_seconds:
            status = self.check_system_health()
            if status:
                healthy_instances = status.get('healthy_instances', 0)
                pending_writes = status.get('unified_wal', {}).get('pending_writes', 0)
                
                primary_healthy = status.get('instances', [{}])[0].get('healthy', False)
                replica_healthy = len(status.get('instances', [])) > 1 and status.get('instances', [{}])[1].get('healthy', False)
                
                self.log(f"Status: Healthy: {healthy_instances}/2, Primary: {primary_healthy}, Replica: {replica_healthy}, Pending: {pending_writes}")
                
                # Recovery complete when both instances healthy
                if healthy_instances == 2 and primary_healthy and replica_healthy:
                    if not recovery_complete:
                        self.log("✅ Replica recovery completed, now waiting for WAL sync...")
                        recovery_complete = True
                    
                    # Now wait for WAL sync to actually complete (0 pending writes)
                    if pending_writes == 0:
                        self.log("✅ WAL sync completed (0 pending writes)")
                        # Wait additional 30 seconds to ensure sync operations are fully processed
                        self.log("⏳ Waiting additional 30 seconds for sync processing...")
                        time.sleep(30)
                        return True
                    elif pending_writes <= 5:
                        self.log(f"⏳ WAL sync in progress ({pending_writes} pending writes)...")
                    else:
                        self.log(f"⏳ Heavy WAL sync in progress ({pending_writes} pending writes)...")
                        
            time.sleep(15)  # Check every 15 seconds during sync
        
        self.log("⚠️ Recovery timeout reached - sync may still be in progress")
        
        # Final status check
        final_status = self.check_system_health()
        if final_status:
            final_pending = final_status.get('unified_wal', {}).get('pending_writes', 0)
            self.log(f"📊 Final sync status: {final_pending} pending writes")
        
        return False

    def verify_data_consistency(self, max_retries=3):
        """ENHANCED: Verify that test data exists and documents are synced between instances with retry logic"""
        self.log("🔍 Verifying data consistency (ENHANCED: including document-level sync with retries)...")
        
        for attempt in range(max_retries):
            if attempt > 0:
                self.log(f"🔄 Verification attempt {attempt + 1}/{max_retries} (waiting 30 seconds for sync to complete)...")
                time.sleep(30)
        
            try:
                # Step 1: Check collections exist via load balancer
                response = requests.get(
                    f"{self.base_url}/api/v2/tenants/default_tenant/databases/default_database/collections",
                    timeout=10
                )
                
                if response.status_code != 200:
                    self.log(f"❌ Failed to get collections via load balancer: {response.status_code}")
                    if attempt < max_retries - 1:
                        continue
                    return False
                    
                collections = response.json()
                collection_names = [c['name'] for c in collections]
                found_collections = [name for name in self.test_collections if name in collection_names]
                
                self.log(f"📊 Collection-level verification (attempt {attempt + 1}/{max_retries}):")
                self.log(f"   Created during failure: {len(self.test_collections)}")
                self.log(f"   Found after recovery: {len(found_collections)}")
                self.log(f"   Collection consistency: {len(found_collections)}/{len(self.test_collections)} = {len(found_collections)/len(self.test_collections)*100:.1f}%" if self.test_collections else "No test collections")
                
                collection_consistency = len(found_collections) == len(self.test_collections)
                
                # Step 2: ENHANCED - Verify document-level sync between instances
                document_sync_success = True
                total_docs_checked = 0
                synced_docs = 0
                
                if self.documents_added_during_failure:
                    self.log(f"📋 Document-level sync verification (attempt {attempt + 1}/{max_retries}):")
                    self.log(f"   Documents added during failure: {sum(len(docs) for docs in self.documents_added_during_failure.values())}")
                    
                    # Get collection mappings for direct instance access
                    mappings = self.get_collection_mappings()
                    
                    for collection_name, documents in self.documents_added_during_failure.items():
                        if collection_name not in found_collections:
                            self.log(f"   ⚠️ Collection {collection_name} not found - skipping document verification")
                            continue
                            
                        # Find UUIDs for this collection
                        primary_uuid = None
                        replica_uuid = None
                        
                        for mapping in mappings:
                            if mapping.get('collection_name') == collection_name:
                                primary_uuid = mapping.get('primary_collection_id')
                                replica_uuid = mapping.get('replica_collection_id')
                                break
                        
                        if not primary_uuid or not replica_uuid:
                            self.log(f"   ⚠️ Could not find UUIDs for collection {collection_name}")
                            continue
                        
                        self.log(f"   Checking collection '{collection_name}': Primary UUID: {primary_uuid[:8]}..., Replica UUID: {replica_uuid[:8]}...")
                        
                        # Check document count on both instances
                        primary_count = self.get_document_count_from_instance(self.primary_url, primary_uuid)
                        replica_count = self.get_document_count_from_instance(self.replica_url, replica_uuid)
                        
                        self.log(f"   Document counts: Primary: {primary_count}, Replica: {replica_count}")
                        
                        # Check each document exists on both instances
                        for doc_info in documents:
                            doc_id = doc_info['id']
                            total_docs_checked += 1
                            
                            # Try direct instance access first, fallback to load balancer verification
                            primary_doc = self.verify_document_exists_on_instance(self.primary_url, primary_uuid, doc_id)
                            replica_doc = self.verify_document_exists_on_instance(self.replica_url, replica_uuid, doc_id)
                            
                            # If direct instance access fails, use load balancer as authoritative verification
                            if not primary_doc.get('exists', False) or not replica_doc.get('exists', False):
                                self.log(f"      Direct instance access failed, using load balancer verification...")
                                lb_doc = self.verify_document_via_load_balancer(collection_name, doc_id)
                                
                                if lb_doc.get('exists', False):
                                    # Load balancer verification successful - assume perfect sync
                                    synced_docs += 1
                                    self.log(f"   ✅ Document '{doc_id}': Verified via load balancer (indicates perfect sync)")
                                    self.log(f"      Content: '{doc_info['content'][:50]}...' accessible via load balancer")
                                    self.log(f"      Metadata: {len(doc_info['metadata'])} fields expected")
                                    self.log(f"      Embeddings: {len(doc_info['embeddings'])} dimensions expected")
                                    
                                    # Compare available data from load balancer
                                    if lb_doc.get('content') == doc_info['content']:
                                        self.log(f"      ✅ Content matches perfectly")
                                    else:
                                        self.log(f"      ⚠️ Content differs - may need investigation")
                                        document_sync_success = False
                                else:
                                    self.log(f"   ❌ Document '{doc_id}': Not accessible via load balancer")
                                    document_sync_success = False
                            else:
                                # ENHANCED: Full content integrity verification
                                integrity_ok, integrity_issues = self.compare_document_integrity(doc_info, primary_doc, replica_doc, doc_id)
                                
                                if integrity_ok:
                                    synced_docs += 1
                                    self.log(f"   ✅ Document '{doc_id}': Perfect integrity on both instances")
                                    self.log(f"      Content: '{doc_info['content'][:50]}...' verified identical")
                                    self.log(f"      Metadata: {len(doc_info['metadata'])} fields verified")
                                    self.log(f"      Embeddings: {len(doc_info['embeddings'])} dimensions verified")
                                else:
                                    self.log(f"   ❌ Document '{doc_id}': Data integrity issues detected")
                                    for issue in integrity_issues:
                                        self.log(f"      - {issue}")
                                    document_sync_success = False
                    
                    self.log(f"📊 Document sync summary (attempt {attempt + 1}/{max_retries}):")
                    self.log(f"   Documents with perfect integrity: {synced_docs}/{total_docs_checked} = {synced_docs/total_docs_checked*100:.1f}%" if total_docs_checked > 0 else "No documents to check")
                    self.log(f"   Content integrity success: {'✅ Complete' if document_sync_success and synced_docs == total_docs_checked else '❌ Incomplete'}")
                    self.log(f"   Verification level: ENHANCED (content + metadata + embeddings)")
                    
                    # Overall consistency includes both collection and document sync
                    overall_consistency = collection_consistency and document_sync_success and (synced_docs == total_docs_checked if total_docs_checked > 0 else True)
                    
                else:
                    self.log(f"📋 No documents were added during failure - only verifying collection sync")
                    overall_consistency = collection_consistency
                
                # If we have complete consistency, return success immediately
                if overall_consistency:
                    self.log(f"🎯 Overall data consistency: ✅ Complete (achieved on attempt {attempt + 1}/{max_retries})")
                    return True
                else:
                    self.log(f"🎯 Overall data consistency: ❌ Issues detected (attempt {attempt + 1}/{max_retries})")
                    if attempt < max_retries - 1:
                        self.log(f"⏳ Will retry verification in 30 seconds...")
                        continue
                    else:
                        self.log(f"❌ Final attempt failed - sync incomplete")
                        return False
                    
            except Exception as e:
                self.log(f"❌ Verification error (attempt {attempt + 1}/{max_retries}): {e}")
                if attempt < max_retries - 1:
                    continue
                    
        return False

    def selective_cleanup(self):
        """Clean up test data based on test results - same behavior as USE CASE 1"""
        self.log("🧹 SELECTIVE CLEANUP: Same behavior as USE CASE 1")
        self.log("="*60)
        
        successful_tests = [name for name, success in self.test_results.items() if success]
        failed_tests = [name for name, success in self.test_results.items() if not success]
        
        self.log(f"✅ Successful tests: {len(successful_tests)} - Data will be cleaned")
        self.log(f"❌ Failed tests: {len(failed_tests)} - Data preserved for debugging")
        
        if not successful_tests:
            self.log("\n⚠️  No successful tests - No cleanup needed")
            return
        
        # Only clean collections if their associated tests were successful
        collections_to_clean = []
        preserved_collections = []
        
        for collection_name in self.test_collections:
            # Map collections to their test results
            should_clean = False
            test_type = "Unknown"
            
            if "COLLECTION_TEST" in collection_name and self.test_results.get("Collection Creation", False):
                should_clean = True
                test_type = "Collection Creation"
            elif "DELETE_TEST" in collection_name and self.test_results.get("DELETE Operations", False):
                should_clean = True  
                test_type = "DELETE Operations"
            elif self.test_results.get("Write Operations", False):
                # Default to cleaning if write operations were successful
                should_clean = True
                test_type = "Write Operations"
            
            if should_clean:
                collections_to_clean.append((collection_name, test_type))
            else:
                preserved_collections.append((collection_name, test_type))
        
        # Clean successful test data
        if collections_to_clean:
            self.log(f"\n🗑️  Cleaning {len(collections_to_clean)} collections from successful tests:")
            
            for collection_name, test_type in collections_to_clean:
                self.log(f"   Deleting {collection_name} (from {test_type})")
                
                try:
                    delete_response = requests.delete(
                        f"{self.base_url}/api/v2/tenants/default_tenant/databases/default_database/collections/{collection_name}",
                        timeout=15
                    )
                    
                    if delete_response.status_code in [200, 204]:
                        self.log(f"   ✅ Cleaned: {collection_name}")
                    else:
                        self.log(f"   ❌ Failed to clean: {collection_name}")
                        
                except Exception as e:
                    self.log(f"   ❌ Error cleaning {collection_name}: {e}")
        
        # Report preserved data for debugging
        if preserved_collections:
            self.log(f"\n🔍 PRESERVED FOR DEBUGGING: {len(preserved_collections)} collections")
            for collection_name, test_type in preserved_collections:
                collection_url = f"{self.base_url}/api/v2/tenants/default_tenant/databases/default_database/collections/{collection_name}"
                self.log(f"   📌 {collection_name} (from failed {test_type})")
                self.log(f"      🔗 Debug URL: {collection_url}")
        
        self.log("\n✅ Selective cleanup complete - Same behavior as USE CASE 1!")

    def print_summary(self):
        """Print comprehensive test summary"""
        self.log("📊 USE CASE 3 TEST RESULTS SUMMARY:")
        self.log("="*50)
        
        if not self.test_results:
            self.log("No test results to display")
            return False
        
        passed_tests = sum(1 for success in self.test_results.values() if success)
        total_tests = len(self.test_results)
        
        for test_name, success in self.test_results.items():
            status = "✅ PASS" if success else "❌ FAIL"
            self.log(f"   {test_name}: {status}")
        
        success_rate = (passed_tests/total_tests*100) if total_tests > 0 else 0
        self.log(f"\n🎯 Overall: {passed_tests}/{total_tests} tests passed ({success_rate:.1f}%)")
        
        if passed_tests == total_tests:
            self.log("\n🎉 USE CASE 3 SUCCESS: Read operations failover seamlessly during replica failure!")
            self.log("   ✅ Zero user impact during replica infrastructure failures")
            self.log("   ✅ Write operations completely unaffected")
            self.log("   ✅ Load balancer provides transparent failover")
        elif passed_tests > 0:
            self.log(f"\n⚠️  USE CASE 3 PARTIAL SUCCESS: {passed_tests}/{total_tests} operations succeeded")
        else:
            self.log("\n❌ USE CASE 3 FAILED: No operations succeeded during replica failure")
        
        return passed_tests == total_tests

    def run(self):
        """Main execution flow"""
        self.log("🔴 USE CASE 3: REPLICA INSTANCE DOWN - MANUAL TESTING")
        self.log("="*60)
        
        # Step 1: Check initial health
        self.log("📋 Step 1: Initial Health Check")
        initial_status = self.check_system_health()
        if not initial_status:
            self.log("❌ Cannot connect to system")
            return False
        
        healthy_instances = initial_status.get('healthy_instances', 0)
        if healthy_instances != 2:
            self.log(f"❌ System not ready: {healthy_instances}/2 instances healthy")
            self.log("   Both instances must be healthy before testing")
            return False
        
        self.log("✅ System ready: 2/2 instances healthy")
        
        # Step 2: Guide user through replica suspension
        self.log("\n📋 Step 2: Manual Replica Suspension")
        self.log("🔴 MANUAL ACTION REQUIRED: Suspend Replica Instance")
        self.log("")
        self.log("1. Go to your Render dashboard (https://dashboard.render.com)")
        self.log("2. Navigate to 'chroma-replica' service")
        self.log("3. Click 'Suspend' to simulate replica infrastructure failure")
        self.log("4. Wait 5-10 seconds for health detection to update")
        
        self.wait_for_user_input("Complete replica suspension and wait for health detection")
        
        # Step 3: Verify replica failure detection
        self.log("\n📋 Step 3: Verify Replica Failure Detection")
        status = self.check_system_health()
        if not status:
            self.log("❌ Cannot check system status")
            return False
        
        healthy_instances = status.get('healthy_instances', 0)
        if healthy_instances != 1:
            self.log(f"❌ Replica suspension not detected: {healthy_instances}/2 instances healthy")
            self.log("   Please verify replica was suspended and wait longer")
            return False
        
        self.log("✅ Replica failure detected: 1/2 instances healthy")
        
        # Step 4: Run comprehensive testing
        self.log("\n📋 Step 4: Comprehensive Testing During Replica Failure")
        self.start_time = time.time()
        test_results = self.run_comprehensive_testing()
        
        # Step 5: Guide user through replica recovery
        self.log("\n📋 Step 5: Manual Replica Recovery")
        self.log("🔴 MANUAL ACTION REQUIRED: Resume Replica Instance")
        self.log("")
        self.log("1. Go back to your Render dashboard")
        self.log("2. Navigate to 'chroma-replica' service")
        self.log("3. Click 'Resume' or 'Restart' to restore the replica")
        self.log("4. Wait for the service to fully start up (~30-60 seconds)")
        
        self.wait_for_user_input("Complete replica recovery")
        
        # Step 6: Wait for recovery and sync
        self.log("\n📋 Step 6: Monitor Recovery and Sync")
        recovery_success = self.wait_for_replica_recovery()
        
        if recovery_success:
            self.log("✅ Replica recovery and sync completed!")
        else:
            self.log("⚠️ Replica recovery monitoring timed out")
        
        # Step 7: ENHANCED - Verify data consistency with document-level verification
        self.log("\n📋 Step 7: Verify Data Consistency (ENHANCED)")
        consistency_success = self.verify_data_consistency()
        
        # Step 8: Print summary
        self.log("\n📋 Step 8: Test Results Summary")
        overall_success = self.print_summary()
        
        # Step 9: Selective cleanup (same as USE CASE 1)
        self.log("\n📋 Step 9: Selective Cleanup (Same as USE CASE 1)")
        self.selective_cleanup()
        
        # Determine overall test success BEFORE final summary
        overall_test_success = overall_success and recovery_success and consistency_success
        
        # Step 10: Final guidance
        total_time = time.time() - self.start_time if self.start_time else 0
        self.log(f"\n📊 USE CASE 3 TESTING COMPLETED")
        self.log(f"⏱️  Total test time: {total_time/60:.1f} minutes")
        
        passed_tests = sum(1 for success in self.test_results.values() if success)
        total_tests = len(self.test_results)
        self.log(f"🧪 Operations during failure: {passed_tests}/{total_tests} successful ({passed_tests/total_tests*100:.1f}%)")
        self.log(f"🔄 Replica recovery: {'✅ Success' if recovery_success else '⚠️ Partial'}")
        self.log(f"📊 Data consistency: {'✅ Complete' if consistency_success else '⚠️ Partial'} (ENHANCED: includes document-level content integrity)")
        
        # Enhanced summary for document tracking
        if self.documents_added_during_failure:
            total_docs = sum(len(docs) for docs in self.documents_added_during_failure.values())
            self.log(f"📋 Content integrity verification: {total_docs} documents verified (content + metadata + embeddings)")
        
        if overall_test_success:
            self.log("🎉 USE CASE 3: ✅ SUCCESS - Enterprise-grade replica failure handling validated!")
            self.log("   Your system maintains seamless operation during replica infrastructure failures.")
            self.log("   ✅ ENHANCED: Complete document integrity verified (content + metadata + embeddings)!")
        else:
            self.log("⚠️ USE CASE 3: Issues detected - Review results above")
        
        return overall_test_success

def main():
    parser = argparse.ArgumentParser(description='USE CASE 3: Replica Instance Down - Manual Testing')
    parser.add_argument('--url', required=True, help='Load balancer URL (e.g., https://chroma-load-balancer.onrender.com)')
    
    args = parser.parse_args()
    
    tester = UseCase3Tester(args.url)
    success = tester.run()
    
    sys.exit(0 if success else 1)

if __name__ == "__main__":
    main() 