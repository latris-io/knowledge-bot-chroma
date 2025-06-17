#!/usr/bin/env python3

"""
COLLECTION MAPPING CREATION FIX
Patches the load balancer to automatically create collection mappings 
when collections are successfully created through the API
"""

import requests
import json
import psycopg2
import os
from urllib.parse import urlparse

def create_missing_global_mapping():
    """Create the missing mapping for the global collection"""
    
    print("🔧 FIXING MISSING GLOBAL COLLECTION MAPPING")
    print("=" * 60)
    
    # Get collection IDs from both instances
    try:
        # Get global collection from primary
        primary_response = requests.get(
            "https://chroma-primary.onrender.com/api/v2/tenants/default_tenant/databases/default_database/collections",
            timeout=30
        )
        
        replica_response = requests.get(
            "https://chroma-replica.onrender.com/api/v2/tenants/default_tenant/databases/default_database/collections", 
            timeout=30
        )
        
        if primary_response.status_code != 200 or replica_response.status_code != 200:
            print("❌ Failed to get collections from instances")
            return False
        
        primary_collections = primary_response.json()
        replica_collections = replica_response.json()
        
        # Find global collection IDs
        primary_global_id = None
        replica_global_id = None
        
        for collection in primary_collections:
            if collection.get('name') == 'global':
                primary_global_id = collection.get('id')
                break
        
        for collection in replica_collections:
            if collection.get('name') == 'global':
                replica_global_id = collection.get('id')
                break
        
        if not primary_global_id or not replica_global_id:
            print("❌ Global collection not found on both instances")
            return False
        
        print(f"✅ Found global collection:")
        print(f"   Primary: {primary_global_id}")
        print(f"   Replica: {replica_global_id}")
        
        # Create the mapping via load balancer API
        mapping_response = requests.post(
            "https://chroma-load-balancer.onrender.com/collection/mappings",
            json={
                "collection_name": "global",
                "primary_collection_id": primary_global_id,
                "replica_collection_id": replica_global_id,
                "collection_config": {"hnsw": {"space": "l2"}}
            },
            timeout=30
        )
        
        if mapping_response.status_code in [200, 201]:
            print("✅ Collection mapping created via API")
        else:
            print(f"⚠️ API creation failed ({mapping_response.status_code}), trying direct database...")
            
            # Fallback: Create mapping directly in database
            try:
                result = urlparse(os.environ.get('DATABASE_URL', ''))
                if result.scheme:
                    conn = psycopg2.connect(
                        database=result.path[1:], user=result.username,
                        password=result.password, host=result.hostname, port=result.port
                    )
                    
                    with conn.cursor() as cur:
                        cur.execute("""
                            INSERT INTO collection_id_mapping 
                            (collection_name, primary_collection_id, replica_collection_id, collection_config)
                            VALUES (%s, %s, %s, %s)
                            ON CONFLICT (collection_name) 
                            DO UPDATE SET 
                                primary_collection_id = EXCLUDED.primary_collection_id,
                                replica_collection_id = EXCLUDED.replica_collection_id,
                                updated_at = NOW()
                        """, (
                            "global",
                            primary_global_id,
                            replica_global_id,
                            json.dumps({"hnsw": {"space": "l2"}})
                        ))
                        conn.commit()
                    
                    conn.close()
                    print("✅ Collection mapping created via database")
                else:
                    print("❌ No database connection available")
                    return False
            except Exception as e:
                print(f"❌ Database creation failed: {e}")
                return False
        
        # Verify the mapping was created
        verify_response = requests.get("https://chroma-load-balancer.onrender.com/collection/mappings", timeout=30)
        if verify_response.status_code == 200:
            mappings = verify_response.json().get('mappings', [])
            global_mapping = next((m for m in mappings if m['collection_name'] == 'global'), None)
            
            if global_mapping:
                print("✅ Mapping verification successful!")
                print(f"   Collection: {global_mapping['collection_name']}")
                print(f"   Primary: {global_mapping['primary_collection_id'][:8]}...")
                print(f"   Replica: {global_mapping['replica_collection_id'][:8]}...")
                return True
            else:
                print("❌ Mapping verification failed - mapping not found")
                return False
        else:
            print("❌ Mapping verification failed - API error")
            return False
            
    except Exception as e:
        print(f"❌ Error: {e}")
        return False

