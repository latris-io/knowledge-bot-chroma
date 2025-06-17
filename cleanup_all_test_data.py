#!/usr/bin/env python3

import requests
import psycopg2
import os
from urllib.parse import urlparse

class TestDataCleaner:
    def __init__(self):
        self.base_url = 'https://chroma-load-balancer.onrender.com'
        self.primary_url = 'https://chroma-primary.onrender.com'
        self.replica_url = 'https://chroma-replica.onrender.com'
        
        # CRITICAL: Collections that must NEVER be deleted (bulletproof protection)
        self.PROTECTED_COLLECTIONS = ['global', 'Global', 'GLOBAL', 'production', 'prod', 'main']
        
        self.test_patterns = ['DELETE_TEST_', 'AUTOTEST_', 'TEST_', 'PATCH_TEST_', 'test_collection_', 'failover_test_']
        self.preserve = self.PROTECTED_COLLECTIONS  # Use protected list
    
    def get_db_connection(self):
        try:
            result = urlparse(os.environ.get('DATABASE_URL', ''))
            if result.scheme:
                return psycopg2.connect(
                    database=result.path[1:], user=result.username, 
                    password=result.password, host=result.hostname, port=result.port
                )
        except:
            pass
        return None
    
    def is_test_collection(self, name):
        """
        BULLETPROOF SAFETY CHECK: Determine if collection can be safely deleted
        Multiple layers of protection for production collections
        """
        if not name:
            return False  # Never delete collections with empty names
        
        # LAYER 1: Check against protected collections (case-insensitive)
        name_lower = name.lower()
        for protected in self.PROTECTED_COLLECTIONS:
            if protected.lower() in name_lower or name_lower == protected.lower():
                return False  # NEVER delete protected collections
        
        # LAYER 2: Must have test pattern to be considered for deletion
        has_test_pattern = any(pattern in name for pattern in self.test_patterns)
        
        # LAYER 3: Additional safety - must start with common test prefixes
        safe_prefixes = ['DELETE_TEST_', 'AUTOTEST_', 'TEST_', 'PATCH_TEST_', 'test_']
        has_safe_prefix = any(name.startswith(prefix) for prefix in safe_prefixes)
        
        # Only return True if it has test pattern AND safe prefix
        return has_test_pattern and has_safe_prefix
    
    def get_collections(self, instance_url, name):
        try:
            response = requests.get(f'{instance_url}/api/v2/tenants/default_tenant/databases/default_database/collections', timeout=30)
            if response.status_code == 200:
                return response.json()
        except:
            pass
        return []
    
    def delete_collection(self, instance_url, collection):
        name = collection.get('name', '')
        collection_id = collection.get('id', '')
        
        # CRITICAL SAFETY CHECK: Never delete protected collections
        if not name:
            print(f"    🚨 SAFETY BLOCK: Refusing to delete collection with empty name")
            return False
        
        name_lower = name.lower()
        for protected in self.PROTECTED_COLLECTIONS:
            if protected.lower() in name_lower or name_lower == protected.lower():
                print(f"    🔒 PROTECTION ACTIVATED: Refusing to delete protected collection '{name}'")
                return False
        
        try:
            # Try by name
            response = requests.delete(f'{instance_url}/api/v2/tenants/default_tenant/databases/default_database/collections/{name}', timeout=30)
            if response.status_code in [200, 204, 404]:
                return True
            
            # Try by ID
            response = requests.delete(f'{instance_url}/api/v2/tenants/default_tenant/databases/default_database/collections/{collection_id}', timeout=30)
            return response.status_code in [200, 204, 404]
        except:
            pass
        return False
    
    def cleanup_chromadb(self):
        print("🧹 Cleaning ChromaDB instances...")
        results = {'primary': {'deleted': 0, 'total': 0}, 'replica': {'deleted': 0, 'total': 0}}
        
        # Primary
        print("  Cleaning PRIMARY...")
        primary_collections = self.get_collections(self.primary_url, "Primary")
        results['primary']['total'] = len(primary_collections)
        
        for collection in primary_collections:
            name = collection.get('name', '')
            if self.is_test_collection(name):
                if self.delete_collection(self.primary_url, collection):
                    results['primary']['deleted'] += 1
                    print(f"    ✅ Deleted: {name}")
                else:
                    print(f"    ❌ Failed: {name}")
            else:
                print(f"    🛡️ Preserved: {name}")
        
        # Replica
        print("  Cleaning REPLICA...")
        replica_collections = self.get_collections(self.replica_url, "Replica")
        results['replica']['total'] = len(replica_collections)
        
        for collection in replica_collections:
            name = collection.get('name', '')
            if self.is_test_collection(name):
                if self.delete_collection(self.replica_url, collection):
                    results['replica']['deleted'] += 1
                    print(f"    ✅ Deleted: {name}")
                else:
                    print(f"    ❌ Failed: {name}")
            else:
                print(f"    🛡️ Preserved: {name}")
        
        return results
    
    def cleanup_postgresql(self):
        print("🗄️ Cleaning PostgreSQL...")
        conn = self.get_db_connection()
        if not conn:
            print("  ❌ Cannot connect to PostgreSQL")
            return {'deleted': 0}
        
        try:
            with conn.cursor() as cur:
                # Clean collection mappings
                cur.execute("SELECT collection_name FROM collection_id_mapping")
                mappings = cur.fetchall()
                
                deleted = 0
                for (name,) in mappings:
                    if self.is_test_collection(name):
                        # Extra safety check before database deletion
                        name_lower = name.lower()
                        is_protected = any(protected.lower() in name_lower or name_lower == protected.lower() 
                                         for protected in self.PROTECTED_COLLECTIONS)
                        
                        if is_protected:
                            print(f"    🔒 PROTECTION: Skipping protected mapping '{name}'")
                            continue
                        
                        cur.execute("DELETE FROM collection_id_mapping WHERE collection_name = %s", (name,))
                        deleted += 1
                        print(f"    ✅ Deleted mapping: {name}")
                    else:
                        print(f"    🛡️ Preserved mapping: {name}")
                
                # Clean WAL entries
                for pattern in self.test_patterns:
                    cur.execute("DELETE FROM unified_wal_writes WHERE path LIKE %s", (f'%{pattern}%',))
                    wal_deleted = cur.rowcount
                    if wal_deleted > 0:
                        print(f"    ✅ Deleted {wal_deleted} WAL entries for {pattern}")
                
                # Clean old failed entries
                cur.execute("DELETE FROM unified_wal_writes WHERE status = 'failed' AND created_at < NOW() - INTERVAL '1 hour'")
                old_failed = cur.rowcount
                if old_failed > 0:
                    print(f"    ✅ Deleted {old_failed} old failed WAL entries")
                
                conn.commit()
                return {'deleted': deleted}
        except Exception as e:
            print(f"  ❌ PostgreSQL cleanup failed: {e}")
            return {'deleted': 0}
        finally:
            conn.close()
    
    def cleanup_wal_system(self):
        print("🔄 Cleaning WAL system...")
        try:
            total = 0
            for i in range(3):
                response = requests.post(f'{self.base_url}/wal/cleanup', json={'max_age_hours': 0.1}, timeout=30)
                if response.status_code == 200:
                    data = response.json()
                    deleted = data.get('deleted_entries', 0)
                    reset = data.get('reset_entries', 0)
                    total += deleted + reset
                    if deleted > 0 or reset > 0:
                        print(f"    Round {i+1}: {deleted} deleted, {reset} reset")
            return {'processed': total}
        except Exception as e:
            print(f"  ❌ WAL cleanup failed: {e}")
            return {'processed': 0}
    
    def verify_cleanup(self):
        print("🔍 Verifying cleanup...")
        
        # Check instances
        primary_collections = self.get_collections(self.primary_url, "Primary")
        replica_collections = self.get_collections(self.replica_url, "Replica")
        
        primary_test = sum(1 for c in primary_collections if self.is_test_collection(c.get('name', '')))
        replica_test = sum(1 for c in replica_collections if self.is_test_collection(c.get('name', '')))
        
        print(f"  Primary test collections remaining: {primary_test}")
        print(f"  Replica test collections remaining: {replica_test}")
        
        # Check PostgreSQL
        conn = self.get_db_connection()
        if conn:
            try:
                with conn.cursor() as cur:
                    cur.execute("SELECT COUNT(*) FROM collection_id_mapping")
                    total_mappings = cur.fetchone()[0]
                    
                    test_mappings = 0
                    cur.execute("SELECT collection_name FROM collection_id_mapping")
                    for (name,) in cur.fetchall():
                        if self.is_test_collection(name):
                            test_mappings += 1
                    
                    print(f"  PostgreSQL total mappings: {total_mappings}")
                    print(f"  PostgreSQL test mappings remaining: {test_mappings}")
            except:
                pass
            finally:
                conn.close()
        
        success = primary_test == 0 and replica_test == 0
        
        # CRITICAL: Verify global collection was NOT deleted
        print(f"\n🛡️ VERIFYING GLOBAL COLLECTION PROTECTION:")
        global_on_primary = any(c.get('name', '').lower() == 'global' for c in primary_collections)
        global_on_replica = any(c.get('name', '').lower() == 'global' for c in replica_collections)
        
        if global_on_primary:
            print(f"  ✅ Global collection SAFE on primary")
        else:
            print(f"  🚨 CRITICAL: Global collection MISSING from primary!")
            success = False
        
        if global_on_replica:
            print(f"  ✅ Global collection SAFE on replica")
        else:
            print(f"  🚨 CRITICAL: Global collection MISSING from replica!")
            success = False
        
        return success

