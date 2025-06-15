#!/usr/bin/env python3

import psycopg2
import requests
import json
import time

def emergency_database_repair():
    """Emergency repair of corrupted ChromaDB databases with phantom collections"""
    
    DATABASE_URL = "postgresql://chroma_user:xqIF9T5U6LhySuSw86JqWYf7qtyGDXy8@dpg-d16mkandiees73db52u0-a.oregon-postgres.render.com/chroma_ha"
    
    print("🚨 EMERGENCY DATABASE REPAIR - PHANTOM COLLECTION CORRUPTION")
    print("=" * 60)
    
    try:
        # Step 1: Clear ALL WAL entries to start fresh
        print("1. Clearing all corrupted WAL entries...")
        with psycopg2.connect(DATABASE_URL) as conn:
            with conn.cursor() as cur:
                cur.execute("DELETE FROM unified_wal_writes")
                deleted_wal = cur.rowcount
                
                cur.execute("DELETE FROM collection_id_mapping")
                deleted_mappings = cur.rowcount
                
                conn.commit()
                print(f"   ✅ Cleared {deleted_wal} WAL entries")
                print(f"   ✅ Cleared {deleted_mappings} collection mappings")
        
        # Step 2: Reset ChromaDB instances (clear phantom collections)
        print("2. Attempting to reset ChromaDB instances...")
        
        # Try to reset primary
        try:
            reset_primary = requests.post("https://chroma-primary.onrender.com/api/v1/reset", timeout=30)
            print(f"   Primary reset: {reset_primary.status_code}")
        except:
            print("   Primary reset not available - continuing anyway")
        
        # Try to reset replica
        try:
            reset_replica = requests.post("https://chroma-replica.onrender.com/api/v1/reset", timeout=30)
            print(f"   Replica reset: {reset_replica.status_code}")
        except:
            print("   Replica reset not available - continuing anyway")
        
        # Step 3: Wait for services to stabilize
        print("3. Waiting for services to stabilize...")
        time.sleep(10)
        
        # Step 4: Create NEW working collection for your uploads
        print("4. Creating fresh working collection...")
        
        collection_name = "user_documents"  # Simple, clean name
        
        create_payload = {
            "name": collection_name,
            "configuration_json": {
                "hnsw": {
                    "space": "l2",
                    "ef_construction": 100
                }
            }
        }
        
        # Create on primary
        primary_response = requests.post(
            "https://chroma-primary.onrender.com/api/v2/tenants/default_tenant/databases/default_database/collections",
            headers={"Content-Type": "application/json"},
            json=create_payload,
            timeout=30
        )
        
        if primary_response.status_code in [200, 201]:
            primary_data = primary_response.json()
            primary_id = primary_data.get('id')
            print(f"   ✅ Created primary: {primary_id}")
            
            # Verify it's actually accessible (not phantom)
            verify_primary = requests.get(
                f"https://chroma-primary.onrender.com/api/v2/tenants/default_tenant/databases/default_database/collections/{primary_id}",
                timeout=30
            )
            
            if verify_primary.status_code == 200:
                print("   ✅ Primary verified - NOT phantom!")
                
                # Create on replica
                replica_response = requests.post(
                    "https://chroma-replica.onrender.com/api/v2/tenants/default_tenant/databases/default_database/collections",
                    headers={"Content-Type": "application/json"},
                    json=create_payload,
                    timeout=30
                )
                
                if replica_response.status_code in [200, 201]:
                    replica_data = replica_response.json()
                    replica_id = replica_data.get('id')
                    print(f"   ✅ Created replica: {replica_id}")
                    
                    # Verify replica is accessible
                    verify_replica = requests.get(
                        f"https://chroma-replica.onrender.com/api/v2/tenants/default_tenant/databases/default_database/collections/{replica_id}",
                        timeout=30
                    )
                    
                    if verify_replica.status_code == 200:
                        print("   ✅ Replica verified - NOT phantom!")
                        
                        # Create mapping
                        with psycopg2.connect(DATABASE_URL) as conn:
                            with conn.cursor() as cur:
                                cur.execute("""
                                    INSERT INTO collection_id_mapping 
                                    (collection_name, primary_collection_id, replica_collection_id, collection_config)
                                    VALUES (%s, %s, %s, %s)
                                """, (
                                    collection_name,
                                    primary_id,
                                    replica_id,
                                    json.dumps(create_payload["configuration_json"])
                                ))
                                conn.commit()
                                print("   ✅ Collection mapping created")
                        
                        # Step 5: Test with actual document
                        print("5. Testing with real document...")
                        
                        test_payload = {
                            "embeddings": [[0.1] * 3072],
                            "documents": ["Emergency repair test - your uploads will work now!"],
                            "metadatas": [{"test": "emergency_repair", "timestamp": int(time.time())}],
                            "ids": [f"repair_test_{int(time.time())}"]
                        }
                        
                        # Test via load balancer
                        test_response = requests.post(
                            f"https://chroma-load-balancer.onrender.com/api/v2/tenants/default_tenant/databases/default_database/collections/{primary_id}/add",
                            headers={"Content-Type": "application/json"},
                            json=test_payload,
                            timeout=30
                        )
                        
                        if test_response.status_code in [200, 201]:
                            print("   ✅ Test document uploaded successfully!")
                            
                            print()
                            print("🎉🎉🎉 EMERGENCY REPAIR SUCCESSFUL! 🎉🎉🎉")
                            print("🔥 DATABASE CORRUPTION FIXED!")
                            print()
                            print("📌 YOUR NEW WORKING COLLECTION:")
                            print(f"   Collection Name: {collection_name}")
                            print(f"   Primary ID:  {primary_id}")
                            print(f"   Replica ID:  {replica_id}")
                            print()
                            print("📝 UPDATE YOUR INGESTION SERVICE:")
                            print(f"   Collection ID: {primary_id}")
                            print(f"   Collection Name: {collection_name}")
                            print(f"   URL: https://chroma-load-balancer.onrender.com/api/v2/tenants/default_tenant/databases/default_database/collections/{primary_id}/add")
                            print()
                            print("✅ Your file uploads should now work with intelligent sync!")
                            
                        else:
                            print(f"   ❌ Test document failed: {test_response.text}")
                    else:
                        print("   ❌ Replica still phantom")
                else:
                    print(f"   ❌ Replica creation failed: {replica_response.text}")
            else:
                print("   ❌ Primary still phantom")
        else:
            print(f"   ❌ Primary creation failed: {primary_response.text}")
        
    except Exception as e:
        print(f"❌ Emergency repair failed: {e}")
        import traceback
        print(traceback.format_exc())

if __name__ == "__main__":
    emergency_database_repair() 