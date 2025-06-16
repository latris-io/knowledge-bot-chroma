#!/usr/bin/env python3
import psycopg2
from datetime import datetime

def check_pending_status():
    try:
        conn = psycopg2.connect('postgresql://chroma_user:xqIF9T5U6LhySuSw86JqWYf7qtyGDXy8@dpg-d16mkandiees73db52u0-a.oregon-postgres.render.com/chroma_ha')
        cur = conn.cursor()
        
        print("🔍 DETAILED WAL STATUS CHECK")
        print("=" * 60)
        
        # Check all status counts
        cur.execute('SELECT status, COUNT(*) FROM unified_wal_writes GROUP BY status ORDER BY COUNT(*) DESC')
        status_counts = cur.fetchall()
        
        print("📊 STATUS DISTRIBUTION:")
        total = 0
        for status, count in status_counts:
            print(f"   {status}: {count}")
            total += count
        print(f"   TOTAL: {total}")
        print()
        
        # Check specifically for pending entries
        cur.execute('SELECT COUNT(*) FROM unified_wal_writes WHERE status = %s', ('pending',))
        pending_count = cur.fetchone()[0]
        
        print(f"🔄 PENDING ENTRIES: {pending_count}")
        
        if pending_count > 0:
            print("✅ Found pending entries - should be processed by sync")
            
            # Show recent pending entries
            cur.execute('''
                SELECT write_id, method, path, target_instance, retry_count, created_at, updated_at
                FROM unified_wal_writes 
                WHERE status = 'pending'
                ORDER BY updated_at DESC 
                LIMIT 5
            ''')
            
            print("\n📋 RECENT PENDING ENTRIES:")
            for row in cur.fetchall():
                write_id, method, path, target, retry_count, created, updated = row
                short_path = path[:40] + "..." if len(path) > 40 else path
                print(f"   {write_id[:8]} | {method} → {target} | R:{retry_count}")
                print(f"      Path: {short_path}")
                print(f"      Updated: {updated}")
        else:
            print("❌ No pending entries found")
            
            # Check what the cleanup actually did
            print("\n🔧 CHECKING CLEANUP RESULTS:")
            cur.execute('''
                SELECT status, COUNT(*), MAX(updated_at)
                FROM unified_wal_writes 
                WHERE updated_at > NOW() - INTERVAL '30 minutes'
                GROUP BY status
            ''')
            
            recent_updates = cur.fetchall()
            if recent_updates:
                print("   Recent updates (last 30 min):")
                for status, count, max_updated in recent_updates:
                    print(f"      {status}: {count} entries (last: {max_updated})")
            else:
                print("   No recent updates found")
        
        print()
        
        # Check sync-related fields
        cur.execute('''
            SELECT 
                COUNT(*) as total,
                COUNT(*) FILTER (WHERE status = 'pending') as pending,
                COUNT(*) FILTER (WHERE status = 'failed') as failed,
                COUNT(*) FILTER (WHERE status = 'synced') as synced,
                COUNT(*) FILTER (WHERE retry_count > 0) as retried
            FROM unified_wal_writes
        ''')
        
        stats = cur.fetchone()
        total, pending, failed, synced, retried = stats
        
        print("📈 SYNC ANALYSIS:")
        print(f"   Total entries: {total}")
        print(f"   Pending: {pending}")
        print(f"   Failed: {failed}")
        print(f"   Synced: {synced}")
        print(f"   Retried (retry_count > 0): {retried}")
        
        success_rate = (synced / total * 100) if total > 0 else 0
        print(f"   Success rate: {success_rate:.1f}%")
        
        conn.close()
        
    except Exception as e:
        print(f'❌ Database error: {e}')

if __name__ == "__main__":
    check_pending_status() 