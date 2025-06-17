#!/usr/bin/env python3

import requests
import json

def debug_wal_failures():
    """Debug WAL sync failures to identify root cause"""
    
    base_url = 'https://chroma-load-balancer.onrender.com'
    
    print('🔍 DEBUGGING WAL SYNC FAILURES')
    print('=' * 50)
    
    try:
        # Check WAL cleanup to get more detailed error info
        print('1. Checking recent WAL cleanup status...')
        cleanup_response = requests.post(f'{base_url}/wal/cleanup', json={'max_age_hours': 1})
        
        if cleanup_response.status_code == 200:
            cleanup_data = cleanup_response.json()
            print(f'   Cleanup result: {cleanup_data}')
        else:
            print(f'   Cleanup failed: {cleanup_response.status_code} - {cleanup_response.text[:100]}')
        
        # Try to force sync by checking pending writes
        print('\n2. Checking WAL status details...')
        wal_response = requests.get(f'{base_url}/wal/status')
        
        if wal_response.status_code == 200:
            wal_data = wal_response.json()
            print(f'   WAL system approach: {wal_data.get("wal_system", {}).get("approach")}')
            print(f'   Pending writes: {wal_data.get("wal_system", {}).get("pending_writes")}')
            print(f'   Is syncing: {wal_data.get("wal_system", {}).get("is_syncing")}')
            
            perf_stats = wal_data.get("performance_stats", {})
            print(f'   Performance: {perf_stats.get("successful_syncs")} success, {perf_stats.get("failed_syncs")} failed')
            print(f'   Avg throughput: {perf_stats.get("avg_sync_throughput")}')
        else:
            print(f'   WAL status failed: {wal_response.status_code}')
        
        # Check collection mappings for consistency
        print('\n3. Checking collection mapping consistency...')
        mappings_response = requests.get(f'{base_url}/collection/mappings')
        
        if mappings_response.status_code == 200:
            mappings_data = mappings_response.json()
            global_mappings = [m for m in mappings_data.get('mappings', []) if m.get('collection_name') == 'global']
            
            print(f'   Total mappings: {mappings_data.get("count")}')
            print(f'   Global mappings: {len(global_mappings)}')
            
            if global_mappings:
                for mapping in global_mappings:
                    print(f'     Primary ID: {mapping.get("primary_collection_id", "N/A")[:8]}...')
                    print(f'     Replica ID: {mapping.get("replica_collection_id", "N/A")[:8]}...')
                    print(f'     Updated: {mapping.get("updated_at", "N/A")}')
        else:
            print(f'   Mappings failed: {mappings_response.status_code}')
        
        # Test direct instance access to see which one fails
        print('\n4. Testing direct instance access...')
        
        primary_url = 'https://chroma-primary.onrender.com'
        replica_url = 'https://chroma-replica.onrender.com'
        
        # Test primary instance health
        try:
            primary_health = requests.get(f'{primary_url}/api/v1/heartbeat', timeout=10)
            print(f'   Primary heartbeat: {primary_health.status_code}')
        except Exception as e:
            print(f'   Primary heartbeat failed: {e}')
        
        # Test replica instance health  
        try:
            replica_health = requests.get(f'{replica_url}/api/v1/heartbeat', timeout=10)
            print(f'   Replica heartbeat: {replica_health.status_code}')
        except Exception as e:
            print(f'   Replica heartbeat failed: {e}')
        
        # Test collection access on each instance
        primary_id = 'b985a771-811d-4cce-a1fe-4d7206f05fb1'
        replica_id = '6f8c4244-d84e-40ac-a487-92ac4d823072'
        
        print('\n5. Testing collection access on each instance...')
        
        try:
            primary_col = requests.get(f'{primary_url}/api/v2/tenants/default_tenant/databases/default_database/collections/{primary_id}', timeout=10)
            print(f'   Primary collection access: {primary_col.status_code}')
            if primary_col.status_code != 200:
                print(f'     Error: {primary_col.text[:100]}')
        except Exception as e:
            print(f'   Primary collection access failed: {e}')
        
        try:
            replica_col = requests.get(f'{replica_url}/api/v2/tenants/default_tenant/databases/default_database/collections/{replica_id}', timeout=10)
            print(f'   Replica collection access: {replica_col.status_code}')
            if replica_col.status_code != 200:
                print(f'     Error: {replica_col.text[:100]}')
        except Exception as e:
            print(f'   Replica collection access failed: {e}')

    except Exception as e:
        print(f'❌ Debug failed: {e}')

if __name__ == '__main__':
    debug_wal_failures() 