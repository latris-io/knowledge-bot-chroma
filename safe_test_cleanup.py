#!/usr/bin/env python3

"""
SAFE TEST DATA CLEANUP with BULLETPROOF GLOBAL COLLECTION PROTECTION
Multiple layers of protection ensure the 'global' collection is NEVER deleted
"""

import requests
import psycopg2
import os
from urllib.parse import urlparse
import time

class SafeTestDataCleaner:
    def __init__(self):
        self.base_url = 'https://chroma-load-balancer.onrender.com'
        self.primary_url = 'https://chroma-primary.onrender.com'
        self.replica_url = 'https://chroma-replica.onrender.com'
        
        # CRITICAL: Production collections that must NEVER be deleted
        # Multiple layers of protection for these collections
        self.PROTECTED_COLLECTIONS = [
            'global',
            'Global',
            'GLOBAL',
            'production',
            'prod',
            'main'
        ]
        
        # Test patterns to identify collections that CAN be safely deleted
        self.SAFE_TO_DELETE_PATTERNS = [
            'DELETE_TEST_',
            'AUTOTEST_',
            'TEST_',
            'PATCH_TEST_',
            'test_collection_',
            'failover_test_',
            'clean_query_test_',
            'debug_',
            'temp_',
            'demo_',
            'example_'
        ]
        
        # Additional safety: Only delete collections that have specific test prefixes
        self.REQUIRED_TEST_PREFIX = ['DELETE_TEST_', 'AUTOTEST_', 'TEST_', 'PATCH_TEST_', 'test_']
    
    def is_protected_collection(self, collection_name):
        """
        LAYER 1 PROTECTION: Check if collection is protected
        Returns True if collection should NEVER be deleted
        """
        if not collection_name:
            return True  # Protect empty/null names
        
        # Case-insensitive check for protected collections
        name_lower = collection_name.lower()
        for protected in self.PROTECTED_COLLECTIONS:
            if protected.lower() in name_lower or name_lower == protected.lower():
                return True
        
        return False
    
    def is_safe_test_collection(self, collection_name):
        """
        LAYER 2 PROTECTION: Only allow deletion of clearly identified test collections
        Returns True only if collection is definitely a test collection
        """
        if not collection_name:
            return False
        
        # First check: Must NOT be protected
        if self.is_protected_collection(collection_name):
            return False
        
        # Second check: Must have a clear test pattern
        has_test_pattern = any(pattern in collection_name for pattern in self.SAFE_TO_DELETE_PATTERNS)
        
        # Third check: Must have required test prefix (extra safety)
        has_test_prefix = any(collection_name.startswith(prefix) for prefix in self.REQUIRED_TEST_PREFIX)
        
        # Only return True if BOTH conditions are met
        return has_test_pattern and has_test_prefix
    
    def validate_deletion_safety(self, collections_to_delete):
        """
        LAYER 3 PROTECTION: Final validation before any deletion
        """
        print("🛡️ PERFORMING SAFETY VALIDATION...")
        
        # Check for any protected collections in deletion list
        protected_found = []
        for collection_name in collections_to_delete:
            if self.is_protected_collection(collection_name):
                protected_found.append(collection_name)
        
        if protected_found:
            print(f"🚨 CRITICAL SAFETY VIOLATION DETECTED!")
            print(f"❌ The following PROTECTED collections were marked for deletion:")
            for name in protected_found:
                print(f"   🔒 {name}")
            print(f"❌ ABORTING ALL OPERATIONS TO PROTECT PRODUCTION DATA")
            return False
        
        # Verify all collections to delete are actually test collections
        invalid_deletions = []
        for collection_name in collections_to_delete:
            if not self.is_safe_test_collection(collection_name):
                invalid_deletions.append(collection_name)
        
        if invalid_deletions:
            print(f"⚠️ SAFETY WARNING: Some collections don't match safe test patterns:")
            for name in invalid_deletions:
                print(f"   ⚠️ {name}")
            
            confirm = input("Are you sure these are test collections? (yes/no): ").lower().strip()
            if confirm not in ['yes', 'y']:
                print("❌ ABORTING for safety")
                return False
        
        print(f"✅ Safety validation passed - {len(collections_to_delete)} collections cleared for deletion")
        return True
    
    def get_db_connection(self):
        """Get PostgreSQL database connection with error handling"""
        try:
            result = urlparse(os.environ.get('DATABASE_URL', ''))
            if result.scheme:
                return psycopg2.connect(
                    database=result.path[1:], user=result.username, 
                    password=result.password, host=result.hostname, port=result.port
                )
        except Exception as e:
            print(f"⚠️ Database connection failed: {e}")
        return None
    
    def get_collections(self, instance_url, name):
        """Get collections from ChromaDB instance"""
        try:
            response = requests.get(f'{instance_url}/api/v2/tenants/default_tenant/databases/default_database/collections', timeout=30)
            if response.status_code == 200:
                return response.json()
        except Exception as e:
            print(f"❌ Failed to get collections from {name}: {e}")
        return []
    
    def delete_collection_safely(self, instance_url, instance_name, collection):
        """Delete collection with safety checks"""
        collection_name = collection.get('name', '')
        collection_id = collection.get('id', '')
        
        # SAFETY CHECK: Never delete protected collections
        if self.is_protected_collection(collection_name):
            print(f"🔒 PROTECTION ACTIVATED: Refusing to delete protected collection '{collection_name}'")
            return False, "protected_collection"
        
        try:
            # Try delete by name
            response = requests.delete(f'{instance_url}/api/v2/tenants/default_tenant/databases/default_database/collections/{collection_name}', timeout=30)
            if response.status_code in [200, 204, 404]:
                return True, "deleted_by_name"
            
            # Try delete by ID
            response = requests.delete(f'{instance_url}/api/v2/tenants/default_tenant/databases/default_database/collections/{collection_id}', timeout=30)
            if response.status_code in [200, 204, 404]:
                return True, "deleted_by_id"
            
            return False, f"failed_status_{response.status_code}"
        except Exception as e:
            return False, f"exception_{str(e)}"
    
    def cleanup_chromadb_safely(self):
        """Safely clean ChromaDB instances with protection"""
        print("🧹 SAFELY CLEANING CHROMADB INSTANCES")
        print("🛡️ Global collection protection is ACTIVE")
        print("=" * 60)
        
        results = {'primary': {'deleted': 0, 'protected': 0, 'total': 0}, 
                  'replica': {'deleted': 0, 'protected': 0, 'total': 0}}
        
        # Primary instance
        print("\n🔹 Cleaning PRIMARY instance...")
        primary_collections = self.get_collections(self.primary_url, "Primary")
        results['primary']['total'] = len(primary_collections)
        
        # Identify collections to delete
        primary_to_delete = []
        for collection in primary_collections:
            name = collection.get('name', '')
            if self.is_protected_collection(name):
                results['primary']['protected'] += 1
                print(f"    🔒 PROTECTED: {name}")
            elif self.is_safe_test_collection(name):
                primary_to_delete.append(collection)
            else:
                print(f"    ⚠️ UNKNOWN: {name} (skipping for safety)")
        
        # Safety validation
        if not self.validate_deletion_safety([c.get('name', '') for c in primary_to_delete]):
            print("❌ Primary cleanup aborted for safety")
            return results
        
        # Delete safe collections
        for collection in primary_to_delete:
            name = collection.get('name', '')
            success, method = self.delete_collection_safely(self.primary_url, "Primary", collection)
            if success:
                results['primary']['deleted'] += 1
                print(f"    ✅ Deleted: {name}")
            else:
                print(f"    ❌ Failed: {name} - {method}")
        
        # Replica instance
        print("\n🔹 Cleaning REPLICA instance...")
        replica_collections = self.get_collections(self.replica_url, "Replica")
        results['replica']['total'] = len(replica_collections)
        
        # Identify collections to delete
        replica_to_delete = []
        for collection in replica_collections:
            name = collection.get('name', '')
            if self.is_protected_collection(name):
                results['replica']['protected'] += 1
                print(f"    🔒 PROTECTED: {name}")
            elif self.is_safe_test_collection(name):
                replica_to_delete.append(collection)
            else:
                print(f"    ⚠️ UNKNOWN: {name} (skipping for safety)")
        
        # Safety validation
        if not self.validate_deletion_safety([c.get('name', '') for c in replica_to_delete]):
            print("❌ Replica cleanup aborted for safety")
            return results
        
        # Delete safe collections
        for collection in replica_to_delete:
            name = collection.get('name', '')
            success, method = self.delete_collection_safely(self.replica_url, "Replica", collection)
            if success:
                results['replica']['deleted'] += 1
                print(f"    ✅ Deleted: {name}")
            else:
                print(f"    ❌ Failed: {name} - {method}")
        
        return results
    
    def cleanup_postgresql_safely(self):
        """Safely clean PostgreSQL mappings with protection"""
        print("\n🗄️ SAFELY CLEANING POSTGRESQL MAPPINGS")
        print("🛡️ Global collection protection is ACTIVE")
        print("=" * 60)
        
        conn = self.get_db_connection()
        if not conn:
            print("❌ Cannot connect to PostgreSQL - skipping database cleanup")
            return {'deleted': 0, 'protected': 0}
        
        try:
            with conn.cursor() as cur:
                # Get all collection mappings
                cur.execute("SELECT collection_name FROM collection_id_mapping")
                mappings = cur.fetchall()
                
                print(f"📊 Found {len(mappings)} collection mappings in database")
                
                # Categorize mappings
                to_delete = []
                protected = []
                unknown = []
                
                for (name,) in mappings:
                    if self.is_protected_collection(name):
                        protected.append(name)
                    elif self.is_safe_test_collection(name):
                        to_delete.append(name)
                    else:
                        unknown.append(name)
                
                print(f"📋 Mapping analysis:")
                print(f"   🔒 Protected: {len(protected)}")
                print(f"   🗑️ Safe to delete: {len(to_delete)}")
                print(f"   ⚠️ Unknown: {len(unknown)}")
                
                # Show protected collections
                if protected:
                    print(f"\n🔒 PROTECTED collections (will NOT be deleted):")
                    for name in protected:
                        print(f"     🛡️ {name}")
                
                # Safety validation
                if not self.validate_deletion_safety(to_delete):
                    print("❌ PostgreSQL cleanup aborted for safety")
                    return {'deleted': 0, 'protected': len(protected)}
                
                # Delete safe mappings
                deleted_count = 0
                for name in to_delete:
                    # Extra safety check before each deletion
                    if self.is_protected_collection(name):
                        print(f"🚨 SAFETY BLOCK: Refusing to delete {name}")
                        continue
                    
                    cur.execute("DELETE FROM collection_id_mapping WHERE collection_name = %s", (name,))
                    if cur.rowcount > 0:
                        deleted_count += 1
                        print(f"    ✅ Deleted mapping: {name}")
                
                # Clean WAL entries (with protection)
                wal_deleted = 0
                for pattern in self.SAFE_TO_DELETE_PATTERNS:
                    # Make sure pattern doesn't match 'global'
                    if 'global' not in pattern.lower():
                        cur.execute("DELETE FROM unified_wal_writes WHERE path LIKE %s", (f'%{pattern}%',))
                        pattern_deleted = cur.rowcount
                        wal_deleted += pattern_deleted
                        if pattern_deleted > 0:
                            print(f"    ✅ Deleted {pattern_deleted} WAL entries for {pattern}")
                
                conn.commit()
                print(f"\n📊 PostgreSQL cleanup: {deleted_count} mappings deleted, {wal_deleted} WAL entries deleted")
                
                return {'deleted': deleted_count, 'protected': len(protected), 'wal_deleted': wal_deleted}
                
        except Exception as e:
            print(f"❌ PostgreSQL cleanup failed: {e}")
            return {'deleted': 0, 'protected': 0}
        finally:
            conn.close()
    
    def verify_global_protection(self):
        """Verify that global collection is still intact after cleanup"""
        print("\n🔍 VERIFYING GLOBAL COLLECTION PROTECTION")
        print("=" * 60)
        
        # Check ChromaDB instances
        global_on_primary = False
        global_on_replica = False
        
        primary_collections = self.get_collections(self.primary_url, "Primary")
        for collection in primary_collections:
            if collection.get('name', '').lower() == 'global':
                global_on_primary = True
                print(f"✅ Global collection found on PRIMARY: {collection.get('id', 'no-id')}")
                break
        
        replica_collections = self.get_collections(self.replica_url, "Replica")
        for collection in replica_collections:
            if collection.get('name', '').lower() == 'global':
                global_on_replica = True
                print(f"✅ Global collection found on REPLICA: {collection.get('id', 'no-id')}")
                break
        
        # Check PostgreSQL mapping
        global_mapping_exists = False
        conn = self.get_db_connection()
        if conn:
            try:
                with conn.cursor() as cur:
                    cur.execute("SELECT COUNT(*) FROM collection_id_mapping WHERE LOWER(collection_name) = 'global'")
                    global_count = cur.fetchone()[0]
                    if global_count > 0:
                        global_mapping_exists = True
                        print(f"✅ Global mapping found in PostgreSQL")
                    else:
                        print(f"⚠️ Global mapping NOT found in PostgreSQL")
            except Exception as e:
                print(f"❌ Could not verify PostgreSQL mapping: {e}")
            finally:
                conn.close()
        
        # Overall verification
        protection_successful = global_on_primary and global_on_replica and global_mapping_exists
        
        if protection_successful:
            print(f"\n🎉 GLOBAL COLLECTION PROTECTION VERIFIED!")
            print("✅ Global collection intact on both ChromaDB instances")
            print("✅ Global mapping preserved in PostgreSQL")
            print("✅ Production data is safe!")
        else:
            print(f"\n🚨 GLOBAL COLLECTION PROTECTION VERIFICATION FAILED!")
            if not global_on_primary:
                print("❌ Global collection missing from PRIMARY")
            if not global_on_replica:
                print("❌ Global collection missing from REPLICA")
            if not global_mapping_exists:
                print("❌ Global mapping missing from PostgreSQL")
            print("🚨 IMMEDIATE ACTION REQUIRED!")
        
        return protection_successful

