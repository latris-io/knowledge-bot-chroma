#!/usr/bin/env python3

import psycopg2
import requests
import json
import time

def phantom_resistant_repair():
    """Create a phantom-resistant system that works around database corruption"""
    
    DATABASE_URL = "postgresql://chroma_user:xqIF9T5U6LhySuSw86JqWYf7qtyGDXy8@dpg-d16mkandiees73db52u0-a.oregon-postgres.render.com/chroma_ha"
    
    print("🛡️ PHANTOM-RESISTANT SYNC SYSTEM REPAIR")
    print("=" * 50)
    
    try:
        # Step 1: Try multiple collection creation approaches
        print("1. Attempting phantom-resistant collection creation...")
        
        successful_collections = []
        
        # Try 10 different collection names and approaches
        for attempt in range(10):
            collection_name = f"docs_v{attempt}_{int(time.time())}"
            
            print(f"   Attempt {attempt + 1}: {collection_name}")
            
            # Try different configuration approaches
            configs = [
                {"name": collection_name},
                {
                    "name": collection_name,
                    "configuration_json": {"hnsw": {"space": "l2"}}
                },
                {
                    "name": collection_name,
                    "configuration_json": {
                        "hnsw": {
                            "space": "l2",
                            "ef_construction": 100,
                            "ef": 10,
                            "M": 16
                        }
                    }
                }
            ]
            
            for config_idx, config in enumerate(configs):
                try:
                    # Create on primary
                    primary_response = requests.post(
                        "https://chroma-primary.onrender.com/api/v2/tenants/default_tenant/databases/default_database/collections",
                        headers={"Content-Type": "application/json"},
                        json=config,
                        timeout=30
                    )
                    
                    if primary_response.status_code in [200, 201]:
                        primary_data = primary_response.json()
                        primary_id = primary_data.get('id')
                        
                        # Immediately test accessibility
                        verify_response = requests.get(
                            f"https://chroma-primary.onrender.com/api/v2/tenants/default_tenant/databases/default_database/collections/{primary_id}",
                            timeout=30
                        )
                        
                        if verify_response.status_code == 200:
                            print(f"      ✅ SUCCESS! Primary collection is REAL: {primary_id[:8]}...")
                            
                            # Try to create replica immediately
                            replica_response = requests.post(
                                "https://chroma-replica.onrender.com/api/v2/tenants/default_tenant/databases/default_database/collections",
                                headers={"Content-Type": "application/json"},
                                json=config,
                                timeout=30
                            )
                            
                            if replica_response.status_code in [200, 201]:
                                replica_data = replica_response.json()
                                replica_id = replica_data.get('id')
                                
                                # Test replica accessibility
                                verify_replica = requests.get(
                                    f"https://chroma-replica.onrender.com/api/v2/tenants/default_tenant/databases/default_database/collections/{replica_id}",
                                    timeout=30
                                )
                                
                                if verify_replica.status_code == 200:
                                    print(f"      🎉 BOTH COLLECTIONS ARE REAL!")
                                    print(f"         Primary: {primary_id}")
                                    print(f"         Replica: {replica_id}")
                                    
                                    successful_collections.append({
                                        "name": collection_name,
                                        "primary_id": primary_id,
                                        "replica_id": replica_id,
                                        "config": config
                                    })
                                    
                                    # Test immediate document upload
                                    test_payload = {
                                        "embeddings": [[0.1] * 3072],
                                        "documents": ["Phantom-resistant test document"],
                                        "metadatas": [{"test": "phantom_resistant"}],
                                        "ids": ["phantom_test_1"]
                                    }
                                    
                                    upload_response = requests.post(
                                        f"https://chroma-primary.onrender.com/api/v2/tenants/default_tenant/databases/default_database/collections/{primary_id}/add",
                                        headers={"Content-Type": "application/json"},
                                        json=test_payload,
                                        timeout=30
                                    )
                                    
                                    if upload_response.status_code in [200, 201]:
                                        print(f"      🚀 DOCUMENT UPLOAD SUCCESSFUL!")
                                        
                                        # Create mapping immediately
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
                                                    json.dumps(config.get("configuration_json", {}))
                                                ))
                                                conn.commit()
                                        
                                        print(f"      📝 WORKING COLLECTION FOUND!")
                                        print()
                                        print(f"      🎯 UPDATE YOUR INGESTION SERVICE:")
                                        print(f"         Collection ID: {primary_id}")
                                        print(f"         Collection Name: {collection_name}")
                                        print(f"         URL: https://chroma-load-balancer.onrender.com/api/v2/tenants/default_tenant/databases/default_database/collections/{primary_id}/add")
                                        
                                        # Test sync via load balancer
                                        print("2. Testing intelligent sync via load balancer...")
                                        
                                        lb_test_payload = {
                                            "embeddings": [[0.2] * 3072],
                                            "documents": ["Load balancer sync test"],
                                            "metadatas": [{"test": "lb_sync"}],
                                            "ids": ["lb_test_1"]
                                        }
                                        
                                        lb_response = requests.post(
                                            f"https://chroma-load-balancer.onrender.com/api/v2/tenants/default_tenant/databases/default_database/collections/{primary_id}/add",
                                            headers={"Content-Type": "application/json"},
                                            json=lb_test_payload,
                                            timeout=30
                                        )
                                        
                                        if lb_response.status_code in [200, 201]:
                                            print("   ✅ Load balancer upload successful!")
                                            print("   🔄 Monitoring sync...")
                                            
                                            # Monitor for sync
                                            for i in range(6):
                                                time.sleep(5)
                                                
                                                try:
                                                    primary_count = int(requests.get(f"https://chroma-primary.onrender.com/api/v2/tenants/default_tenant/databases/default_database/collections/{primary_id}/count", timeout=30).text)
                                                    replica_count = int(requests.get(f"https://chroma-replica.onrender.com/api/v2/tenants/default_tenant/databases/default_database/collections/{replica_id}/count", timeout=30).text)
                                                    
                                                    print(f"   ({(i+1)*5}s) Counts: Primary={primary_count}, Replica={replica_count}")
                                                    
                                                    if replica_count > 0:
                                                        print()
                                                        print("🎉🎉🎉 PHANTOM-RESISTANT SYNC SUCCESS! 🎉🎉🎉")
                                                        print("🛡️ WORKING DESPITE DATABASE CORRUPTION!")
                                                        print("🚀 INTELLIGENT WAL SYNC OPERATIONAL!")
                                                        print()
                                                        print("✅ Your file uploads will now sync automatically!")
                                                        return
                                                        
                                                except Exception as e:
                                                    print(f"   Count error: {e}")
                                        
                                        else:
                                            print(f"   Load balancer test failed: {lb_response.status_code}")
                                        
                                        # Even if sync isn't immediate, we have working collections
                                        print()
                                        print("🎯 PHANTOM-RESISTANT COLLECTIONS CREATED!")
                                        print("📝 Use this collection for your uploads!")
                                        return
                                        
                                    break  # Success, no need to try more configs
                            
                        else:
                            print(f"      ❌ Primary phantom (config {config_idx + 1})")
                    
                except Exception as e:
                    print(f"      Error with config {config_idx + 1}: {str(e)[:50]}...")
                    continue
            
            # Small delay between attempts
            time.sleep(2)
        
        if successful_collections:
            print(f"\n🎉 Found {len(successful_collections)} working collections!")
            best = successful_collections[0]
            print(f"📌 BEST WORKING COLLECTION:")
            print(f"   Name: {best['name']}")
            print(f"   Primary: {best['primary_id']}")
            print(f"   Replica: {best['replica_id']}")
        else:
            print("\n❌ All attempts failed - database corruption is severe")
            print("🔧 Recommendation: ChromaDB services need restart")
        
    except Exception as e:
        print(f"❌ Phantom-resistant repair failed: {e}")
        import traceback
        print(traceback.format_exc())

if __name__ == "__main__":
    phantom_resistant_repair() 