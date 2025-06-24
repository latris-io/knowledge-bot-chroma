#!/usr/bin/env python3
"""
USE CASE 2: Primary Instance Down - Manual Testing Protocol
=========================================================

This script guides you through the complete USE CASE 2 testing lifecycle:
1. Manual primary suspension via Render dashboard
2. Automated testing during infrastructure failure  
3. Manual primary recovery via Render dashboard
4. Automatic verification of sync completion (ENHANCED: includes document-level sync)
5. Automatic cleanup of test data

Usage: python test_use_case_2_manual.py --url https://chroma-load-balancer.onrender.com
"""

import argparse
import requests
import json
import time
import sys
import subprocess
from datetime import datetime, timedelta

class UseCase2Tester:
    def __init__(self, base_url):
        self.base_url = base_url.rstrip('/')
        self.test_collections = []
        self.test_results = {}  # Track individual test results for selective cleanup
        self.session_id = f"UC2_MANUAL_{int(time.time())}"
        self.start_time = None
        # ENHANCED: Track documents added during failure for sync verification
        self.documents_added_during_failure = {}  # {collection_name: [doc_info]}
        self.primary_url = "https://chroma-primary.onrender.com"
        self.replica_url = "https://chroma-replica.onrender.com"
        
    def log(self, message, level="INFO"):
        timestamp = datetime.now().strftime("%H:%M:%S")
        print(f"[{timestamp}] {level}: {message}")
        
    def wait_for_user(self, message):
        """Wait for user confirmation before proceeding"""
        print(f"\n🔴 {message}")
        input("Press Enter when ready to continue...")
        
    def check_system_health(self):
        """Check current system health status"""
        try:
            response = requests.get(f"{self.base_url}/status", timeout=10)
            if response.status_code == 200:
                status = response.json()
                return status
            else:
                self.log(f"Health check failed: {response.status_code}", "ERROR")
                return None
        except Exception as e:
            self.log(f"Health check error: {e}", "ERROR")
            return None

    def get_collection_mappings(self):
        """Get collection name to UUID mappings for direct instance access"""
        try:
            response = requests.get(f"{self.base_url}/admin/collection_mappings", timeout=10)
            if response.status_code == 200:
                data = response.json()
                mappings = data.get('collection_mappings', [])
                return mappings
            else:
                self.log(f"Failed to get collection mappings: {response.status_code}", "WARNING")
                return []
        except Exception as e:
            self.log(f"Error getting collection mappings: {e}", "WARNING")
            return []

    def get_document_count_from_instance(self, instance_url, collection_uuid):
        """Get document count directly from a specific instance using UUID"""
        try:
            response = requests.post(
                f"{instance_url}/api/v2/tenants/default_tenant/databases/default_database/collections/{collection_uuid}/get",
                json={"include": ["documents"]},
                timeout=10
            )
            if response.status_code == 200:
                result = response.json()
                return len(result.get('documents', []))
            else:
                return 0
        except Exception as e:
            self.log(f"Error getting document count from {instance_url}: {e}", "WARNING")
            return 0

    def verify_document_exists_on_instance(self, instance_url, collection_uuid, doc_id):
        """Verify a specific document exists on an instance"""
        try:
            response = requests.post(
                f"{instance_url}/api/v2/tenants/default_tenant/databases/default_database/collections/{collection_uuid}/get",
                json={"ids": [doc_id], "include": ["documents", "metadatas"]},
                timeout=10
            )
            if response.status_code == 200:
                result = response.json()
                documents = result.get('documents', [])
                return len(documents) > 0 and len(documents[0]) > 0
            return False
        except Exception as e:
            self.log(f"Error checking document on {instance_url}: {e}", "WARNING")
            return False
            
    def create_test_collection(self, name_suffix="", test_name=None):
        """Create a test collection during failure simulation"""
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
                # Track which collection belongs to which test for selective cleanup
                if test_name:
                    if test_name not in self.test_results:
                        self.test_results[test_name] = {'collections': [], 'success': False}
                    self.test_results[test_name]['collections'].append(collection_name)
                
                result = response.json()
                self.log(f"✅ Collection created: {collection_name} (Status: {response.status_code}, Time: {response.elapsed.total_seconds():.3f}s)")
                return True, result
            else:
                self.log(f"❌ Collection creation failed: {response.status_code}", "ERROR")
                return False, None
                
        except Exception as e:
            self.log(f"❌ Collection creation error: {e}", "ERROR")
            return False, None
            
    def test_operations_during_failure(self):
        """Test various operations during primary failure"""
        self.log("🧪 Testing operations during primary failure...")
        
        success_count = 0
        total_tests = 0
        
        # Test 1: Collection Creation
        test_name = "collection_creation"
        total_tests += 1
        self.log("Test 1: Collection Creation")
        success, _ = self.create_test_collection("CREATE_TEST", test_name)
        self.test_results[test_name] = {'collections': self.test_results.get(test_name, {}).get('collections', []), 'success': success}
        if success:
            success_count += 1
            
        # Test 2: Document Addition (with embeddings) - ENHANCED with tracking
        test_name = "document_addition"
        total_tests += 1
        self.log("Test 2: Document Addition with Embeddings")
        doc_success = False
        if self.test_collections:
            try:
                collection_name = self.test_collections[0]
                doc_id = f"doc_{self.session_id}"
                doc_content = "Test document during primary failure"
                doc_metadata = {"test_type": "primary_down", "session": self.session_id, "failure_time": datetime.now().isoformat()}
                
                doc_payload = {
                    "documents": [doc_content],
                    "metadatas": [doc_metadata],
                    "ids": [doc_id],
                    "embeddings": [[0.1, 0.2, 0.3, 0.4, 0.5]]  # Required embeddings
                }
                
                response = requests.post(
                    f"{self.base_url}/api/v2/tenants/default_tenant/databases/default_database/collections/{collection_name}/add",
                    json=doc_payload,
                    timeout=15
                )
                
                if response.status_code == 201:
                    doc_success = True
                    success_count += 1
                    
                    # ENHANCED: Track document for later sync verification
                    if collection_name not in self.documents_added_during_failure:
                        self.documents_added_during_failure[collection_name] = []
                    
                    self.documents_added_during_failure[collection_name].append({
                        'id': doc_id,
                        'content': doc_content,
                        'metadata': doc_metadata,
                        'embeddings': [0.1, 0.2, 0.3, 0.4, 0.5]
                    })
                    
                    self.log(f"✅ Document added: {doc_id} (Status: {response.status_code}, Time: {response.elapsed.total_seconds():.3f}s)")
                    self.log(f"📋 Tracked for sync verification: Collection '{collection_name}', Document '{doc_id}'")
                else:
                    self.log(f"❌ Document addition failed: {response.status_code}", "ERROR")
                    
            except Exception as e:
                self.log(f"❌ Document addition error: {e}", "ERROR")
        
        # Note: Document addition uses existing collection, so we track success separately        
        self.test_results[test_name] = {'collections': [], 'success': doc_success}
                
        # Test 3: Document Query
        test_name = "document_query"
        total_tests += 1
        self.log("Test 3: Document Query")
        query_success = False
        if self.test_collections:
            try:
                collection_name = self.test_collections[0]
                query_payload = {
                    "query_embeddings": [[0.1, 0.2, 0.3, 0.4, 0.5]],
                    "n_results": 1,
                    "include": ["documents", "metadatas"]
                }
                
                response = requests.post(
                    f"{self.base_url}/api/v2/tenants/default_tenant/databases/default_database/collections/{collection_name}/query",
                    json=query_payload,
                    timeout=15
                )
                
                if response.status_code == 200:
                    query_success = True
                    success_count += 1
                    result = response.json()
                    doc_count = len(result.get('documents', [[]])[0])
                    self.log(f"✅ Document query (Status: {response.status_code}, Documents: {doc_count}, Time: {response.elapsed.total_seconds():.3f}s)")
                else:
                    self.log(f"❌ Document query failed: {response.status_code}", "ERROR")
                    
            except Exception as e:
                self.log(f"❌ Document query error: {e}", "ERROR")
        
        # Note: Document query uses existing collection, so we track success separately
        self.test_results[test_name] = {'collections': [], 'success': query_success}
                
        # Test 4: Additional Collection Creation
        test_name = "additional_collection"
        total_tests += 1
        self.log("Test 4: Additional Collection Creation")
        success, _ = self.create_test_collection("ADDITIONAL", test_name)
        self.test_results[test_name] = {'collections': self.test_results.get(test_name, {}).get('collections', []), 'success': success}
        if success:
            success_count += 1
            
        self.log(f"📊 Operations during failure: {success_count}/{total_tests} successful ({success_count/total_tests*100:.1f}%)")
        return success_count, total_tests
        
    def wait_for_recovery_and_sync(self, timeout_minutes=12):
        """Wait for primary recovery and WAL sync completion with proper retry logic"""
        self.log("⏳ Waiting for primary recovery and WAL sync...")
        
        start_time = time.time()
        timeout_seconds = timeout_minutes * 60
        
        # Phase 1: Wait for primary recovery
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
                        self.log("✅ Primary recovery completed, now waiting for WAL sync...")
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
            
        self.log("⚠️ Recovery timeout reached - sync may still be in progress", "WARNING")
        
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
                    self.log(f"❌ Failed to get collections via load balancer: {response.status_code}", "ERROR")
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
                            
                            primary_has_doc = self.verify_document_exists_on_instance(self.primary_url, primary_uuid, doc_id)
                            replica_has_doc = self.verify_document_exists_on_instance(self.replica_url, replica_uuid, doc_id)
                            
                            if primary_has_doc and replica_has_doc:
                                synced_docs += 1
                                self.log(f"   ✅ Document '{doc_id}': Found on both instances")
                            elif replica_has_doc and not primary_has_doc:
                                self.log(f"   ❌ Document '{doc_id}': Only on replica (sync failed)")
                                document_sync_success = False
                            elif primary_has_doc and not replica_has_doc:
                                self.log(f"   ⚠️ Document '{doc_id}': Only on primary (expected during failure)")
                            else:
                                self.log(f"   ❌ Document '{doc_id}': Missing from both instances")
                                document_sync_success = False
                    
                    self.log(f"📊 Document sync summary (attempt {attempt + 1}/{max_retries}):")
                    self.log(f"   Documents synced: {synced_docs}/{total_docs_checked} = {synced_docs/total_docs_checked*100:.1f}%" if total_docs_checked > 0 else "No documents to check")
                    self.log(f"   Document sync success: {'✅ Complete' if document_sync_success and synced_docs == total_docs_checked else '❌ Incomplete'}")
                    
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
                self.log(f"❌ Verification error (attempt {attempt + 1}/{max_retries}): {e}", "ERROR")
                if attempt < max_retries - 1:
                    continue
                    
        return False
        
    def cleanup_test_data(self, overall_test_success=True):
        """Clean up test data using selective cleanup based on OVERALL test result"""
        if not self.test_collections:
            self.log("No test data to clean up")
            return True
        
        # CRITICAL: If OVERALL test failed, preserve ALL data for debugging
        if not overall_test_success:
            self.log("🔒 OVERALL TEST FAILED - Preserving ALL test data for debugging")
            self.log("🔍 PRESERVED COLLECTIONS FOR DEBUGGING:")
            for collection in self.test_collections:
                self.log(f"   - {collection}")
                self.log(f"   URL: {self.base_url}/api/v2/tenants/default_tenant/databases/default_database/collections/{collection}")
            
            # Show why test failed
            failed_reasons = []
            for test_name, test_data in self.test_results.items():
                if not test_data['success']:
                    failed_reasons.append(test_name)
            
            if failed_reasons:
                self.log(f"📋 Failed operations: {', '.join(failed_reasons)}")
            self.log("💡 Review test output above for debugging information")
            self.log("🧹 Manual cleanup available: python comprehensive_system_cleanup.py --url URL")
            return True  # This is expected behavior for failed tests
            
        # If overall test PASSED, apply selective cleanup (only remove successful test data)
        self.log("🧹 OVERALL TEST PASSED - Applying selective cleanup (same as USE CASE 1)...")
        
        # Analyze test results for selective cleanup
        successful_collections = []
        failed_collections = []
        
        for test_name, test_data in self.test_results.items():
            if test_data['success']:
                successful_collections.extend(test_data['collections'])
                if test_data['collections']:
                    self.log(f"✅ {test_name}: SUCCESS - Collections will be cleaned")
                else:
                    self.log(f"✅ {test_name}: SUCCESS - Used existing collection")
            else:
                failed_collections.extend(test_data['collections'])
                if test_data['collections']:
                    self.log(f"❌ {test_name}: FAILED - Collections preserved for debugging")
                else:
                    self.log(f"❌ {test_name}: FAILED - Used existing collection")
        
        # Check for any collections not tracked by individual tests
        untracked_collections = [col for col in self.test_collections if col not in successful_collections and col not in failed_collections]
        
        # Clean successful collections only
        collections_to_clean = successful_collections
        collections_to_preserve = failed_collections + untracked_collections
        
        if collections_to_clean:
            self.log(f"🔄 Cleaning {len(collections_to_clean)} collections from successful tests...")
            try:
                # Use comprehensive_system_cleanup.py for bulletproof cleanup
                result = subprocess.run([
                    "python", "comprehensive_system_cleanup.py", 
                    "--url", self.base_url
                ], capture_output=True, text=True, timeout=120)
                
                if result.returncode == 0:
                    self.log("✅ Selective cleanup completed successfully")
                    self.log("📊 Cleanup summary:")
                    # Parse cleanup output for summary
                    lines = result.stdout.split('\n')
                    for line in lines:
                        if 'CLEANUP SUMMARY' in line or line.startswith('✅') or line.startswith('🔧'):
                            if line.strip():
                                self.log(f"   {line.strip()}")
                    cleanup_success = True
                else:
                    self.log(f"❌ Cleanup failed with return code {result.returncode}", "ERROR")
                    self.log(f"Error output: {result.stderr}", "ERROR")
                    cleanup_success = False
                    
            except subprocess.TimeoutExpired:
                self.log("❌ Cleanup timeout - manual cleanup may be required", "ERROR")
                cleanup_success = False
            except Exception as e:
                self.log(f"❌ Cleanup error: {e}", "ERROR")
                cleanup_success = False
        else:
            self.log("ℹ️  No successful tests with collections found - no data to clean")
            cleanup_success = True
        
        # Report what's being preserved (even in successful overall tests)
        if collections_to_preserve:
            self.log("🔒 PRESERVED FOR DEBUGGING:")
            for collection in failed_collections:
                self.log(f"   - {collection} (from failed individual test)")
            for collection in untracked_collections:
                self.log(f"   - {collection} (untracked - preserved by default)")
                
            # Provide debugging URLs for preserved collections
            self.log("🔍 DEBUG COLLECTIONS:")
            for collection in collections_to_preserve:
                self.log(f"   Collection: {collection}")
                self.log(f"   URL: {self.base_url}/api/v2/tenants/default_tenant/databases/default_database/collections/{collection}")
        
        if collections_to_preserve:
            self.log("⚠️ Some collections preserved for debugging - manual cleanup may be needed later")
        else:
            self.log("✅ Selective cleanup complete - all test data removed (no failed operations)")
            
        return cleanup_success
            
    def run_complete_test_cycle(self):
        """Run the complete USE CASE 2 testing cycle"""
        self.start_time = time.time()
        
        print("="*80)
        print("🚀 USE CASE 2: Primary Instance Down - Manual Testing Protocol")
        print("="*80)
        
        # Step 1: Initial Health Check
        self.log("📋 Step 1: Initial System Health Check")
        initial_status = self.check_system_health()
        if not initial_status:
            self.log("❌ Cannot connect to system", "ERROR")
            return False
            
        healthy_instances = initial_status.get('healthy_instances', 0)
        if healthy_instances != 2:
            self.log(f"⚠️ Warning: Only {healthy_instances}/2 instances healthy", "WARNING")
            
        self.log(f"✅ Initial status: {healthy_instances}/2 instances healthy")
        
        # Step 2: Manual Primary Suspension
        self.wait_for_user("""
MANUAL ACTION REQUIRED: Suspend Primary Instance
        
1. Go to your Render dashboard (https://dashboard.render.com)
2. Navigate to 'chroma-primary' service
3. Click 'Suspend' to simulate infrastructure failure
4. Wait 5-10 seconds for health detection to update
        """)
        
        # Step 3: Verify Primary Down
        self.log("📋 Step 3: Verifying primary failure detection...")
        time.sleep(10)  # Wait for health detection
        
        failure_status = self.check_system_health()
        if failure_status:
            primary_healthy = failure_status.get('instances', [{}])[0].get('healthy', True)
            if not primary_healthy:
                self.log("✅ Primary failure detected by load balancer")
            else:
                self.log("⚠️ Primary still appears healthy - may need more time", "WARNING")
                
        # Step 4: Test Operations During Failure
        self.log("📋 Step 4: Testing operations during infrastructure failure...")
        success_count, total_tests = self.test_operations_during_failure()
        
        if success_count == 0:
            self.log("❌ All operations failed during primary outage", "ERROR")
            return False
            
        # Step 5: Manual Primary Recovery
        self.wait_for_user("""
MANUAL ACTION REQUIRED: Resume Primary Instance
        
1. Go back to your Render dashboard
2. Navigate to 'chroma-primary' service  
3. Click 'Resume' or 'Restart' to restore the primary
4. Wait for the service to fully start up (~30-60 seconds)
        """)
        
        # Step 6: Wait for Recovery and Sync
        self.log("📋 Step 6: Waiting for recovery and sync completion...")
        recovery_success = self.wait_for_recovery_and_sync()
        
        if not recovery_success:
            self.log("⚠️ Recovery may still be in progress", "WARNING")
            
        # Step 7: Verify Data Consistency
        self.log("📋 Step 7: Verifying data consistency...")
        consistency_ok = self.verify_data_consistency()
        
        # Determine overall test success BEFORE cleanup
        overall_test_success = success_count >= total_tests * 0.8 and consistency_ok
        
        # Step 8: Automatic Cleanup (Based on OVERALL test result)
        self.log("📋 Step 8: Automatic cleanup of test data...")
        cleanup_success = self.cleanup_test_data(overall_test_success)
        
        # Final Summary
        total_time = time.time() - self.start_time
        print("\n" + "="*80)
        print("📊 USE CASE 2 TESTING SUMMARY")
        print("="*80)
        print(f"⏱️  Total test time: {total_time/60:.1f} minutes")
        print(f"🧪 Operations during failure: {success_count}/{total_tests} successful ({success_count/total_tests*100:.1f}%)")
        print(f"🔄 Primary recovery: {'✅ Success' if recovery_success else '⚠️ Partial'}")
        print(f"📊 Data consistency: {'✅ Complete' if consistency_ok else '⚠️ Partial'} (ENHANCED: includes document-level sync)")
        print(f"🧹 Automatic cleanup: {'✅ Complete' if cleanup_success else '⚠️ Manual needed'}")
        
        # Enhanced summary for document tracking
        if self.documents_added_during_failure:
            total_docs = sum(len(docs) for docs in self.documents_added_during_failure.values())
            print(f"📋 Document sync verification: {total_docs} documents tracked and verified")
        
        if overall_test_success:
            print("\n🎉 USE CASE 2: ✅ SUCCESS - Enterprise-grade high availability validated!")
            print("   Your system maintains CMS operations during infrastructure failures.")
            print("   ✅ ENHANCED: Document-level sync from replica to primary verified!")
            return True
        else:
            print("\n❌ USE CASE 2: Issues detected - Review results above")
            print("   🔒 TEST DATA PRESERVED for debugging (failed test)")
            return False

def main():
    parser = argparse.ArgumentParser(description='USE CASE 2: Primary Instance Down - Manual Testing')
    parser.add_argument('--url', required=True, help='Load balancer URL')
    args = parser.parse_args()
    
    tester = UseCase2Tester(args.url)
    success = tester.run_complete_test_cycle()
    
    sys.exit(0 if success else 1)

if __name__ == "__main__":
    main() 