def main():
    print("🛡️ SAFE TEST DATA CLEANUP")
    print("=" * 80)
    print("🔒 BULLETPROOF PROTECTION FOR GLOBAL COLLECTION")
    print("=" * 80)
    print("This cleanup has multiple layers of protection to ensure the")
    print("'global' collection and its mapping are NEVER deleted.")
    print()
    print("Protected collections: global, Global, GLOBAL, production, prod, main")
    print("Safe to delete: Collections with test prefixes only")
    
    cleaner = SafeTestDataCleaner()
    
    confirm = input("\nProceed with SAFE cleanup? (yes/no): ").lower().strip()
    if confirm not in ['yes', 'y']:
        print("❌ Cancelled by user")
        return
    
    # Perform safe cleanup
    print(f"\n🛡️ INITIATING SAFE CLEANUP WITH GLOBAL PROTECTION...")
    
    chromadb_results = cleaner.cleanup_chromadb_safely()
    postgresql_results = cleaner.cleanup_postgresql_safely()
    
    # Verify protection worked
    protection_verified = cleaner.verify_global_protection()
    
    # Summary
    print("\n" + "=" * 80)
    print("📊 SAFE CLEANUP SUMMARY")
    print("=" * 80)
    print(f"✅ Primary: {chromadb_results['primary']['deleted']} deleted, {chromadb_results['primary']['protected']} protected")
    print(f"✅ Replica: {chromadb_results['replica']['deleted']} deleted, {chromadb_results['replica']['protected']} protected")
    print(f"✅ PostgreSQL: {postgresql_results['deleted']} mappings deleted, {postgresql_results['protected']} protected")
    print(f"✅ Global protection: {'VERIFIED' if protection_verified else 'FAILED'}")
    
    if protection_verified:
        print(f"\n🎉 SAFE CLEANUP COMPLETED SUCCESSFULLY!")
        print("🛡️ Global collection and mapping are SAFE")
        print("🧹 Test data has been cleaned")
        print("✅ Production data is protected")
    else:
        print(f"\n🚨 CLEANUP COMPLETED BUT PROTECTION VERIFICATION FAILED!")
        print("IMMEDIATE MANUAL VERIFICATION REQUIRED!")

if __name__ == '__main__':
    main() 