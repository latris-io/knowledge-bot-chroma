#!/usr/bin/env python3
"""
Manual fix for the current 'global' collection mapping
Uses the proven approach from create_working_collection.py
"""

import requests
import psycopg2
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

def create_mapping_in_db(collection_name, primary_id, replica_id):
    """Create collection mapping in PostgreSQL using the proven connection method"""
    try:
        # Use the same connection approach as create_working_collection.py
        conn = psycopg2.connect(
            "postgresql://chroma_user:chroma_password@dpg-ctu71klds78s73e47cag-a.oregon-postgres.render.com:5432/chroma_db?sslmode=require"
        )
        cursor = conn.cursor()
        
        # Check if mapping already exists
        cursor.execute(
            "SELECT collection_name FROM collection_id_mapping WHERE collection_name = %s",
            (collection_name,)
        )
        
        if cursor.fetchone():
            print(f"⚠️ Mapping for '{collection_name}' already exists - updating...")
            cursor.execute(
                """UPDATE collection_id_mapping 
                   SET primary_collection_id = %s, replica_collection_id = %s, updated_at = NOW()
                   WHERE collection_name = %s""",
                (primary_id, replica_id, collection_name)
            )
        else:
            print(f"✅ Creating new mapping for '{collection_name}'...")
            cursor.execute(
                """INSERT INTO collection_id_mapping 
                   (collection_name, primary_collection_id, replica_collection_id, created_at) 
                   VALUES (%s, %s, %s, NOW())""",
                (collection_name, primary_id, replica_id)
            )
        
        conn.commit()
        conn.close()
        
        print(f"✅ Mapping saved successfully:")
        print(f"   Collection: {collection_name}")
        print(f"   Primary: {primary_id}")
        print(f"   Replica: {replica_id}")
        return True
        
    except Exception as e:
        print(f"❌ Database error: {e}")
        return False

def main():
    print("🔧 FIXING CURRENT GLOBAL COLLECTION MAPPING")
    print("=" * 50)
    
    # Get current collection IDs
    print("1. Getting current collection IDs...")
    
    primary_url = "https://chroma-primary.onrender.com"
    replica_url = "https://chroma-replica.onrender.com"
    
    primary_id = get_collection_info(primary_url, "global")
    replica_id = get_collection_info(replica_url, "global")
    
    if not primary_id:
        print("❌ 'global' collection not found on primary instance")
        return False
        
    if not replica_id:
        print("❌ 'global' collection not found on replica instance")
        return False
        
    print(f"   Primary 'global': {primary_id}")
    print(f"   Replica 'global': {replica_id}")
    
    # Create the mapping
    print("2. Creating collection mapping in database...")
    success = create_mapping_in_db("global", primary_id, replica_id)
    
    if success:
        print("\n🎉 GLOBAL COLLECTION MAPPING FIXED!")
        print("   Your CMS DELETE operations should now work properly")
        print("   Future collections will auto-create mappings thanks to the load balancer fix")
        return True
    else:
        print("\n❌ Failed to create mapping")
        return False

if __name__ == "__main__":
    main() 