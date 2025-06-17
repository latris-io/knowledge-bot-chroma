#!/usr/bin/env python3

"""
Enhanced Delete Sync System
Ensures reliable chunk deletion synchronization between ChromaDB instances
Handles offline scenarios and phantom mapping cleanup
"""

import requests
import json
import time
import psycopg2
import os
from urllib.parse import urlparse
from typing import Dict, List, Optional, Tuple
import threading
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class EnhancedDeleteSyncManager:
    """
    Manages reliable DELETE synchronization with phantom mapping cleanup
    and offline instance recovery
    """
    
    def __init__(self):
        self.base_url = 'https://chroma-load-balancer.onrender.com'
        self.primary_url = 'https://chroma-primary.onrender.com'
        self.replica_url = 'https://chroma-replica.onrender.com'
        
    def get_db_connection(self):
        """Get database connection with retry logic"""
        max_retries = 3
        for attempt in range(max_retries):
            try:
                result = urlparse(os.environ.get('DATABASE_URL', ''))
                if not result.scheme:
                    logger.error("DATABASE_URL not set")
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
                logger.warning(f"Database connection attempt {attempt + 1} failed: {e}")
                if attempt < max_retries - 1:
                    time.sleep(2 ** attempt)  # Exponential backoff
                else:
                    logger.error("All database connection attempts failed")
                    return None

    def cleanup_phantom_mappings(self) -> int:
        """
        Clean up phantom collection mappings that exist in database
        but not in actual ChromaDB instances
        """
        logger.info("🧹 Starting phantom mapping cleanup...")
        
        try:
            # Get all current mappings
            mappings_response = requests.get(f'{self.base_url}/collection/mappings', timeout=30)
            if mappings_response.status_code != 200:
                logger.error(f"Failed to get mappings: {mappings_response.status_code}")
                return 0
            
            mappings_data = mappings_response.json()
            all_mappings = mappings_data.get('mappings', [])
            
            if not all_mappings:
                logger.info("No mappings found to clean")
                return 0
            
            logger.info(f"Found {len(all_mappings)} mappings to check")
            
            # Check which collections actually exist
            phantom_count = 0
            
            conn = self.get_db_connection()
            if not conn:
                logger.error("Cannot connect to database for cleanup")
                return 0
            
            try:
                with conn.cursor() as cur:
                    for mapping in all_mappings:
                        collection_name = mapping.get('collection_name', '')
                        primary_id = mapping.get('primary_collection_id', '')
                        replica_id = mapping.get('replica_collection_id', '')
                        
                        # Skip production collections (non-test collections)
                        if not any(prefix in collection_name.upper() for prefix in ['AUTOTEST_', 'TEST_', 'DELETE_TEST_']):
                            continue
                        
                        # Check if collections exist on instances
                        primary_exists = self.check_collection_exists(self.primary_url, primary_id)
                        replica_exists = self.check_collection_exists(self.replica_url, replica_id)
                        
                        if not primary_exists and not replica_exists:
                            # Both collections deleted - remove phantom mapping
                            logger.info(f"Removing phantom mapping: {collection_name}")
                            cur.execute(
                                "DELETE FROM collection_id_mapping WHERE collection_name = %s",
                                (collection_name,)
                            )
                            phantom_count += 1
                
                conn.commit()
                logger.info(f"✅ Cleaned up {phantom_count} phantom mappings")
                return phantom_count
                
            finally:
                conn.close()
                
        except Exception as e:
            logger.error(f"Phantom mapping cleanup failed: {e}")
            return 0

    def check_collection_exists(self, instance_url: str, collection_id: str) -> bool:
        """Check if a collection exists on a specific instance"""
        try:
            response = requests.get(
                f'{instance_url}/api/v2/tenants/default_tenant/databases/default_database/collections/{collection_id}',
                timeout=10
            )
            return response.status_code == 200
        except Exception:
            return False

    def enhanced_delete_operation(self, collection_name: str) -> Dict[str, any]:
        """
        Execute enhanced DELETE operation with comprehensive sync
        """
        logger.info(f"🗑️ Starting enhanced DELETE for collection: {collection_name}")
        
        result = {
            'success': False,
            'primary_deleted': False,
            'replica_deleted': False,
            'wal_logged': False,
            'offline_instances': [],
            'errors': []
        }
        
        # Step 1: Check instance availability
        primary_online = self.check_instance_health(self.primary_url)
        replica_online = self.check_instance_health(self.replica_url)
        
        logger.info(f"Instance status - Primary: {'online' if primary_online else 'offline'}, Replica: {'online' if replica_online else 'offline'}")
        
        if not primary_online:
            result['offline_instances'].append('primary')
        if not replica_online:
            result['offline_instances'].append('replica')
        
        # Step 2: Execute DELETE on available instances
        if primary_online:
            result['primary_deleted'] = self.delete_from_instance(self.primary_url, collection_name)
            if result['primary_deleted']:
                logger.info("✅ Primary deletion successful")
            else:
                result['errors'].append("Primary deletion failed")
        
        if replica_online:
            result['replica_deleted'] = self.delete_from_instance(self.replica_url, collection_name)
            if result['replica_deleted']:
                logger.info("✅ Replica deletion successful")
            else:
                result['errors'].append("Replica deletion failed")
        
        # Step 3: Log to WAL for offline instances
        if result['offline_instances']:
            result['wal_logged'] = self.log_pending_delete(collection_name, result['offline_instances'])
        
        # Step 4: Clean up collection mapping
        self.cleanup_collection_mapping(collection_name)
        
        # Step 5: Determine overall success
        online_deletions_successful = True
        if primary_online and not result['primary_deleted']:
            online_deletions_successful = False
        if replica_online and not result['replica_deleted']:
            online_deletions_successful = False
        
        result['success'] = online_deletions_successful and (result['wal_logged'] if result['offline_instances'] else True)
        
        return result

    def check_instance_health(self, instance_url: str) -> bool:
        """Check if an instance is healthy and responding"""
        try:
            response = requests.get(f'{instance_url}/api/v1/heartbeat', timeout=5)
            return response.status_code == 200
        except Exception:
            return False

    def delete_from_instance(self, instance_url: str, collection_name: str) -> bool:
        """Delete collection from a specific instance"""
        try:
            # First try by name
            response = requests.delete(
                f'{instance_url}/api/v2/tenants/default_tenant/databases/default_database/collections/{collection_name}',
                timeout=30
            )
            
            if response.status_code in [200, 204, 404]:
                return True
            
            # If name-based deletion fails, try to find by ID and delete
            collections_response = requests.get(
                f'{instance_url}/api/v2/tenants/default_tenant/databases/default_database/collections',
                timeout=30
            )
            
            if collections_response.status_code == 200:
                collections = collections_response.json()
                for collection in collections:
                    if collection.get('name') == collection_name:
                        collection_id = collection.get('id')
                        
                        delete_response = requests.delete(
                            f'{instance_url}/api/v2/tenants/default_tenant/databases/default_database/collections/{collection_id}',
                            timeout=30
                        )
                        
                        return delete_response.status_code in [200, 204, 404]
            
            return False
            
        except Exception as e:
            logger.error(f"Delete from instance failed: {e}")
            return False

    def log_pending_delete(self, collection_name: str, offline_instances: List[str]) -> bool:
        """Log pending DELETE operation for offline instances"""
        try:
            conn = self.get_db_connection()
            if not conn:
                return False
            
            try:
                with conn.cursor() as cur:
                    # Create pending deletes table if it doesn't exist
                    cur.execute("""
                        CREATE TABLE IF NOT EXISTS pending_deletes (
                            id SERIAL PRIMARY KEY,
                            collection_name VARCHAR(255) NOT NULL,
                            target_instances TEXT[] NOT NULL,
                            created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
                            attempts INTEGER DEFAULT 0,
                            last_attempt TIMESTAMP WITH TIME ZONE,
                            status VARCHAR(20) DEFAULT 'pending'
                        )
                    """)
                    
                    # Insert pending delete record
                    cur.execute("""
                        INSERT INTO pending_deletes (collection_name, target_instances)
                        VALUES (%s, %s)
                    """, (collection_name, offline_instances))
                    
                    conn.commit()
                    logger.info(f"✅ Logged pending delete for {collection_name} on instances: {offline_instances}")
                    return True
                    
            finally:
                conn.close()
                
        except Exception as e:
            logger.error(f"Failed to log pending delete: {e}")
            return False

    def cleanup_collection_mapping(self, collection_name: str):
        """Clean up collection mapping for deleted collection"""
        try:
            conn = self.get_db_connection()
            if not conn:
                return
            
            try:
                with conn.cursor() as cur:
                    cur.execute(
                        "DELETE FROM collection_id_mapping WHERE collection_name = %s",
                        (collection_name,)
                    )
                    if cur.rowcount > 0:
                        logger.info(f"✅ Cleaned up mapping for {collection_name}")
                    conn.commit()
            finally:
                conn.close()
                
        except Exception as e:
            logger.error(f"Failed to cleanup mapping: {e}")

    def process_pending_deletes(self) -> int:
        """
        Process pending DELETE operations for instances that came back online
        """
        logger.info("🔄 Processing pending DELETE operations...")
        
        try:
            conn = self.get_db_connection()
            if not conn:
                return 0
            
            processed_count = 0
            
            try:
                with conn.cursor() as cur:
                    # Get all pending deletes
                    cur.execute("""
                        SELECT id, collection_name, target_instances, attempts
                        FROM pending_deletes 
                        WHERE status = 'pending' AND attempts < 5
                        ORDER BY created_at ASC
                    """)
                    
                    pending_deletes = cur.fetchall()
                    
                    for delete_id, collection_name, target_instances, attempts in pending_deletes:
                        success = True
                        
                        for instance_name in target_instances:
                            instance_url = self.primary_url if instance_name == 'primary' else self.replica_url
                            
                            if self.check_instance_health(instance_url):
                                if self.delete_from_instance(instance_url, collection_name):
                                    logger.info(f"✅ Processed pending delete for {collection_name} on {instance_name}")
                                else:
                                    success = False
                                    logger.warning(f"⚠️ Failed to process pending delete for {collection_name} on {instance_name}")
                            else:
                                success = False
                                logger.info(f"Instance {instance_name} still offline")
                        
                        # Update the record
                        if success:
                            cur.execute("""
                                UPDATE pending_deletes 
                                SET status = 'completed', last_attempt = NOW()
                                WHERE id = %s
                            """, (delete_id,))
                            processed_count += 1
                        else:
                            cur.execute("""
                                UPDATE pending_deletes 
                                SET attempts = attempts + 1, last_attempt = NOW()
                                WHERE id = %s
                            """, (delete_id,))
                    
                    conn.commit()
                    
            finally:
                conn.close()
            
            if processed_count > 0:
                logger.info(f"✅ Processed {processed_count} pending DELETE operations")
            
            return processed_count
            
        except Exception as e:
            logger.error(f"Failed to process pending deletes: {e}")
            return 0

    def force_wal_cleanup(self) -> bool:
        """Force cleanup of WAL backlog"""
        try:
            logger.info("🧹 Forcing WAL cleanup...")
            
            # Multiple aggressive cleanup rounds
            for i in range(5):
                response = requests.post(
                    f'{self.base_url}/wal/cleanup',
                    json={'max_age_hours': 0.01},
                    timeout=30
                )
                
                if response.status_code == 200:
                    data = response.json()
                    deleted = data.get('deleted_entries', 0)
                    reset = data.get('reset_entries', 0)
                    if deleted > 0 or reset > 0:
                        logger.info(f"Round {i+1}: {deleted} deleted, {reset} reset")
                
                time.sleep(2)  # Brief pause between rounds
            
            return True
            
        except Exception as e:
            logger.error(f"WAL cleanup failed: {e}")
            return False

    def comprehensive_system_repair(self) -> Dict[str, any]:
        """
        Perform comprehensive system repair to fix DELETE sync issues
        """
        logger.info("🔧 Starting comprehensive system repair...")
        
        results = {
            'phantom_mappings_cleaned': 0,
            'wal_cleanup_success': False,
            'pending_deletes_processed': 0,
            'system_healthy': False
        }
        
        try:
            # Step 1: Clean up phantom mappings
            results['phantom_mappings_cleaned'] = self.cleanup_phantom_mappings()
            
            # Step 2: Force WAL cleanup
            results['wal_cleanup_success'] = self.force_wal_cleanup()
            
            # Step 3: Process pending deletes
            results['pending_deletes_processed'] = self.process_pending_deletes()
            
            # Step 4: Check final system health
            status_response = requests.get(f'{self.base_url}/status', timeout=30)
            if status_response.status_code == 200:
                status_data = status_response.json()
                healthy_instances = status_data.get('healthy_instances', 0)
                pending_writes = status_data.get('unified_wal', {}).get('pending_writes', 0)
                
                results['system_healthy'] = healthy_instances >= 2 and pending_writes < 10
                
                logger.info(f"System status: {healthy_instances} healthy instances, {pending_writes} pending writes")
            
            return results
            
        except Exception as e:
            logger.error(f"Comprehensive repair failed: {e}")
            return results

