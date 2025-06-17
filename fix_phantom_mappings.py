#!/usr/bin/env python3

import requests
import json

def fix_phantom_mappings():
    """Clean up phantom collection mappings"""
    
    base_url = 'https://chroma-load-balancer.onrender.com'
    primary_url = 'https://chroma-primary.onrender.com'
    replica_url = 'https://chroma-replica.onrender.com'
    
    print('🔧 FIXING PHANTOM COLLECTION MAPPINGS')
    print('=' * 50)
    
    try:
        # Get all collection mappings
        print('1. Fetching current collection mappings...')
        mappings_response = requests.get(f'{base_url}/collection/mappings')
        
        if mappings_response.status_code != 200:
            print(f'❌ Failed to get mappings: {mappings_response.status_code}')
            return
        
        mappings_data = mappings_response.json()
        all_mappings = mappings_data.get('mappings', [])
        print(f'   Found {len(all_mappings)} total mappings')
        
        # Check which collections actually exist
        print('\n2. Checking actual collection existence...')
        
        phantom_mappings = []
        valid_mappings = []
        
        for mapping in all_mappings:
            collection_name = mapping.get('collection_name')
            primary_id = mapping.get('primary_collection_id')
            replica_id = mapping.get('replica_collection_id')
            
            print(f'   Checking {collection_name}...')
            
            # Check if collections exist on both instances
            primary_exists = False
            replica_exists = False
            
            try:
                primary_resp = requests.get(
                    f'{primary_url}/api/v2/tenants/default_tenant/databases/default_database/collections/{primary_id}',
                    timeout=10
                )
                primary_exists = primary_resp.status_code == 200
            except:
                primary_exists = False
            
            try:
                replica_resp = requests.get(
                    f'{replica_url}/api/v2/tenants/default_tenant/databases/default_database/collections/{replica_id}',
                    timeout=10
                )
                replica_exists = replica_resp.status_code == 200
            except:
                replica_exists = False
            
            print(f'     Primary exists: {primary_exists}, Replica exists: {replica_exists}')
            
            if not primary_exists and not replica_exists:
                print(f'     ❌ PHANTOM MAPPING: {collection_name} - collections deleted but mapping remains')
                phantom_mappings.append(mapping)
            elif primary_exists and replica_exists:
                print(f'     ✅ VALID MAPPING: {collection_name} - both collections exist')
                valid_mappings.append(mapping)
            else:
                print(f'     ⚠️ INCONSISTENT: {collection_name} - exists on only one instance')
                phantom_mappings.append(mapping)  # Treat inconsistent as phantom for cleanup
        
        print(f'\n📊 MAPPING ANALYSIS:')
        print(f'   Valid mappings: {len(valid_mappings)}')
        print(f'   Phantom mappings to clean: {len(phantom_mappings)}')
        
        # Clean up phantom mappings by deleting them through the load balancer API
        if phantom_mappings:
            print(f'\n3. Cleaning up {len(phantom_mappings)} phantom mappings...')
            
            for mapping in phantom_mappings:
                collection_name = mapping.get('collection_name')
                print(f'   Cleaning mapping for: {collection_name}')
                
                # Delete mapping through load balancer (which should clean up database)
                try:
                    delete_response = requests.delete(
                        f'{base_url}/collection/mappings/{collection_name}',
                        timeout=10
                    )
                    
                    if delete_response.status_code in [200, 204, 404]:
                        print(f'     ✅ Cleaned mapping for {collection_name}')
                    else:
                        print(f'     ⚠️ Cleanup response for {collection_name}: {delete_response.status_code}')
                except Exception as e:
                    print(f'     ❌ Failed to clean {collection_name}: {e}')
        
        # Verify cleanup
        print('\n4. Verifying cleanup...')
        final_mappings_response = requests.get(f'{base_url}/collection/mappings')
        
        if final_mappings_response.status_code == 200:
            final_data = final_mappings_response.json()
            remaining_count = final_data.get('count', 0)
            print(f'   Remaining mappings: {remaining_count}')
            
            if remaining_count == len(valid_mappings):
                print(f'   ✅ SUCCESS: All phantom mappings cleaned up')
            else:
                print(f'   ⚠️ Some mappings may still exist')
        
        # Check collection listings now
        print('\n5. Checking final collection state...')
        
        primary_collections = requests.get(f'{primary_url}/api/v2/tenants/default_tenant/databases/default_database/collections')
        replica_collections = requests.get(f'{replica_url}/api/v2/tenants/default_tenant/databases/default_database/collections')
        lb_collections = requests.get(f'{base_url}/api/v2/tenants/default_tenant/databases/default_database/collections')
        
        print(f'   Primary collections: {len(primary_collections.json()) if primary_collections.status_code == 200 else "Error"}')
        print(f'   Replica collections: {len(replica_collections.json()) if replica_collections.status_code == 200 else "Error"}')
        print(f'   Load balancer collections: {len(lb_collections.json()) if lb_collections.status_code == 200 else "Error"}')
        
        if lb_collections.status_code == 200:
            lb_collection_data = lb_collections.json()
            if len(lb_collection_data) == 0:
                print(f'   ✅ Load balancer now shows 0 collections (phantom mappings cleaned)')
            else:
                remaining_names = [c.get('name') for c in lb_collection_data]
                print(f'   Remaining collections: {remaining_names}')

    except Exception as e:
        print(f'❌ Cleanup failed: {e}')

if __name__ == '__main__':
    fix_phantom_mappings() 