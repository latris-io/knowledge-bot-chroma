#!/usr/bin/env python3

"""
CMS DELETE Monitor and Auto-Fix Service
Monitors for inconsistent DELETE states and automatically fixes them
Can be run as a background service to ensure CMS deletions always work correctly
"""

import requests
import time
import json
import threading
import logging
from datetime import datetime, timedelta

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class CMSDeleteMonitor:
    def __init__(self):
        self.base_url = 'https://chroma-load-balancer.onrender.com'
        self.primary_url = 'https://chroma-primary.onrender.com'
        self.replica_url = 'https://chroma-replica.onrender.com'
        self.monitoring = False
        self.fix_stats = {
            'inconsistencies_detected': 0,
            'fixes_applied': 0,
            'last_check': None,
            'last_fix': None
        }
    
    def check_instances_health(self):
        """Check health of both instances"""
        try:
            primary_health = requests.get(f'{self.primary_url}/api/v1/heartbeat', timeout=5)
            primary_online = primary_health.status_code == 200
        except:
            primary_online = False
        
        try:
            replica_health = requests.get(f'{self.replica_url}/api/v1/heartbeat', timeout=5)
            replica_online = replica_health.status_code == 200
        except:
            replica_online = False
        
        return primary_online, replica_online
    
    def get_collections_from_instance(self, instance_url):
        """Get all collections from an instance"""
        try:
            response = requests.get(
                f'{instance_url}/api/v2/tenants/default_tenant/databases/default_database/collections',
                timeout=30
            )
            
            if response.status_code == 200:
                return {c.get('name'): c.get('id') for c in response.json()}
            
        except Exception as e:
            logger.error(f"Failed to get collections from {instance_url}: {e}")
        
        return {}
    
    def detect_inconsistencies(self):
        """Detect collections that exist on one instance but not the other"""
        primary_online, replica_online = self.check_instances_health()
        
        if not primary_online or not replica_online:
            logger.warning(f"Cannot check consistency - Primary: {'online' if primary_online else 'offline'}, Replica: {'online' if replica_online else 'offline'}")
            return []
        
        primary_collections = self.get_collections_from_instance(self.primary_url)
        replica_collections = self.get_collections_from_instance(self.replica_url)
        
        inconsistencies = []
        
        # Find collections on primary but not replica
        primary_only = set(primary_collections.keys()) - set(replica_collections.keys())
        for collection_name in primary_only:
            # Skip global collection (it's supposed to have different IDs)
            if collection_name != 'global':
                inconsistencies.append({
                    'collection_name': collection_name,
                    'type': 'primary_only',
                    'description': f'Collection exists on primary but not replica'
                })
        
        # Find collections on replica but not primary
        replica_only = set(replica_collections.keys()) - set(primary_collections.keys())
        for collection_name in replica_only:
            if collection_name != 'global':
                inconsistencies.append({
                    'collection_name': collection_name,
                    'type': 'replica_only', 
                    'description': f'Collection exists on replica but not primary'
                })
        
        return inconsistencies
    
    def fix_inconsistency(self, inconsistency):
        """Fix a detected inconsistency"""
        collection_name = inconsistency['collection_name']
        inconsistency_type = inconsistency['type']
        
        logger.info(f"Fixing inconsistency: {collection_name} ({inconsistency_type})")
        
        try:
            if inconsistency_type == 'primary_only':
                # Collection exists on primary but not replica - should be deleted from primary
                # This represents a failed DELETE operation where replica was cleaned but primary wasn't
                success = self.delete_from_instance(self.primary_url, collection_name)
                if success:
                    logger.info(f"✅ Fixed: Deleted {collection_name} from primary")
                    return True
                else:
                    logger.error(f"❌ Failed to delete {collection_name} from primary")
                    return False
            
            elif inconsistency_type == 'replica_only':
                # Collection exists on replica but not primary - should be deleted from replica
                # This is less common but can happen
                success = self.delete_from_instance(self.replica_url, collection_name)
                if success:
                    logger.info(f"✅ Fixed: Deleted {collection_name} from replica")
                    return True
                else:
                    logger.error(f"❌ Failed to delete {collection_name} from replica")
                    return False
            
        except Exception as e:
            logger.error(f"Exception fixing {collection_name}: {e}")
            return False
        
        return False
    
    def delete_from_instance(self, instance_url, collection_name):
        """Delete collection from specific instance"""
        try:
            # Try delete by name
            response = requests.delete(
                f'{instance_url}/api/v2/tenants/default_tenant/databases/default_database/collections/{collection_name}',
                timeout=30
            )
            
            if response.status_code in [200, 204, 404]:
                return True
            
            # Try delete by ID if name fails
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
    
    def monitor_and_fix(self, check_interval=60):
        """Continuous monitoring with auto-fix"""
        logger.info(f"🔍 Starting CMS DELETE monitor (checking every {check_interval}s)")
        self.monitoring = True
        
        while self.monitoring:
            try:
                self.fix_stats['last_check'] = datetime.now()
                
                # Detect inconsistencies
                inconsistencies = self.detect_inconsistencies()
                
                if inconsistencies:
                    self.fix_stats['inconsistencies_detected'] += len(inconsistencies)
                    logger.warning(f"🚨 Detected {len(inconsistencies)} DELETE inconsistencies")
                    
                    # Fix each inconsistency
                    fixes_applied = 0
                    for inconsistency in inconsistencies:
                        if self.fix_inconsistency(inconsistency):
                            fixes_applied += 1
                    
                    self.fix_stats['fixes_applied'] += fixes_applied
                    if fixes_applied > 0:
                        self.fix_stats['last_fix'] = datetime.now()
                        logger.info(f"✅ Applied {fixes_applied}/{len(inconsistencies)} fixes")
                else:
                    logger.debug("✅ No DELETE inconsistencies detected")
                
                # Clean WAL periodically (every 10 checks)
                if self.fix_stats['inconsistencies_detected'] % 10 == 0:
                    self.cleanup_wal()
                
            except Exception as e:
                logger.error(f"Monitor cycle failed: {e}")
            
            # Wait for next check
            time.sleep(check_interval)
    
    def cleanup_wal(self):
        """Periodic WAL cleanup"""
        try:
            response = requests.post(
                f'{self.base_url}/wal/cleanup',
                json={'max_age_hours': 1},  # Clean entries older than 1 hour
                timeout=30
            )
            
            if response.status_code == 200:
                data = response.json()
                logger.info(f"🧹 WAL cleanup: {data.get('deleted_entries', 0)} deleted, {data.get('reset_entries', 0)} reset")
        except:
            pass
    
    def stop_monitoring(self):
        """Stop the monitoring loop"""
        self.monitoring = False
        logger.info("🛑 CMS DELETE monitor stopped")
    
    def get_stats(self):
        """Get monitoring statistics"""
        return self.fix_stats
    
    def enhanced_delete_with_verification(self, collection_name):
        """Enhanced DELETE with immediate verification and fix"""
        logger.info(f"🗑️ Enhanced DELETE with verification: {collection_name}")
        
        # Check initial state
        primary_online, replica_online = self.check_instances_health()
        
        if not primary_online and not replica_online:
            return {'success': False, 'error': 'Both instances offline'}
        
        result = {
            'success': False,
            'primary_deleted': False,
            'replica_deleted': False,
            'verification_passed': False
        }
        
        # Try load balancer DELETE first
        try:
            response = requests.delete(
                f'{self.base_url}/api/v2/tenants/default_tenant/databases/default_database/collections/{collection_name}',
                timeout=30
            )
            
            if response.status_code in [200, 204]:
                logger.info("Load balancer DELETE accepted")
                
                # Wait for sync
                time.sleep(8)
                
                # Verify on both instances
                if primary_online:
                    primary_collections = self.get_collections_from_instance(self.primary_url)
                    result['primary_deleted'] = collection_name not in primary_collections
                
                if replica_online:
                    replica_collections = self.get_collections_from_instance(self.replica_url)
                    result['replica_deleted'] = collection_name not in replica_collections
                
                # Check if verification passed
                verification_passed = True
                if primary_online and not result['primary_deleted']:
                    verification_passed = False
                if replica_online and not result['replica_deleted']:
                    verification_passed = False
                
                result['verification_passed'] = verification_passed
                
                if verification_passed:
                    result['success'] = True
                    logger.info("✅ Load balancer DELETE successful and verified")
                    return result
                else:
                    logger.warning("⚠️ Load balancer DELETE incomplete - applying fixes")
        
        except Exception as e:
            logger.error(f"Load balancer DELETE failed: {e}")
        
        # Direct deletion if load balancer failed or verification failed
        if primary_online and not result['primary_deleted']:
            success = self.delete_from_instance(self.primary_url, collection_name)
            result['primary_deleted'] = success
            if success:
                logger.info("✅ Direct primary deletion successful")
        
        if replica_online and not result['replica_deleted']:
            success = self.delete_from_instance(self.replica_url, collection_name)
            result['replica_deleted'] = success
            if success:
                logger.info("✅ Direct replica deletion successful")
        
        # Final verification
        online_deletions_successful = True
        if primary_online and not result['primary_deleted']:
            online_deletions_successful = False
        if replica_online and not result['replica_deleted']:
            online_deletions_successful = False
        
        result['success'] = online_deletions_successful
        result['verification_passed'] = online_deletions_successful
        
        return result

