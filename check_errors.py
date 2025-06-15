import psycopg2

DATABASE_URL = "postgresql://chroma_user:xqIF9T5U6LhySuSw86JqWYf7qtyGDXy8@dpg-d16mkandiees73db52u0-a.oregon-postgres.render.com/chroma_ha"

print("🔍 Checking WAL Error Details")
print("=" * 50)

try:
    with psycopg2.connect(DATABASE_URL) as conn:
        with conn.cursor() as cur:
            # Get recent failed entries with error details
            cur.execute("""
                SELECT write_id, path, error_message, retry_count, data, headers
                FROM unified_wal_writes 
                WHERE status = 'failed' 
                ORDER BY created_at DESC 
                LIMIT 5
            """)
            
            failed_entries = cur.fetchall()
            print(f"Recent failed entries: {len(failed_entries)}")
            print()
            
            for i, (write_id, path, error_msg, retry_count, data, headers) in enumerate(failed_entries, 1):
                print(f"{i}. WAL Entry {write_id[:8]}...")
                print(f"   Path: {path}")
                print(f"   Error: {error_msg}")
                print(f"   Retries: {retry_count}")
                
                # Show data size and method info
                data_size = len(data) if data else 0
                print(f"   Data size: {data_size} bytes")
                
                if headers:
                    import json
                    try:
                        headers_dict = json.loads(headers) if isinstance(headers, str) else headers
                        print(f"   Headers: {list(headers_dict.keys())}")
                    except:
                        print(f"   Headers: [parsing error]")
                
                print()
            
            # Check collection mappings
            print("Collection Mappings:")
            cur.execute("SELECT collection_name, primary_collection_id, replica_collection_id FROM collection_id_mapping")
            mappings = cur.fetchall()
            
            for name, primary_id, replica_id in mappings:
                print(f"   {name}: {primary_id[:8]}... ↔ {replica_id[:8]}...")
            
            if not mappings:
                print("   No mappings found!")
                
except Exception as e:
    print(f"❌ Error: {e}")
    import traceback
    print(traceback.format_exc()) 