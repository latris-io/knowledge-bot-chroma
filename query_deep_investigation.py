#!/usr/bin/env python3
"""
Deep Query Investigation - Test different scenarios to find working patterns
"""

import requests
import json
import uuid
import time

def test_scenario(name, base_url, collection_name, embedding, doc_text, delay=5):
    """Test a specific query scenario"""
    print(f'\n🧪 {name}')
    print(f'   Collection: {collection_name}')
    print(f'   Embedding: {embedding}')
    print(f'   Delay: {delay}s')
    
    try:
        # Create collection
        create_resp = requests.post(
            f'{base_url}/api/v2/tenants/default_tenant/databases/default_database/collections', 
            json={'name': collection_name}, 
            timeout=30
        )
        print(f'   📚 Create: {create_resp.status_code}')
        
        if create_resp.status_code not in [200, 201]:
            print(f'   ❌ Create failed')
            return False

        # Add document
        doc_id = f'test_{uuid.uuid4().hex[:8]}'
        add_resp = requests.post(
            f'{base_url}/api/v2/tenants/default_tenant/databases/default_database/collections/{collection_name}/add',
            json={
                'embeddings': [embedding],
                'documents': [doc_text],
                'metadatas': [{'test_scenario': name}],
                'ids': [doc_id]
            }, 
            timeout=30
        )
        print(f'   📄 Add: {add_resp.status_code}')
        
        if add_resp.status_code not in [200, 201]:
            print(f'   ❌ Add failed')
            return False

        # Wait
        print(f'   ⏳ Waiting {delay}s...')
        time.sleep(delay)
        
        # Query with exact same embedding
        query_resp = requests.post(
            f'{base_url}/api/v2/tenants/default_tenant/databases/default_database/collections/{collection_name}/query',
            json={
                'query_embeddings': [embedding],
                'n_results': 1,
                'include': ['documents', 'metadatas']
            }, 
            timeout=30
        )
        print(f'   🔍 Query: {query_resp.status_code}')
        
        if query_resp.status_code == 200:
            result = query_resp.json()
            result_count = len(result.get('ids', [[]])[0]) if result.get('ids') else 0
            print(f'   📊 Results: {result_count}')
            
            if result_count > 0:
                print(f'   ✅ SUCCESS: Found {result_count} result(s)')
                distances = result.get('distances', [[]])[0] if result.get('distances') else []
                if distances:
                    print(f'   📏 Distance: {distances[0]:.6f}')
                return True
            else:
                print(f'   ❌ FAIL: No results')
                return False
        else:
            print(f'   ❌ Query failed: {query_resp.status_code}')
            return False
            
    except Exception as e:
        print(f'   ❌ Exception: {e}')
        return False
    finally:
        # Cleanup
        try:
            requests.delete(f'{base_url}/api/v2/tenants/default_tenant/databases/default_database/collections/{collection_name}', timeout=30)
        except:
            pass

def main():
    base_url = 'https://chroma-load-balancer.onrender.com'
    timestamp = int(time.time())
    
    print('🔍 DEEP QUERY INVESTIGATION')
    print('Testing different scenarios to find working patterns')
    print('='*70)
    
    # Test scenarios
    scenarios = [
        {
            'name': 'Standard 5D embedding',
            'collection': f'test_standard_{timestamp}_{uuid.uuid4().hex[:8]}',
            'embedding': [0.1, 0.2, 0.3, 0.4, 0.5],
            'doc_text': 'Standard test document',
            'delay': 5
        },
        {
            'name': 'Different 5D embedding',
            'collection': f'test_different_{timestamp}_{uuid.uuid4().hex[:8]}',
            'embedding': [0.6, 0.7, 0.8, 0.9, 1.0],
            'doc_text': 'Different test document',
            'delay': 5
        },
        {
            'name': 'Longer delay (15s)',
            'collection': f'test_delay_{timestamp}_{uuid.uuid4().hex[:8]}',
            'embedding': [0.2, 0.3, 0.4, 0.5, 0.6],
            'doc_text': 'Delayed test document',
            'delay': 15
        },
        {
            'name': 'Higher dimensional (10D)',
            'collection': f'test_10d_{timestamp}_{uuid.uuid4().hex[:8]}',
            'embedding': [0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0],
            'doc_text': '10D test document',
            'delay': 5
        },
        {
            'name': 'Simple normalized',
            'collection': f'test_norm_{timestamp}_{uuid.uuid4().hex[:8]}',
            'embedding': [1.0, 0.0, 0.0, 0.0, 0.0],
            'doc_text': 'Normalized test document',
            'delay': 10
        }
    ]
    
    results = []
    
    for scenario in scenarios:
        success = test_scenario(
            scenario['name'],
            base_url,
            scenario['collection'],
            scenario['embedding'],
            scenario['doc_text'],
            scenario['delay']
        )
        results.append((scenario['name'], success))
    
    # Summary
    print('\n' + '='*70)
    print('📊 DEEP INVESTIGATION RESULTS')
    print('='*70)
    
    successful = 0
    for name, success in results:
        status = '✅ PASS' if success else '❌ FAIL'
        print(f'{status} {name}')
        if success:
            successful += 1
    
    print(f'\n📈 Success Rate: {successful}/{len(results)} ({(successful/len(results)*100):.1f}%)')
    
    if successful == 0:
        print('\n❌ ALL QUERIES FAILED - Systematic query indexing issue')
        print('🔍 Recommendations:')
        print('   - Check ChromaDB embedding indexing configuration')
        print('   - Verify embedding storage vs query consistency')  
        print('   - Check if embedding index needs rebuild')
    elif successful == len(results):
        print('\n✅ ALL QUERIES WORKED - Issue might be test-specific')
    else:
        print(f'\n⚠️ PARTIAL SUCCESS - Pattern detected')
        print('🔍 Working scenarios may reveal the solution')
    
    return successful > 0

if __name__ == "__main__":
    success = main()
    exit(0 if success else 1) 