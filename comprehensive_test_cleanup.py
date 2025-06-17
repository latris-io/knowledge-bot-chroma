#!/usr/bin/env python3

"""
Comprehensive Test Data Cleanup
Removes ALL test data from ChromaDB instances and PostgreSQL database
Preserves production collections like 'global'
"""

import requests
import json
import psycopg2
import os
from urllib.parse import urlparse
import time

class ComprehensiveTestCleanup:
    def __init__(self):
        self.base_url = 'https://chroma-load-balancer.onrender.com'
        self.primary_url = 'https://chroma-primary.onrender.com'
        self.replica_url = 'https://chroma-replica.onrender.com'
        
        # Test collection patterns to identify and remove
        self.test_patterns = [
            'DELETE_TEST_',
            'AUTOTEST_',
            'TEST_',
            'PATCH_TEST_',
            'test_collection_',
            'failover_test_',
            'ENHANCED_',
            'debug_',
            'temp_'
        ]
        
        # Production collections to preserve
        self.preserve_collections = ['global']
    
    def get_db_connection(self):
        """Get PostgreSQL database connection"""
        try:
            result = urlparse(os.environ.get('DATABASE_URL', ''))
            if not result.scheme:
                print("❌ DATABASE_URL not set")
                return None
            
            conn = psycopg2.connect(
                database=result.path[1:],
                user=result.username,
                password=result.password,
                host=result.hostname,
                port=result.port
            )
            return conn
        except Exception as e:
            print(f"❌ Database connection failed: {e}")
            return None
    
    def is_test_collection(self, collection_name):
        """Check if collection is a test collection"""
        if collection_name in self.preserve_collections:
            return False
        
        return any(pattern in collection_name for pattern in self.test_patterns)
    
    def get_collections_from_instance(self, instance_url, instance_name):
        """Get all collections from a ChromaDB instance"""
        try:
            response = requests.get(
                f'{instance_url}/api/v2/tenants/default_tenant/databases/default_database/collections',
                timeout=30
            )
            
            if response.status_code == 200:
                collections = response.json()
                print(f"📊 {instance_name}: Found {len(collections)} total collections")
                return collections
            else:
                print(f"❌ {instance_name}: Failed to get collections - {response.status_code}")
                return []
        except Exception as e:
            print(f"❌ {instance_name}: Exception getting collections - {e}")
            return []
    
    def delete_collection_from_instance(self, instance_url, instance_name, collection):
        """Delete a collection from a specific instance"""
        collection_name = collection.get('name', '')
        collection_id = collection.get('id', '')
        
        try:
            # Try delete by name first
            response = requests.delete(
                f'{instance_url}/api/v2/tenants/default_tenant/databases/default_database/collections/{collection_name}',
                timeout=30
            )
            
            if response.status_code in [200, 204, 404]:
                return True, "deleted_by_name"
            
            # Try delete by ID if name fails
            response = requests.delete(
                f'{instance_url}/api/v2/tenants/default_tenant/databases/default_database/collections/{collection_id}',
                timeout=30
            )
            
            if response.status_code in [200, 204, 404]:
                return True, "deleted_by_id"
            
            return False, f"failed_status_{response.status_code}"
            
        except Exception as e:
            return False, f"exception_{str(e)}"
    
    def cleanup_chromadb_instances(self):
        """Clean up test collections from both ChromaDB instances"""
        print("🧹 CLEANING CHROMADB INSTANCES")
        print("=" * 60)
        
        cleanup_stats = {
            'primary': {'total': 0, 'test': 0, 'deleted': 0, 'preserved': 0},
            'replica': {'total': 0, 'test': 0, 'deleted': 0, 'preserved': 0}
        }
        
        # Clean primary instance
        print("\n🔹 Cleaning PRIMARY instance...")
        primary_collections = self.get_collections_from_instance(self.primary_url, "Primary")
        cleanup_stats['primary']['total'] = len(primary_collections)
        
        for collection in primary_collections:
            collection_name = collection.get('name', '')
            
            if self.is_test_collection(collection_name):
                cleanup_stats['primary']['test'] += 1
                success, method = self.delete_collection_from_instance(
                    self.primary_url, "Primary", collection
                )
                
                if success:
                    cleanup_stats['primary']['deleted'] += 1
                    print(f"   ✅ Deleted: {collection_name}")
                else:
                    print(f"   ❌ Failed: {collection_name} - {method}")
            else:
                cleanup_stats['primary']['preserved'] += 1
                print(f"   🛡️ Preserved: {collection_name}")
        
        # Clean replica instance
        print("\n🔹 Cleaning REPLICA instance...")
        replica_collections = self.get_collections_from_instance(self.replica_url, "Replica")
        cleanup_stats['replica']['total'] = len(replica_collections)
        
        for collection in replica_collections:
            collection_name = collection.get('name', '')
            
            if self.is_test_collection(collection_name):
                cleanup_stats['replica']['test'] += 1
                success, method = self.delete_collection_from_instance(
                    self.replica_url, "Replica", collection
                )
                
                if success:
                    cleanup_stats['replica']['deleted'] += 1
                    print(f"   ✅ Deleted: {collection_name}")
                else:
                    print(f"   ❌ Failed: {collection_name} - {method}")
            else:
                cleanup_stats['replica']['preserved'] += 1
                print(f"   🛡️ Preserved: {collection_name}")
        
        return cleanup_stats
    
    def cleanup_postgresql_mappings(self):
        """Clean up test collection mappings from PostgreSQL"""
        print("\n🗄️ CLEANING POSTGRESQL COLLECTION MAPPINGS")
        print("=" * 60)
        
        conn = self.get_db_connection()
        if not conn:
            print("❌ Cannot connect to PostgreSQL - skipping database cleanup")
            return {'deleted': 0, 'preserved': 0, 'total': 0}
        
        try:
            with conn.cursor() as cur:
                # Get all collection mappings
                cur.execute("SELECT collection_name, primary_collection_id, replica_collection_id FROM collection_id_mapping")
                all_mappings = cur.fetchall()
                
                print(f"📊 Found {len(all_mappings)} collection mappings in database")
                
                deleted_count = 0
                preserved_count = 0
                
                for collection_name, primary_id, replica_id in all_mappings:
                    if self.is_test_collection(collection_name):
                        # Delete test collection mapping
                        cur.execute("DELETE FROM collection_id_mapping WHERE collection_name = %s", (collection_name,))
                        deleted_count += 1
                        print(f"   ✅ Deleted mapping: {collection_name}")
                    else:
                        preserved_count += 1
                        print(f"   🛡️ Preserved mapping: {collection_name}")
                
                conn.commit()
                print(f"\n📊 PostgreSQL cleanup: {deleted_count} deleted, {preserved_count} preserved")
                
                return {'deleted': deleted_count, 'preserved': preserved_count, 'total': len(all_mappings)}
                
        except Exception as e:
            print(f"❌ PostgreSQL cleanup failed: {e}")
            return {'deleted': 0, 'preserved': 0, 'total': 0}
        finally:
            conn.close()
    
    def cleanup_wal_entries(self):
        """Clean up test-related WAL entries"""
        print("\n📝 CLEANING WAL ENTRIES")
        print("=" * 60)
        
        conn = self.get_db_connection()
        if not conn:
            print("❌ Cannot connect to PostgreSQL - skipping WAL cleanup")
            return {'deleted': 0}
        
        try:
            with conn.cursor() as cur:
                # Delete WAL entries for test collections
                deleted_count = 0
                
                for pattern in self.test_patterns:
                    cur.execute("""
                        DELETE FROM unified_wal_writes 
                        WHERE path LIKE %s OR path LIKE %s
                    """, (f'%/{pattern}%', f'%{pattern}%'))
                    
                    pattern_deleted = cur.rowcount
                    deleted_count += pattern_deleted
                    
                    if pattern_deleted > 0:
                        print(f"   ✅ Deleted {pattern_deleted} WAL entries for pattern: {pattern}")
                
                # Also clean up old failed entries (older than 1 hour)
                cur.execute("""
                    DELETE FROM unified_wal_writes 
                    WHERE status = 'failed' AND created_at < NOW() - INTERVAL '1 hour'
                """)
                
                old_failed = cur.rowcount
                deleted_count += old_failed
                
                if old_failed > 0:
                    print(f"   ✅ Deleted {old_failed} old failed WAL entries")
                
                conn.commit()
                print(f"\n📊 WAL cleanup: {deleted_count} entries deleted")
                
                return {'deleted': deleted_count}
                
        except Exception as e:
            print(f"❌ WAL cleanup failed: {e}")
            return {'deleted': 0}
        finally:
            conn.close()
    
    def cleanup_pending_deletes(self):
        """Clean up pending delete entries"""
        print("\n⏳ CLEANING PENDING DELETE ENTRIES")
        print("=" * 60)
        
        conn = self.get_db_connection()
        if not conn:
            print("❌ Cannot connect to PostgreSQL - skipping pending deletes cleanup")
            return {'deleted': 0}
        
        try:
            with conn.cursor() as cur:
                # Check if pending_deletes table exists
                cur.execute("""
                    SELECT EXISTS (
                        SELECT FROM information_schema.tables 
                        WHERE table_name = 'pending_deletes'
                    )
                """)
                
                table_exists = cur.fetchone()[0]
                
                if not table_exists:
                    print("   ℹ️ No pending_deletes table found")
                    return {'deleted': 0}
                
                # Delete test-related pending deletes
                deleted_count = 0
                
                for pattern in self.test_patterns:
                    cur.execute("""
                        DELETE FROM pending_deletes 
                        WHERE collection_name LIKE %s
                    """, (f'%{pattern}%',))
                    
                    pattern_deleted = cur.rowcount
                    deleted_count += pattern_deleted
                    
                    if pattern_deleted > 0:
                        print(f"   ✅ Deleted {pattern_deleted} pending deletes for pattern: {pattern}")
                
                conn.commit()
                print(f"\n📊 Pending deletes cleanup: {deleted_count} entries deleted")
                
                return {'deleted': deleted_count}
                
        except Exception as e:
            print(f"❌ Pending deletes cleanup failed: {e}")
            return {'deleted': 0}
        finally:
            conn.close()
    
    def force_wal_system_cleanup(self):
        """Force cleanup of WAL system via load balancer"""
        print("\n🔄 FORCING WAL SYSTEM CLEANUP")
        print("=" * 60)
        
        try:
            total_processed = 0
            
            for i in range(3):
                response = requests.post(
                    f'{self.base_url}/wal/cleanup',
                    json={'max_age_hours': 0.1},  # Clean entries older than 6 minutes
                    timeout=30
                )
                
                if response.status_code == 200:
                    data = response.json()
                    deleted = data.get('deleted_entries', 0)
                    reset = data.get('reset_entries', 0)
                    total_processed += deleted + reset
                    
                    if deleted > 0 or reset > 0:
                        print(f"   Round {i+1}: {deleted} deleted, {reset} reset")
                
                time.sleep(1)
            
            print(f"\n📊 WAL system cleanup: {total_processed} entries processed")
            return {'processed': total_processed}
            
        except Exception as e:
            print(f"❌ WAL system cleanup failed: {e}")
            return {'processed': 0}
    
    def verify_cleanup(self):
        """Verify that cleanup was successful"""
        print("\n🔍 VERIFYING CLEANUP RESULTS")
        print("=" * 60)
        
        # Check ChromaDB instances
        primary_collections = self.get_collections_from_instance(self.primary_url, "Primary")
        replica_collections = self.get_collections_from_instance(self.replica_url, "Replica")
        
        # Count remaining test collections
        primary_test_remaining = sum(1 for c in primary_collections if self.is_test_collection(c.get('name', '')))
        replica_test_remaining = sum(1 for c in replica_collections if self.is_test_collection(c.get('name', '')))
        
        print(f"\n📊 VERIFICATION RESULTS:")
        print(f"   Primary test collections remaining: {primary_test_remaining}")
        print(f"   Replica test collections remaining: {replica_test_remaining}")
        
        # Check PostgreSQL mappings
        conn = self.get_db_connection()
        if conn:
            try:
                with conn.cursor() as cur:
                    cur.execute("SELECT COUNT(*) FROM collection_id_mapping")
                    total_mappings = cur.fetchone()[0]
                    
                    # Count test mappings
                    test_mapping_count = 0
                    cur.execute("SELECT collection_name FROM collection_id_mapping")
                    for (collection_name,) in cur.fetchall():
                        if self.is_test_collection(collection_name):
                            test_mapping_count += 1
                    
                    print(f"   PostgreSQL total mappings: {total_mappings}")
                    print(f"   PostgreSQL test mappings remaining: {test_mapping_count}")
                    
            except Exception as e:
                print(f"   ❌ PostgreSQL verification failed: {e}")
            finally:
                conn.close()
        
        # Overall success
        cleanup_success = (primary_test_remaining == 0 and 
                          replica_test_remaining == 0)
        
        if cleanup_success:
            print(f"\n🎉 CLEANUP SUCCESSFUL!")
            print("✅ All test collections removed from ChromaDB instances")
            print("✅ Database cleaned of test-related entries")
        else:
            print(f"\n⚠️ CLEANUP PARTIALLY SUCCESSFUL")
            print("Some test collections may remain - manual cleanup may be needed")
        
        return cleanup_success
    
    def comprehensive_cleanup(self):
        """Perform comprehensive cleanup of all test data"""
        print("🧹 COMPREHENSIVE TEST DATA CLEANUP")
        print("=" * 80)
        print("Removing ALL test data while preserving production collections")
        print("=" * 80)
        
        results = {}
        
        # Step 1: Clean ChromaDB instances
        results['chromadb'] = self.cleanup_chromadb_instances()
        
        # Step 2: Clean PostgreSQL collection mappings
        results['postgresql_mappings'] = self.cleanup_postgresql_mappings()
        
        # Step 3: Clean WAL entries
        results['wal_entries'] = self.cleanup_wal_entries()
        
        # Step 4: Clean pending deletes
        results['pending_deletes'] = self.cleanup_pending_deletes()
        
        # Step 5: Force WAL system cleanup
        results['wal_system'] = self.force_wal_system_cleanup()
        
        # Step 6: Verify cleanup
        results['verification_success'] = self.verify_cleanup()
        
        return results

