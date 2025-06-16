#!/usr/bin/env python3

import psycopg2
import json

def fix_global_mapping():
    # Correct current collection IDs
    PRIMARY_ID = "f36b253b-c27d-44e7-b031-66abda933a09"
    REPLICA_ID = "faf2d734-7174-402e-a789-56c4ceeffcd0"
    
    try:
        conn = psycopg2.connect('postgresql://chroma_user:xqIF9T5U6LhySuSw86JqWYf7qtyGDXy8@dpg-d16mkandiees73db52u0-a.oregon-postgres.render.com/chroma_ha')
        cur = conn.cursor()
        
        print("🔧 Updating global collection mapping...")
        
        # Update mapping
        cur.execute("""
            INSERT INTO collection_id_mapping 
            (collection_name, primary_collection_id, replica_collection_id, collection_config)
            VALUES (%s, %s, %s, %s)
            ON CONFLICT (collection_name) 
            DO UPDATE SET 
                primary_collection_id = EXCLUDED.primary_collection_id,
                replica_collection_id = EXCLUDED.replica_collection_id,
                updated_at = NOW()
        """, ("global", PRIMARY_ID, REPLICA_ID, '{}'))
        
        conn.commit()
        print("✅ Collection mapping updated successfully!")
        
        # Verify
        cur.execute("SELECT primary_collection_id, replica_collection_id FROM collection_id_mapping WHERE collection_name = 'global'")
        result = cur.fetchone()
        print(f"📊 Updated mapping: Primary={result[0]}, Replica={result[1]}")
        
        cur.close()
        conn.close()
        return True
        
    except Exception as e:
        print(f"❌ Error: {e}")
        return False

if __name__ == "__main__":
    fix_global_mapping() 