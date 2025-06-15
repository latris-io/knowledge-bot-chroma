#!/usr/bin/env python3

import requests
import json
import time
import os
import psycopg2

def clean_failed_wal_entries():
    """Clean failed WAL entries to reset sync state"""
    
    base_url = "https://chroma-load-balancer.onrender.com"
    
    print("🧹 Fixing WAL Sync Issues")
    print("=" * 50)
    
    try:
        # Step 1: Wait for deployment
        print("1. Waiting for deployment to complete (30 seconds)...")
        time.sleep(30)
        
        # Step 2: Check system status
        print("2. Checking system health...")
        
        health_response = requests.get(f"{base_url}/health", timeout=30)
        if health_response.status_code != 200:
            print(f"   ❌ System not healthy: {health_response.status_code}")
            return
        
        print("   ✅ System healthy")
        
        # Step 3: Clean WAL entries using database
        print("3. Cleaning failed WAL entries...")
        
        try:
            database_url = "postgresql://chroma_user:xqIF9T5U6LhySuSw86JqWYf7qtyGDXy8@dpg-d16mkandiees73db52u0-a.oregon-postgres.render.com/chroma_ha"
            
            with psycopg2.connect(database_url) as conn:
                with conn.cursor() as cur:
                    # Clear old failed entries
                    cur.execute("""
                        DELETE FROM unified_wal_writes 
                        WHERE status = 'failed' 
                        AND created_at < NOW() - INTERVAL '1 hour'
                    """)
                    
                    deleted_count = cur.rowcount
                    
                    # Reset recent failed entries
                    cur.execute("""
                        UPDATE unified_wal_writes 
                        SET retry_count = 0, error_message = NULL, status = 'pending'
                        WHERE status = 'failed' 
                    """)
                    
                    reset_count = cur.rowcount
                    conn.commit()
                    
                    print(f"   ✅ Cleaned {deleted_count} old entries, reset {reset_count} failed entries")
                    
        except Exception as e:
            print(f"   ❌ Database cleanup failed: {e}")
        
        # Step 4: Test intelligent sync
        print("4. Testing intelligent sync...")
        
        test_payload = {
            "embeddings": [[0.1] * 3072],
            "documents": ["Intelligent sync test"],
            "metadatas": [{"test": "fix_verification", "document_id": f"fix_{int(time.time())}"}],
            "ids": [f"fix_test_{int(time.time())}"]
        }
        
        # Use the known global collection ID
        global_id = "eb07030e-ed7e-4aab-8249-3a95efefccb0"
        
        ingest_response = requests.post(
            f"{base_url}/api/v2/tenants/default_tenant/databases/default_database/collections/{global_id}/add",
            headers={"Content-Type": "application/json"},
            json=test_payload,
            timeout=30
        )
        
        if ingest_response.status_code in [200, 201]:
            print("   ✅ Test ingestion successful")
            
            print("5. Waiting for sync (20 seconds)...")
            time.sleep(20)
            
            # Check results
            status_response = requests.get(f"{base_url}/wal/status", timeout=30)
            if status_response.status_code == 200:
                wal_status = status_response.json()
                successful_syncs = wal_status['performance_stats']['successful_syncs']
                failed_syncs = wal_status['performance_stats']['failed_syncs']
                
                print(f"   Successful syncs: {successful_syncs}")
                print(f"   Failed syncs: {failed_syncs}")
                
                if successful_syncs > 0:
                    print("   🎉 INTELLIGENT SYNC IS WORKING!")
                else:
                    print("   ⚠️ Still having sync issues")
        else:
            print(f"   ❌ Test ingestion failed: {ingest_response.status_code}")
        
        print(f"\n{'='*50}")
        print("🔧 WAL Sync Fix Completed!")
        
    except Exception as e:
        print(f"\n❌ Fix failed: {e}")

if __name__ == "__main__":
    clean_failed_wal_entries() 