def run_monitor_service(check_interval=60):
    """Run as background monitoring service"""
    monitor = CMSDeleteMonitor()
    
    try:
        monitor.monitor_and_fix(check_interval)
    except KeyboardInterrupt:
        logger.info("Monitoring stopped by user")
        monitor.stop_monitoring()

def test_enhanced_delete():
    """Test the enhanced DELETE functionality"""
    monitor = CMSDeleteMonitor()
    
    test_collection = f"DELETE_TEST_{int(time.time())}"
    
    try:
        # Create test collection
        create_response = requests.post(
            f"{monitor.base_url}/api/v2/tenants/default_tenant/databases/default_database/collections",
            json={"name": test_collection, "configuration": {"hnsw": {"space": "l2"}}},
            timeout=30
        )
        
        if create_response.status_code in [200, 201]:
            logger.info(f"✅ Created test collection: {test_collection}")
            time.sleep(2)
            
            # Test enhanced delete
            result = monitor.enhanced_delete_with_verification(test_collection)
            
            print(f"\n📊 Enhanced DELETE Test Results:")
            print(f"   Overall success: {'✅' if result['success'] else '❌'}")
            print(f"   Primary deleted: {'✅' if result['primary_deleted'] else '❌'}")
            print(f"   Replica deleted: {'✅' if result['replica_deleted'] else '❌'}")
            print(f"   Verification passed: {'✅' if result['verification_passed'] else '❌'}")
            
            return result['success']
        else:
            logger.error("Failed to create test collection")
            return False
    except Exception as e:
        logger.error(f"Test failed: {e}")
        return False

