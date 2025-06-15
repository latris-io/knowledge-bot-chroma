#!/usr/bin/env python3
import psycopg2
import json
from datetime import datetime

def check_wal_status():
    try:
        conn = psycopg2.connect('postgresql://chroma_user:xqIF9T5U6LhySuSw86JqWYf7qtyGDXy8@dpg-d16mkandiees73db52u0-a.oregon-postgres.render.com/chroma_ha')
        cur = conn.cursor()
        
        # Check recent WAL entries
        cur.execute('SELECT COUNT(*) FROM unified_wal_writes')
        total_count = cur.fetchone()[0]
        print(f'Total WAL entries: {total_count}')
        
        # Check recent entries with details
        cur.execute('''
            SELECT write_id, method, target_instance, status, created_at, retry_count, conversion_type
            FROM unified_wal_writes 
            ORDER BY created_at DESC 
            LIMIT 15
        ''')
        
        entries = cur.fetchall()
        print(f'\nRecent WAL entries:')
        for entry in entries:
            print(f'ID: {entry[0][:8]}, Method: {entry[1]}, Target: {entry[2]}, Status: {entry[3]}, Time: {entry[4]}, Retries: {entry[5]}, Conversion: {entry[6]}')
        
        # Check specifically for deletions
        cur.execute('''
            SELECT COUNT(*) FROM unified_wal_writes 
            WHERE (method = 'DELETE' OR path LIKE '%delete') AND created_at > NOW() - INTERVAL '24 hours'
        ''')
        recent_deletions = cur.fetchone()[0]
        print(f'\nDeletions in last 24 hours: {recent_deletions}')
        
        # Check pending entries
        cur.execute('SELECT COUNT(*) FROM unified_wal_writes WHERE status = %s', ('pending',))
        pending = cur.fetchone()[0]
        print(f'Pending entries: {pending}')
        
        # Check failed entries
        cur.execute('SELECT COUNT(*) FROM unified_wal_writes WHERE status = %s', ('failed',))
        failed = cur.fetchone()[0]
        print(f'Failed entries: {failed}')
        
        # Check executed entries
        cur.execute('SELECT COUNT(*) FROM unified_wal_writes WHERE status = %s', ('executed',))
        executed = cur.fetchone()[0]
        print(f'Executed entries: {executed}')
        
        # Check if there are any conversion entries
        cur.execute('SELECT COUNT(*) FROM unified_wal_writes WHERE conversion_type IS NOT NULL')
        conversion_entries = cur.fetchone()[0]
        print(f'Entries with conversion: {conversion_entries}')
        
        # Status summary
        print(f'\n📊 WAL Status Summary:')
        print(f'   ✅ Total: {total_count}')
        print(f'   ⏳ Pending: {pending}')
        print(f'   ✅ Executed: {executed}')
        print(f'   ❌ Failed: {failed}')
        print(f'   🔄 Conversions: {conversion_entries}')
        
        if pending > 0:
            print(f'\n⚠️  WARNING: {pending} pending writes detected!')
        if failed > 0:
            print(f'\n❌ ERROR: {failed} failed writes detected!')
        
        conn.close()
        
    except Exception as e:
        print(f'Database error: {e}')

if __name__ == "__main__":
    check_wal_status() 