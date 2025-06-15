#!/usr/bin/env python3
import psycopg2
from datetime import datetime

def check_unified_wal_status():
    try:
        conn = psycopg2.connect('postgresql://chroma_user:xqIF9T5U6LhySuSw86JqWYf7qtyGDXy8@dpg-d16mkandiees73db52u0-a.oregon-postgres.render.com/chroma_ha')
        cur = conn.cursor()
        
        # Check total WAL entries
        cur.execute('SELECT COUNT(*) FROM unified_wal_writes')
        total_count = cur.fetchone()[0]
        print(f'📊 Total WAL entries: {total_count}')
        
        # Check by status
        cur.execute('SELECT status, COUNT(*) FROM unified_wal_writes GROUP BY status')
        status_counts = cur.fetchall()
        print(f'\n📈 Status breakdown:')
        for status, count in status_counts:
            status_emoji = {'pending': '⏳', 'executed': '✅', 'failed': '❌', 'synced': '🔄'}.get(status, '📋')
            print(f'   {status_emoji} {status}: {count}')
        
        # Check recent entries
        cur.execute('''
            SELECT write_id, method, target_instance, status, created_at, retry_count, conversion_type
            FROM unified_wal_writes 
            ORDER BY created_at DESC 
            LIMIT 10
        ''')
        
        entries = cur.fetchall()
        print(f'\n📋 Recent WAL entries:')
        for entry in entries:
            write_id, method, target, status, created, retries, conversion = entry
            status_emoji = {'pending': '⏳', 'executed': '✅', 'failed': '❌', 'synced': '🔄'}.get(status, '📋')
            conversion_str = f' (Conv: {conversion})' if conversion else ''
            print(f'   {status_emoji} {write_id[:8]} | {method} → {target} | R:{retries}{conversion_str}')
        
        # Check for issues
        cur.execute('SELECT COUNT(*) FROM unified_wal_writes WHERE status = %s', ('pending',))
        pending = cur.fetchone()[0]
        
        cur.execute('SELECT COUNT(*) FROM unified_wal_writes WHERE status = %s', ('failed',))
        failed = cur.fetchone()[0]
        
        cur.execute('SELECT COUNT(*) FROM unified_wal_writes WHERE conversion_type IS NOT NULL')
        conversions = cur.fetchone()[0]
        
        print(f'\n🚨 Health Check:')
        if pending > 0:
            print(f'   ⚠️  {pending} pending writes (processing delay)')
        if failed > 0:
            print(f'   ❌ {failed} failed writes (need attention)')
        if conversions > 0:
            print(f'   🔄 {conversions} deletion conversions (working correctly)')
        
        if pending == 0 and failed == 0:
            print(f'   ✅ WAL system healthy - no pending or failed writes')
        
        conn.close()
        
    except Exception as e:
        print(f'❌ Database error: {e}')

if __name__ == "__main__":
    check_unified_wal_status() 