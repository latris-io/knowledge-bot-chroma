#!/usr/bin/env python3

import requests
import json
import time

def force_reset_wal_system():
    """Force reset the WAL system to clear failed states"""
    
    base_url = 'https://chroma-load-balancer.onrender.com'
    
    print('🔄 FORCE RESETTING WAL SYSTEM')
    print('=' * 50)
    
    try:
        # Step 1: Clear old failed WAL entries (aggressive cleanup)
        print('1. Clearing failed WAL entries...')
        cleanup_response = requests.post(
            f'{base_url}/wal/cleanup', 
            json={'max_age_hours': 0.1},  # Very aggressive - clear entries older than 6 minutes
            timeout=30
        )
        
        if cleanup_response.status_code == 200:
            cleanup_data = cleanup_response.json()
            print(f'   ✅ WAL cleanup: {cleanup_data.get("deleted_entries", 0)} deleted, {cleanup_data.get("reset_entries", 0)} reset')
        else:
            print(f'   ⚠️ WAL cleanup response: {cleanup_response.status_code}')
        
        # Step 2: Check current system status
        print('\n2. Checking system status after cleanup...')
        status_response = requests.get(f'{base_url}/status')
        
        if status_response.status_code == 200:
            status_data = status_response.json()
            healthy_instances = status_data.get('healthy_instances', 0)
            total_instances = status_data.get('total_instances', 0)
            
            print(f'   Healthy instances: {healthy_instances}/{total_instances}')
            
            # WAL status
            wal_status = status_data.get('unified_wal', {})
            pending_writes = wal_status.get('pending_writes', 0)
            is_syncing = wal_status.get('is_syncing', False)
            
            print(f'   Pending WAL writes: {pending_writes}')
            print(f'   Is syncing: {is_syncing}')
            
            # Performance stats
            perf_stats = status_data.get('performance_stats', {})
            successful_syncs = perf_stats.get('successful_syncs', 0)
            failed_syncs = perf_stats.get('failed_syncs', 0)
            
            print(f'   Sync performance: {successful_syncs} success, {failed_syncs} failed')
        else:
            print(f'   ⚠️ Status check failed: {status_response.status_code}')
        
        # Step 3: Check current collection state
        print('\n3. Checking collection state...')
        collections_response = requests.get(f'{base_url}/api/v2/tenants/default_tenant/databases/default_database/collections')
        
        if collections_response.status_code == 200:
            collections = collections_response.json()
            print(f'   Collections visible through load balancer: {len(collections)}')
            
            for collection in collections:
                name = collection.get('name', 'unknown')
                collection_id = collection.get('id', 'unknown')
                print(f'     - {name}: {collection_id[:8]}...')
        else:
            print(f'   ⚠️ Collection listing failed: {collections_response.status_code}')
        
        # Step 4: Check collection mappings
        print('\n4. Checking collection mappings...')
        mappings_response = requests.get(f'{base_url}/collection/mappings')
        
        if mappings_response.status_code == 200:
            mappings_data = mappings_response.json()
            mapping_count = mappings_data.get('count', 0)
            print(f'   Collection mappings in database: {mapping_count}')
            
            if mapping_count > 0:
                print('   Sample mappings:')
                for mapping in mappings_data.get('mappings', [])[:5]:  # Show first 5
                    name = mapping.get('collection_name', 'unknown')
                    primary_id = mapping.get('primary_collection_id', 'unknown')
                    replica_id = mapping.get('replica_collection_id', 'unknown')
                    print(f'     - {name}: {primary_id[:8]}... ↔ {replica_id[:8]}...')
        else:
            print(f'   ⚠️ Mappings check failed: {mappings_response.status_code}')
        
        print('\n5. System reset analysis:')
        
        # Determine if system is in good state
        if cleanup_response.status_code == 200 and status_response.status_code == 200:
            status_data = status_response.json()
            healthy_instances = status_data.get('healthy_instances', 0)
            pending_writes = status_data.get('unified_wal', {}).get('pending_writes', 0)
            
            if healthy_instances >= 2 and pending_writes == 0:
                print('   ✅ System appears healthy and caught up')
                print('   📝 Ready for testing DELETE operations')
                return True
            else:
                print(f'   ⚠️ System not optimal: {healthy_instances} instances, {pending_writes} pending writes')
                return False
        else:
            print('   ❌ System reset had issues')
            return False

    except Exception as e:
        print(f'❌ Reset failed: {e}')
        return False

if __name__ == '__main__':
    success = force_reset_wal_system()
    
    if success:
        print('\n🎯 SYSTEM READY FOR TESTING')
        print('You can now test DELETE operations safely')
    else:
        print('\n⚠️ SYSTEM NEEDS ATTENTION')
        print('Manual intervention may be required') 