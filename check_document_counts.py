#!/usr/bin/env python3

import requests
import json

def check_documents(instance_name, base_url, collection_id):
    """Check document count in a collection"""
    try:
        # First, try to get collection info
        collection_response = requests.get(
            f'{base_url}/api/v2/tenants/default_tenant/databases/default_database/collections/{collection_id}',
            timeout=30
        )
        
        if collection_response.status_code != 200:
            print(f'{instance_name}: Collection not found - {collection_response.status_code}')
            return None
        
        # Query documents in the collection with proper ChromaDB format
        query_payload = {
            "query_embeddings": None,
            "query_texts": ["test"],
            "n_results": 1000,
            "include": ["metadatas", "documents"]
        }
        
        response = requests.post(
            f'{base_url}/api/v2/tenants/default_tenant/databases/default_database/collections/{collection_id}/query',
            json=query_payload,
            timeout=30
        )
        
        if response.status_code == 200:
            data = response.json()
            doc_count = len(data.get('ids', []))
            print(f'{instance_name}: {doc_count} documents in global collection')
            
            # Show some document IDs if they exist
            if doc_count > 0:
                doc_ids = data.get('ids', [])[:5]  # Show first 5 IDs
                print(f'   Sample document IDs: {doc_ids}')
            
            return doc_count
        elif response.status_code == 422:
            # Try simpler query format
            simple_payload = {
                "query_texts": ["test"],
                "n_results": 10
            }
            
            response = requests.post(
                f'{base_url}/api/v2/tenants/default_tenant/databases/default_database/collections/{collection_id}/query',
                json=simple_payload,
                timeout=30
            )
            
            if response.status_code == 200:
                data = response.json()
                doc_count = len(data.get('ids', []))
                print(f'{instance_name}: {doc_count} documents in global collection (simple query)')
                return doc_count
            else:
                print(f'{instance_name}: Query failed even with simple format - {response.status_code}')
                print(f'   Response: {response.text[:200]}')
                return None
        else:
            print(f'{instance_name}: Query error {response.status_code} - {response.text[:100]}')
            return None
    except Exception as e:
        print(f'{instance_name}: Exception - {e}')
        return None

def main():
    primary_url = 'https://chroma-primary.onrender.com'
    replica_url = 'https://chroma-replica.onrender.com'
    
    # Collection IDs from our earlier collection mapping check
    primary_collection_id = 'b985a771-811d-4cce-a1fe-4d7206f05fb1'
    replica_collection_id = '6f8c4244-d84e-40ac-a487-92ac4d823072'
    
    print('🔍 CHECKING DOCUMENT COUNTS IN GLOBAL COLLECTION')
    print('=' * 50)
    
    # Check documents in global collection on both instances
    primary_count = check_documents('Primary', primary_url, primary_collection_id)
    replica_count = check_documents('Replica', replica_url, replica_collection_id)
    
    print(f'\n📊 DOCUMENT COUNT COMPARISON:')
    print(f'Primary: {primary_count} documents')
    print(f'Replica: {replica_count} documents')
    
    if primary_count is not None and replica_count is not None:
        if primary_count > replica_count:
            print('❌ PRIMARY HAS MORE DATA - deletion not synced to primary!')
            print('   This matches the user\'s report: replica was cleaned but primary wasn\'t')
        elif replica_count > primary_count:
            print('❌ REPLICA HAS MORE DATA - unexpected state')
        else:
            print('✅ Both instances have same document count')
            if primary_count == 0:
                print('   Both collections are empty (fully synced deletion)')
            else:
                print('   Both collections have data (no deletion occurred)')

if __name__ == '__main__':
    main() 