def main():
    print("🚀 CMS DELETE MONITOR AND AUTO-FIX SERVICE")
    print("=" * 70)
    print("This service monitors for inconsistent DELETE states and fixes them automatically")
    print("Ensures your CMS deletions always work consistently across both instances")
    
    import sys
    
    if len(sys.argv) > 1:
        command = sys.argv[1]
        
        if command == 'monitor':
            print("\n🔍 Starting continuous monitoring service...")
            print("Press Ctrl+C to stop")
            run_monitor_service(check_interval=60)
            
        elif command == 'test':
            print("\n🧪 Testing enhanced DELETE functionality...")
            test_success = test_enhanced_delete()
            
            if test_success:
                print("\n🎉 Enhanced DELETE working perfectly!")
            else:
                print("\n⚠️ Enhanced DELETE needs attention")
            
        elif command == 'check':
            print("\n🔍 Checking for inconsistencies...")
            monitor = CMSDeleteMonitor()
            inconsistencies = monitor.detect_inconsistencies()
            
            if inconsistencies:
                print(f"🚨 Found {len(inconsistencies)} inconsistencies:")
                for inc in inconsistencies:
                    print(f"   - {inc['collection_name']}: {inc['description']}")
                
                print(f"\nRun 'python {sys.argv[0]} fix' to fix these issues")
            else:
                print("✅ No inconsistencies detected!")
                
        elif command == 'fix':
            print("\n🔧 Fixing detected inconsistencies...")
            monitor = CMSDeleteMonitor()
            inconsistencies = monitor.detect_inconsistencies()
            
            if inconsistencies:
                fixes_applied = 0
                for inc in inconsistencies:
                    if monitor.fix_inconsistency(inc):
                        fixes_applied += 1
                
                print(f"✅ Applied {fixes_applied}/{len(inconsistencies)} fixes")
            else:
                print("✅ No inconsistencies to fix!")
        else:
            print(f"Unknown command: {command}")
            show_usage()
    else:
        show_usage()

def show_usage():
    print("\nUsage:")
    print("  python cms_delete_monitor.py test     - Test DELETE functionality")
    print("  python cms_delete_monitor.py check    - Check for inconsistencies")
    print("  python cms_delete_monitor.py fix      - Fix detected inconsistencies")
    print("  python cms_delete_monitor.py monitor  - Run continuous monitoring service")
    print("\nFor your CMS:")
    print("  1. Run 'test' to verify DELETE functionality")
    print("  2. Run 'check' to see if there are any current issues")
    print("  3. Run 'fix' to resolve any inconsistencies")
    print("  4. Run 'monitor' to keep the system healthy automatically")

if __name__ == '__main__':
    main() 