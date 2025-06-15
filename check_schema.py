#!/usr/bin/env python3
"""
Check PostgreSQL database schema and data
"""

import psycopg2

DATABASE_URL = "postgresql://chroma_user:xqIF9T5U6LhySuSw86JqWYf7qtyGDXy8@dpg-d16mkandiees73db52u0-a.oregon-postgres.render.com/chroma_ha"

def check_database_schema():
    """Check actual table schemas and data"""
    print("🗄️  Checking PostgreSQL Database Schema & Data")
    print("=" * 60)
    
    try:
        with psycopg2.connect(DATABASE_URL) as conn:
            with conn.cursor() as cursor:
                
                # Get all tables
                cursor.execute("""
                    SELECT table_name 
                    FROM information_schema.tables 
                    WHERE table_schema = 'public' 
                    ORDER BY table_name
                """)
                tables = [row[0] for row in cursor.fetchall()]
                
                for table in tables:
                    print(f"\n📋 TABLE: {table}")
                    
                    # Get column info
                    cursor.execute("""
                        SELECT column_name, data_type 
                        FROM information_schema.columns 
                        WHERE table_name = %s 
                        ORDER BY ordinal_position
                    """, [table])
                    columns = cursor.fetchall()
                    
                    print("   Columns:")
                    for col_name, col_type in columns:
                        print(f"     • {col_name} ({col_type})")
                    
                    # Get row count
                    cursor.execute(f"SELECT COUNT(*) FROM {table}")
                    count = cursor.fetchone()[0]
                    print(f"   Rows: {count}")
                    
                    # Show sample data if any exists
                    if count > 0:
                        cursor.execute(f"SELECT * FROM {table} LIMIT 3")
                        rows = cursor.fetchall()
                        if rows:
                            print("   Sample data:")
                            for i, row in enumerate(rows[:2]):
                                print(f"     Row {i+1}: {row}")
                
                print(f"\n📊 SUMMARY: {len(tables)} tables found")
                
    except Exception as e:
        print(f"❌ Database check failed: {e}")

if __name__ == "__main__":
    check_database_schema() 