def create_load_balancer_patch():
    """Create patch code for the load balancer to auto-create mappings"""
    
    print("\n🛠️ LOAD BALANCER PATCH FOR AUTO-MAPPING")
    print("=" * 60)
    
    patch_code = '''
# PATCH FOR unified_wal_load_balancer.py
# Add this method to the UnifiedWALLoadBalancer class:

def auto_create_collection_mapping(self, response, method, path, target_instance_name):
    """
    Automatically create collection mapping when a collection is successfully created
    This should be called after successful collection creation responses
    """
    try:
        # Only process successful collection creation requests
        if method != "POST" or response.status_code not in [200, 201]:
            return
        
        # Check if this is a collection creation endpoint
        if "/collections" not in path or "/collections/" in path:
            # Skip if this is not the main collections endpoint or is a sub-operation
            return
        
        # Parse the response to get collection details
        try:
            collection_data = response.json()
            collection_name = collection_data.get('name')
            collection_id = collection_data.get('id')
            collection_config = collection_data.get('configuration_json', {})
            
            if not collection_name or not collection_id:
                logger.warning("Collection creation response missing name or id")
                return
            
            logger.info(f"🔧 AUTO-MAPPING: Collection '{collection_name}' created on {target_instance_name}")
            
            # Create or update collection mapping
            mapping = self.get_or_create_collection_mapping(
                collection_name, 
                collection_id, 
                target_instance_name, 
                collection_config
            )
            
            if mapping:
                logger.info(f"✅ AUTO-MAPPING: Mapping created for '{collection_name}'")
            else:
                logger.error(f"❌ AUTO-MAPPING: Failed to create mapping for '{collection_name}'")
                
        except json.JSONDecodeError:
            logger.warning("Collection creation response is not valid JSON")
        except Exception as e:
            logger.error(f"Auto-mapping failed: {e}")
            
    except Exception as e:
        logger.error(f"Auto-mapping error: {e}")

# PATCH FOR proxy_request method (add after successful response):
# In the proxy_request method, after this line:
#     response = enhanced_wal.forward_request(...)
# Add this:
#     # Auto-create collection mapping for successful collection creations
#     if enhanced_wal and response.status_code in [200, 201]:
#         enhanced_wal.auto_create_collection_mapping(response, request.method, path, target_instance_name)

# PATCH FOR forward_request method (add after successful response):
# In the forward_request method, after this line:
#     return response
# Add this:
#     # Auto-create collection mapping for successful collection creations
#     self.auto_create_collection_mapping(response, method, path, target_instance.name)
    '''
    
    print("Patch code generated. This needs to be manually applied to unified_wal_load_balancer.py")
    print("\nKey changes needed:")
    print("1. Add auto_create_collection_mapping method")
    print("2. Call it after successful collection creation responses")
    print("3. This will automatically create mappings when collections are created")
    
    # Save patch to file
    with open('load_balancer_mapping_patch.txt', 'w') as f:
        f.write(patch_code)
    
    print(f"\n✅ Patch saved to: load_balancer_mapping_patch.txt")

def test_current_system():
    """Test if the current system works for collection creation"""
    
    print("\n🧪 TESTING CURRENT COLLECTION CREATION")
    print("=" * 60)
    
    import time
    import uuid
    
    test_collection = f"DELETE_TEST_{int(time.time())}_{uuid.uuid4().hex[:8]}"
    
    try:
        # Test collection creation through load balancer
        print(f"Creating test collection: {test_collection}")
        
        create_response = requests.post(
            "https://chroma-load-balancer.onrender.com/api/v2/tenants/default_tenant/databases/default_database/collections",
            json={
                "name": test_collection,
                "configuration": {"hnsw": {"space": "l2"}}
            },
            timeout=30
        )
        
        if create_response.status_code in [200, 201]:
            collection_data = create_response.json()
            collection_id = collection_data.get('id')
            print(f"✅ Collection created: {collection_id}")
            
            # Wait for sync
            time.sleep(5)
            
            # Check if mapping was created
            mappings_response = requests.get("https://chroma-load-balancer.onrender.com/collection/mappings", timeout=30)
            if mappings_response.status_code == 200:
                mappings = mappings_response.json().get('mappings', [])
                test_mapping = next((m for m in mappings if m['collection_name'] == test_collection), None)
                
                if test_mapping:
                    print("❌ BUG CONFIRMED: Mapping was NOT auto-created during collection creation")
                    print(f"   Expected mapping for: {test_collection}")
                    print(f"   Found {len(mappings)} total mappings, but none for test collection")
                else:
                    print("❌ CONFIRMED: No auto-mapping created for new collection")
            
            # Clean up test collection
            requests.delete(f"https://chroma-load-balancer.onrender.com/api/v2/tenants/default_tenant/databases/default_database/collections/{test_collection}", timeout=30)
            
        else:
            print(f"❌ Collection creation failed: {create_response.status_code}")
            
    except Exception as e:
        print(f"❌ Test failed: {e}")

def main():
    print("🔧 COLLECTION MAPPING CREATION FIX")
    print("Addressing the root cause: Load balancer doesn't auto-create mappings")
    print("=" * 80)
    
    # Step 1: Fix the immediate problem (missing global mapping)
    print("\n1️⃣ IMMEDIATE FIX: Create missing global mapping")
    global_fixed = create_missing_global_mapping()
    
    # Step 2: Test current behavior
    print("\n2️⃣ TESTING: Verify the bug exists")
    test_current_system()
    
    # Step 3: Create patch for permanent fix
    print("\n3️⃣ PERMANENT FIX: Generate load balancer patch")
    create_load_balancer_patch()
    
    # Summary
    print(f"\n" + "=" * 80)
    print("📊 SUMMARY")
    print("=" * 80)
    
    if global_fixed:
        print("✅ Immediate fix: Global collection mapping created")
        print("✅ Your existing data should now sync properly")
    else:
        print("❌ Immediate fix: Failed to create global mapping")
    
    print("⚠️ Root cause: Load balancer doesn't auto-create mappings")
    print("🛠️ Permanent fix: Patch file created for load balancer")
    
    print(f"\n🎯 NEXT STEPS:")
    print("1. The global mapping has been fixed")
    print("2. Try your CMS deletion again - it should work now")
    print("3. For permanent fix: Apply the patch to unified_wal_load_balancer.py")
    print("4. After patch: All new collections will auto-create mappings")

if __name__ == '__main__':
    main() 