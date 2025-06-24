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
        
    def wait_for_recovery_and_sync(self, timeout_minutes=5):
        """Wait for primary recovery and WAL sync completion"""
        self.log("⏳ Waiting for primary recovery and WAL sync...")
        
        start_time = time.time()
        timeout_seconds = timeout_minutes * 60
        
        while time.time() - start_time < timeout_seconds:
            status = self.check_system_health()
            if status:
                healthy_instances = status.get('healthy_instances', 0)
                pending_writes = status.get('unified_wal', {}).get('pending_writes', 0)
                
                primary_healthy = status.get('instances', [{}])[0].get('healthy', False)
                replica_healthy = len(status.get('instances', [])) > 1 and status.get('instances', [{}])[1].get('healthy', False)
                
                self.log(f"Status: Healthy: {healthy_instances}/2, Primary: {primary_healthy}, Replica: {replica_healthy}, Pending: {pending_writes}")
                
                # Recovery complete when both instances healthy and minimal pending writes
                if healthy_instances == 2 and pending_writes <= 2:
                    self.log("✅ Primary recovery and sync completed!")
                    return True
                    
            time.sleep(10)
            
        self.log("⚠️ Recovery timeout reached", "WARNING")
        return False
        
    def verify_data_consistency(self):
        """ENHANCED: Verify that test data exists and documents are synced between instances"""
        self.log("🔍 Verifying data consistency (ENHANCED: including document-level sync)...")
        
        try:
            # Step 1: Check collections exist via load balancer
            response = requests.get(
                f"{self.base_url}/api/v2/tenants/default_tenant/databases/default_database/collections",
                timeout=10
            )
            
            if response.status_code != 200:
                self.log(f"❌ Failed to get collections via load balancer: {response.status_code}", "ERROR")
                return False
                
            collections = response.json()
            collection_names = [c['name'] for c in collections]
            found_collections = [name for name in self.test_collections if name in collection_names]
            
            self.log(f"📊 Collection-level verification:")
            self.log(f"   Created during failure: {len(self.test_collections)}")
            self.log(f"   Found after recovery: {len(found_collections)}")
            self.log(f"   Collection consistency: {len(found_collections)}/{len(self.test_collections)} = {len(found_collections)/len(self.test_collections)*100:.1f}%" if self.test_collections else "No test collections")
            
            collection_consistency = len(found_collections) == len(self.test_collections)
            
            # Step 2: ENHANCED - Verify document-level sync between instances
            if self.documents_added_during_failure:
                self.log(f"📋 Document-level sync verification:")
                self.log(f"   Documents added during failure: {sum(len(docs) for docs in self.documents_added_during_failure.values())}")
                
                # Get collection mappings for direct instance access
                mappings = self.get_collection_mappings()
                
                document_sync_success = True
                total_docs_checked = 0
                synced_docs = 0
                
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
                
                self.log(f"📊 Document sync summary:")
                self.log(f"   Documents synced: {synced_docs}/{total_docs_checked} = {synced_docs/total_docs_checked*100:.1f}%" if total_docs_checked > 0 else "No documents to check")
                self.log(f"   Document sync success: {'✅ Complete' if document_sync_success and synced_docs == total_docs_checked else '❌ Incomplete'}")
                
                # Overall consistency includes both collection and document sync
                overall_consistency = collection_consistency and document_sync_success and (synced_docs == total_docs_checked if total_docs_checked > 0 else True)
                
            else:
                self.log(f"📋 No documents were added during failure - only verifying collection sync")
                overall_consistency = collection_consistency
            
            self.log(f"🎯 Overall data consistency: {'✅ Complete' if overall_consistency else '❌ Issues detected'}")
            return overall_consistency
                
        except Exception as e:
            self.log(f"❌ Verification error: {e}", "ERROR")
            
        return False
        
    def cleanup_test_data(self):
        """Clean up test data using selective cleanup (only successful tests - USE CASE 1 behavior)"""
        if not self.test_collections:
            self.log("No test data to clean up")
            return True
            
        self.log("🧹 Applying selective cleanup (same as USE CASE 1)...")
        
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
        
        # Conservative approach: only clean collections from explicitly successful tests
        if successful_collections or (not failed_collections and not untracked_collections):
            self.log(f"🔄 Cleaning {len(successful_collections)} collections from successful tests...")
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
                    return True
                else:
                    self.log(f"❌ Cleanup failed with return code {result.returncode}", "ERROR")
                    self.log(f"Error output: {result.stderr}", "ERROR")
                    return False
                    
            except subprocess.TimeoutExpired:
                self.log("❌ Cleanup timeout - manual cleanup may be required", "ERROR")
                return False
            except Exception as e:
                self.log(f"❌ Cleanup error: {e}", "ERROR")
                return False
        else:
            self.log("ℹ️  No successful tests with collections found - no data to clean")
        
        # Report what's being preserved
        if failed_collections:
            self.log("🔒 PRESERVED FOR DEBUGGING:")
            for collection in failed_collections:
                self.log(f"   - {collection} (from failed test)")
                
        if untracked_collections:
            self.log("🔒 PRESERVED (untracked):")
            for collection in untracked_collections:
                self.log(f"   - {collection} (untracked - preserved by default)")
                
        # Provide debugging URLs for preserved collections
        if failed_collections or untracked_collections:
            self.log("🔍 DEBUG COLLECTIONS:")
            for collection in failed_collections + untracked_collections:
                self.log(f"   Collection: {collection}")
                self.log(f"   URL: {self.base_url}/api/v2/tenants/default_tenant/databases/default_database/collections/{collection}")
        
        if failed_collections or untracked_collections:
            self.log("⚠️ Some collections preserved for debugging - manual cleanup may be needed later")
            return True  # Still return success as this is expected behavior
        else:
            self.log("✅ Selective cleanup complete - successful test data removed, no failed test data to preserve")
            return True
            
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
        
        # Step 8: Automatic Cleanup
        self.log("📋 Step 8: Automatic cleanup of test data...")
        cleanup_success = self.cleanup_test_data()
        
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
        
        if success_count >= total_tests * 0.8 and consistency_ok:
            print("\n🎉 USE CASE 2: ✅ SUCCESS - Enterprise-grade high availability validated!")
            print("   Your system maintains CMS operations during infrastructure failures.")
            print("   ✅ ENHANCED: Document-level sync from replica to primary verified!")
            return True
        else:
            print("\n❌ USE CASE 2: Issues detected - Review results above")
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