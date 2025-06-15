import psycopg2

DATABASE_URL = "postgresql://chroma_user:xqIF9T5U6LhySuSw86JqWYf7qtyGDXy8@dpg-d16mkandiees73db52u0-a.oregon-postgres.render.com/chroma_ha"

print("🔍 CHECKING LATEST SYNC ERROR")
print("=" * 50)

with psycopg2.connect(DATABASE_URL) as conn:
    with conn.cursor() as cur:
        cur.execute("SELECT path, error_message, updated_at FROM unified_wal_writes WHERE status = 'failed' ORDER BY updated_at DESC LIMIT 1")
        result = cur.fetchone()
        
        if result:
            path, error, updated_at = result
            print(f"Latest failed path: {path}")
            print(f"Latest error: {error}")
            print(f"Updated at: {updated_at}")
            
            # Check collection IDs
            replica_id = "5beb705b-7903-4f7e-8fc9-3a39ce3a2510"
            primary_id = "7b9ee675-09b3-4911-8b9b-8f04ca8f7809"
            
            print()
            print("COLLECTION ID ANALYSIS:")
            print(f"Path contains replica ID: {replica_id in path}")
            print(f"Path contains primary ID: {primary_id in path}")
            
            if replica_id in path:
                print("✅ Path uses correct replica ID")
                print("❌ Issue is NOT collection ID mapping")
                print("🔍 Different problem causing 400 error")
                
                # Check if it's a data format issue
                if "400 Client Error" in error:
                    print("💡 Likely a request format or data issue")
                    print("🔧 May need to check request body/headers")
            else:
                print("❌ Path still uses wrong collection ID")
                print("🔧 Collection ID mapping not working")
        else:
            print("No failed entries found") 