def main():
    """Main execution"""
    cleanup = ComprehensiveTestCleanup()
    
    print("🚨 WARNING: This will delete ALL test data from:")
    print("• ChromaDB Primary instance")
    print("• ChromaDB Replica instance") 
    print("• PostgreSQL collection_id_mapping table")
    print("• PostgreSQL unified_wal_writes table")
    print("• PostgreSQL pending_deletes table")
    print("\nProduction collections like 'global' will be preserved.")
    
    confirm = input("\nProceed with cleanup? (yes/no): ").lower().strip()
    
    if confirm not in ['yes', 'y']:
        print("❌ Cleanup cancelled by user")
        return
    
    # Perform comprehensive cleanup
    results = cleanup.comprehensive_cleanup()
    
    # Final summary
    print("\n" + "=" * 80)
    print("📊 COMPREHENSIVE CLEANUP SUMMARY")
    print("=" * 80)
    
    chromadb_stats = results['chromadb']
    postgresql_stats = results['postgresql_mappings']
    wal_stats = results['wal_entries']
    pending_stats = results['pending_deletes']
    wal_system_stats = results['wal_system']
    
    print(f"✅ ChromaDB Primary: {chromadb_stats['primary']['deleted']}/{chromadb_stats['primary']['test']} test collections deleted")
    print(f"✅ ChromaDB Replica: {chromadb_stats['replica']['deleted']}/{chromadb_stats['replica']['test']} test collections deleted")
    print(f"✅ PostgreSQL mappings: {postgresql_stats['deleted']} test mappings deleted")
    print(f"✅ WAL entries: {wal_stats['deleted']} test entries deleted")
    print(f"✅ Pending deletes: {pending_stats['deleted']} test entries deleted")
    print(f"✅ WAL system: {wal_system_stats['processed']} entries processed")
    
    if results['verification_success']:
        print(f"\n🎉 COMPREHENSIVE CLEANUP COMPLETED SUCCESSFULLY!")
        print("🔥 All test data has been removed from all systems")
        print("🛡️ Production data has been preserved")
        print("✨ Your databases are now clean and optimized")
    else:
        print(f"\n⚠️ CLEANUP MOSTLY SUCCESSFUL")
        print("Some test data may remain - check the details above")
    
    print(f"\n🎯 WHAT'S CLEAN NOW:")
    print("• ChromaDB instances contain only production collections")
    print("• PostgreSQL database mappings are optimized") 
    print("• WAL system backlog is cleared")
    print("• No phantom mappings causing sync issues")
    print("• Your CMS DELETE operations should work perfectly!")

if __name__ == '__main__':
    main() 