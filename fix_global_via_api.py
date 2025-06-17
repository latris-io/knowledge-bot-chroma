#!/usr/bin/env python3

import requests
import json

def get_collection_info(base_url, collection_name):
    """Get collection info from ChromaDB instance"""
    try:
        response = requests.get(f"{base_url}/api/v2/tenants/default_tenant/databases/default_database/collections/{collection_name}")
        if response.status_code == 200:
            data = response.json()
            return data.get('id')
        return None
    except Exception as e:
        print(f"Error getting collection from {base_url}: {e}")
        return None

def create_mapping_via_api(collection_name, primary_id, replica_id):
    """Create collection mapping via load balancer API"""
    try:
        url = "https://chroma-load-balancer.onrender.com/api/admin/create_mapping"
        payload = {
            "collection_name": collection_name,
            "primary_collection_id": primary_id,
            "replica_collection_id": replica_id
        }
        
        response = requests.post(url, json=payload)
        
        if response.status_code == 200:
            result = response.json()
            print(f"✅ API Response: {result}")
            return True
        else:
            print(f"❌ API Error {response.status_code}: {response.text}")
            return False
            
    except Exception as e:
        print(f"❌ API request error: {e}")
        return False

def main():
    print("🔧 FIXING GLOBAL COLLECTION MAPPING VIA API")
    print("=" * 50)
    
    # Get collection IDs from both instances
    print("1. Getting collection IDs from both instances...")
    
    primary_url = "https://chroma-primary.onrender.com"
    replica_url = "https://chroma-replica.onrender.com"
    
    primary_id = get_collection_info(primary_url, "global")
    replica_id = get_collection_info(replica_url, "global")
    
    if not primary_id:
        print("❌ 'global' collection not found on primary instance")
        return
        
    if not replica_id:
        print("❌ 'global' collection not found on replica instance")
        return
        
    print(f"   Primary 'global': {primary_id}")
    print(f"   Replica 'global': {replica_id}")
    
    # Create mapping via API
    print("2. Creating collection mapping via load balancer API...")
    success = create_mapping_via_api("global", primary_id, replica_id)
    
    if success:
        print("\n🎉 GLOBAL COLLECTION MAPPING FIXED!")
        print("   Your CMS DELETE operations should now work properly")
    else:
        print("\n❌ Failed to create mapping via API")

if __name__ == "__main__":
    main() 