#!/usr/bin/env python3

import psycopg2
import json

def check_failed_wal_entries():
    """Check details of recent failed WAL entries"""
    try:
        conn = psycopg2.connect(
            "postgresql://chroma_user:chroma_password@dpg-ctu71klds78s73e47cag-a.oregon-postgres.render.com:5432/chroma_db?sslmode=require"
        )
        cur = conn.cursor()
        
        print("🔍 CHECKING FAILED WAL ENTRY DETAILS")
        print("=" * 50)
        
        # Get recent failed entries with details
        cur.execute("""
            SELECT write_id, method, path, error_message, status, collection_id, timestamp
            FROM unified_wal_writes 
            WHERE status = 'failed' 
            ORDER BY timestamp DESC 
            LIMIT 10
        """)
        
        failed_entries = cur.fetchall()
        print(f"📊 Found {len(failed_entries)} recent failed entries:")
        
        for i, entry in enumerate(failed_entries, 1):
            write_id, method, path, error_msg, status, collection_id, timestamp = entry
            
            print(f"\n{i}. WAL Entry {write_id[:8]}...")
            print(f"   Method: {method}")
            print(f"   Path: {path[:100]}...")
            print(f"   Collection ID: {collection_id}")
            print(f"   Status: {status}")
            print(f"   Time: {timestamp}")
            if error_msg:
                print(f"   Error: {error_msg[:150]}...")
        
        # Check collection mapping
        print(f"\n🔍 CURRENT COLLECTION MAPPING:")
        cur.execute("SELECT collection_name, primary_collection_id, replica_collection_id FROM collection_id_mapping")
        mappings = cur.fetchall()
        
        for mapping in mappings:
            name, primary_id, replica_id = mapping
            print(f"   {name}: {primary_id[:8]}... ↔ {replica_id[:8]}...")
        
        conn.close()
        
    except Exception as e:
        print(f"❌ Error checking failed WAL entries: {e}")

if __name__ == "__main__":
    check_failed_wal_entries() 