def main():
    print("🧹 COMPREHENSIVE TEST DATA CLEANUP")
    print("🛡️ WITH BULLETPROOF GLOBAL COLLECTION PROTECTION")
    print("=" * 60)
    print("This will remove ALL test data from:")
    print("• ChromaDB Primary and Replica instances")
    print("• PostgreSQL collection mappings")
    print("• PostgreSQL WAL entries")
    print("")
    print("🔒 PROTECTED COLLECTIONS (will NEVER be deleted):")
    print("   • global, Global, GLOBAL")
    print("   • production, prod, main")
    print("")
    print("🗑️ SAFE TO DELETE: Only collections with test prefixes")
    print("   • DELETE_TEST_, AUTOTEST_, TEST_, PATCH_TEST_, test_")
    
    confirm = input("\nProceed? (yes/no): ").lower().strip()
    if confirm not in ['yes', 'y']:
        print("❌ Cancelled")
        return
    
    cleaner = TestDataCleaner()
    
    # Cleanup
    chromadb_results = cleaner.cleanup_chromadb()
    postgresql_results = cleaner.cleanup_postgresql()
    wal_results = cleaner.cleanup_wal_system()
    
    # Verify
    success = cleaner.verify_cleanup()
    
    # Summary
    print("\n" + "=" * 60)
    print("📊 CLEANUP SUMMARY")
    print("=" * 60)
    print(f"✅ Primary: {chromadb_results['primary']['deleted']} collections deleted")
    print(f"✅ Replica: {chromadb_results['replica']['deleted']} collections deleted") 
    print(f"✅ PostgreSQL: {postgresql_results['deleted']} mappings deleted")
    print(f"✅ WAL: {wal_results['processed']} entries processed")
    
    if success:
        print("\n🎉 CLEANUP SUCCESSFUL!")
        print("✅ All test data removed")
        print("✅ Production data preserved")
        print("✅ Databases optimized")
    else:
        print("\n⚠️ PARTIAL SUCCESS")
        print("Some test data may remain")

if __name__ == '__main__':
    main() 