#!/usr/bin/env python3

import requests
import json

def test_load_balancer_access():
    """Test accessing global collection through load balancer"""
    
    load_balancer_url = 'https://chroma-load-balancer.onrender.com'
    
    print('🔍 TESTING LOAD BALANCER ACCESS TO GLOBAL COLLECTION')
    print('=' * 60)
    
    try:
        # Test 1: Get collection info by name
        print('1. Testing collection access by name...')
        response = requests.get(
            f'{load_balancer_url}/api/v2/tenants/default_tenant/databases/default_database/collections/global',
            timeout=30
        )
        print(f'   Status: {response.status_code}')
        if response.status_code == 200:
            data = response.json()
            print(f'   Collection ID: {data.get("id", "N/A")}')
            print(f'   Collection name: {data.get("name", "N/A")}')
        else:
            print(f'   Error: {response.text[:100]}')
        
        # Test 2: Query documents by name
        print('\n2. Testing document query by collection name...')
        query_response = requests.post(
            f'{load_balancer_url}/api/v2/tenants/default_tenant/databases/default_database/collections/global/query',
            json={'query_texts': ['test'], 'n_results': 10},
            timeout=30
        )
        
        print(f'   Status: {query_response.status_code}')
        if query_response.status_code == 200:
            query_data = query_response.json()
            doc_count = len(query_data.get('ids', []))
            print(f'   Documents found: {doc_count}')
            if doc_count > 0:
                print(f'   Sample IDs: {query_data.get("ids", [])[:3]}')
                print(f'   ✅ DATA IS ACCESSIBLE - deletion did not work')
            else:
                print(f'   ✅ NO DOCUMENTS - deletion worked correctly')
        else:
            print(f'   Error: {query_response.text[:100]}')
        
        # Test 3: List all collections
        print('\n3. Testing collection listing...')
        list_response = requests.get(
            f'{load_balancer_url}/api/v2/tenants/default_tenant/databases/default_database/collections',
            timeout=30
        )
        
        print(f'   Status: {list_response.status_code}')
        if list_response.status_code == 200:
            collections = list_response.json()
            global_collections = [c for c in collections if c.get('name') == 'global']
            print(f'   Total collections: {len(collections)}')
            print(f'   Global collections found: {len(global_collections)}')
            
            if global_collections:
                for i, col in enumerate(global_collections):
                    print(f'     Global #{i+1}: {col.get("id", "N/A")[:8]}... (name: {col.get("name")})')
        else:
            print(f'   Error: {list_response.text[:100]}')

    except Exception as e:
        print(f'❌ Exception: {e}')

if __name__ == '__main__':
    test_load_balancer_access() 