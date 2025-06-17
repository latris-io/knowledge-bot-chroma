#!/usr/bin/env python3
"""
Clean Query Test - Simple verification of query functionality
"""

import requests
import json
import uuid
import time

def main():
    base_url = 'https://chroma-load-balancer.onrender.com'
    collection_name = f'clean_query_test_{int(time.time())}_{uuid.uuid4().hex[:8]}'

    print(f'🧪 Clean Query Test: {collection_name}')

    try:
        # Create collection
        create_resp = requests.post(
            f'{base_url}/api/v2/tenants/default_tenant/databases/default_database/collections', 
            json={'name': collection_name}, 
            timeout=30
        )
        print(f'📚 Create: {create_resp.status_code}')

        if create_resp.status_code not in [200, 201]:
            print(f'❌ Create failed: {create_resp.text[:200]}')
            return False

        # Add document
        doc_id = f'clean_test_{uuid.uuid4().hex[:8]}'
        add_resp = requests.post(
            f'{base_url}/api/v2/tenants/default_tenant/databases/default_database/collections/{collection_name}/add',
            json={
                'embeddings': [[0.1, 0.2, 0.3, 0.4, 0.5]],
                'documents': ['Clean test document'],
                'metadatas': [{'test': 'clean_query'}],
                'ids': [doc_id]
            }, 
            timeout=30
        )
        print(f'📄 Add: {add_resp.status_code}')
        
        if add_resp.status_code not in [200, 201]:
            print(f'❌ Add failed: {add_resp.text[:200]}')
            return False

        print('⏳ Waiting 5s for indexing...')
        time.sleep(5)
        
        # Query
        query_resp = requests.post(
            f'{base_url}/api/v2/tenants/default_tenant/databases/default_database/collections/{collection_name}/query',
            json={
                'query_embeddings': [[0.1, 0.2, 0.3, 0.4, 0.5]],
                'n_results': 1,
                'include': ['documents', 'metadatas']
            }, 
            timeout=30
        )
        print(f'🔍 Query: {query_resp.status_code}')
        
        success = False
        if query_resp.status_code == 200:
            result = query_resp.json()
            result_count = len(result.get('ids', [[]])[0]) if result.get('ids') else 0
            print(f'📊 Results: {result_count}')
            
            if result_count > 0:
                print(f'✅ SUCCESS: Query returned {result_count} result(s)')
                print(f'📋 IDs: {result.get("ids", [[]])[0]}')
                print(f'📄 Documents: {result.get("documents", [[]])[0]}')
                success = True
            else:
                print('❌ FAIL: Query returned 0 results')
                print(f'🔍 Full response: {json.dumps(result, indent=2)}')
        else:
            print(f'❌ Query failed: {query_resp.text[:200]}')
        
        return success
        
    except Exception as e:
        print(f'❌ Exception: {e}')
        return False
        
    finally:
        # Cleanup
        try:
            cleanup_resp = requests.delete(
                f'{base_url}/api/v2/tenants/default_tenant/databases/default_database/collections/{collection_name}', 
                timeout=30
            )
            print(f'🧹 Cleanup: {cleanup_resp.status_code}')
        except Exception as e:
            print(f'⚠️ Cleanup failed: {e}')

if __name__ == "__main__":
    success = main()
    print(f'\n{"✅ QUERY WORKING" if success else "❌ QUERY FAILING"}')
    exit(0 if success else 1) 