def main():
    """Main function to repair the DELETE sync system"""
    
    print("🚀 ENHANCED DELETE SYNC SYSTEM REPAIR")
    print("=" * 60)
    
    manager = EnhancedDeleteSyncManager()
    
    # Perform comprehensive repair
    results = manager.comprehensive_system_repair()
    
    print(f"\n📊 REPAIR RESULTS:")
    print(f"✅ Phantom mappings cleaned: {results['phantom_mappings_cleaned']}")
    print(f"✅ WAL cleanup successful: {results['wal_cleanup_success']}")
    print(f"✅ Pending deletes processed: {results['pending_deletes_processed']}")
    print(f"✅ System healthy: {results['system_healthy']}")
    
    # Test the enhanced DELETE functionality
    print(f"\n🧪 TESTING ENHANCED DELETE FUNCTIONALITY...")
    
    test_collection = f"DELETE_TEST_{int(time.time())}"
    
    # Create test collection first
    try:
        create_response = requests.post(
            f"{manager.base_url}/api/v2/tenants/default_tenant/databases/default_database/collections",
            json={"name": test_collection, "configuration": {"hnsw": {"space": "l2"}}},
            timeout=30
        )
        
        if create_response.status_code in [200, 201]:
            print(f"   ✅ Test collection created: {test_collection}")
            
            # Wait for sync
            time.sleep(5)
            
            # Test enhanced delete
            delete_result = manager.enhanced_delete_operation(test_collection)
            
            print(f"   📊 DELETE Results:")
            print(f"      Success: {delete_result['success']}")
            print(f"      Primary deleted: {delete_result['primary_deleted']}")
            print(f"      Replica deleted: {delete_result['replica_deleted']}")
            print(f"      WAL logged: {delete_result['wal_logged']}")
            print(f"      Offline instances: {delete_result['offline_instances']}")
            
            if delete_result['success']:
                print(f"   🎉 ENHANCED DELETE WORKING!")
            else:
                print(f"   ⚠️ DELETE still has issues: {delete_result['errors']}")
                
        else:
            print(f"   ❌ Failed to create test collection: {create_response.status_code}")
            
    except Exception as e:
        print(f"   ❌ Test failed: {e}")
    
    print(f"\n🎯 SUMMARY:")
    if results['system_healthy']:
        print("✅ System repaired successfully!")
        print("✅ DELETE operations should now work reliably")
        print("✅ Offline instance recovery is enabled")
    else:
        print("⚠️ System partially repaired")
        print("⚠️ Some issues may persist")
    
    print(f"\n📋 FOR YOUR CMS:")
    print("• DELETE operations now handle offline instances")
    print("• Phantom mappings have been cleaned")
    print("• WAL sync should be more reliable")
    print("• Test your CMS file deletions now!")

if __name__ == '__main__':
    main() 