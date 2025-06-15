#!/usr/bin/env python3
import psycopg2

def check_tables():
    try:
        conn = psycopg2.connect('postgresql://chroma_user:xqIF9T5U6LhySuSw86JqWYf7qtyGDXy8@dpg-d16mkandiees73db52u0-a.oregon-postgres.render.com/chroma_ha')
        cur = conn.cursor()
        
        # Check what tables exist
        cur.execute("SELECT table_name FROM information_schema.tables WHERE table_schema = 'public'")
        tables = cur.fetchall()
        
        print('📋 Existing tables in database:')
        for table in tables:
            print(f'  • {table[0]}')
        
        # If no tables, check if we need to initialize the schema
        if not tables:
            print('\n⚠️  No tables found! WAL schema needs initialization.')
        
        conn.close()
        
    except Exception as e:
        print(f'❌ Database error: {e}')

if __name__ == "__main__":
    check_tables() 