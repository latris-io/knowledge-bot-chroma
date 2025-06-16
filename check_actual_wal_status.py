#!/usr/bin/env python3

import os
import psycopg2
from collections import Counter

def check_wal_status():
    """Check actual WAL entry statuses in database"""
    try:
        database_url = os.getenv('DATABASE_URL')
        if not database_url:
            print("❌ DATABASE_URL not found")
            return
            
        with psycopg2.connect(database_url) as conn:
            with conn.cursor() as cur:
                # Get status distribution
                cur.execute("""
                    SELECT status, COUNT(*) 
                    FROM unified_wal_writes 
                    GROUP BY status 
                    ORDER BY COUNT(*) DESC
                """)
                
                print("📊 ACTUAL DATABASE STATUS DISTRIBUTION:")
                print("=" * 50)
                
                total = 0
                for status, count in cur.fetchall():
                    print(f"   {status}: {count}")
                    total += count
                
                print(f"   TOTAL: {total}")
                print()
                
                # Get recent entries by status
                cur.execute("""
                    SELECT write_id, method, path, status, target_instance, retry_count, 
                           created_at, updated_at, error_message
                    FROM unified_wal_writes 
                    ORDER BY updated_at DESC 
                    LIMIT 10
                """)
                
                print("📋 RECENT WAL ENTRIES (last 10):")
                print("=" * 50)
                
                for row in cur.fetchall():
                    write_id, method, path, status, target, retry_count, created, updated, error = row
                    short_path = path[:50] + "..." if len(path) > 50 else path
                    print(f"   {write_id[:8]} | {method} → {target} | {status} | R:{retry_count}")
                    if error:
                        print(f"      Error: {error[:100]}...")
                print()
                
                # Check pending entries specifically
                cur.execute("""
                    SELECT COUNT(*) FROM unified_wal_writes 
                    WHERE status = 'pending'
                """)
                pending_count = cur.fetchone()[0]
                
                print(f"🔄 PENDING ENTRIES: {pending_count}")
                
                if pending_count > 0:
                    print("✅ Pending entries found - sync should process them")
                else:
                    print("❌ No pending entries - cleanup may not have worked")
                    
    except Exception as e:
        print(f"❌ Database error: {e}")

if __name__ == "__main__":
    check_wal_status() 