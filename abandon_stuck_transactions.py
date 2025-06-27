#!/usr/bin/env python3

"""
Manual script to abandon stuck transactions and clear WAL errors
to fix USE CASE 2 issues
"""

import os
import psycopg2
import json
from datetime import datetime

# Database connection - use Render's internal PostgreSQL URL
DATABASE_URL = os.getenv("DATABASE_URL", "postgres://knowledge_bot_chroma_postgresql_user:Kg6B6EvUx0qRxYqj8nHKmLAzF4S5Bvu3@dpg-ctslrm23esus73a3k7rg-a.oregon-postgres.render.com/knowledge_bot_chroma_postgresql")

print(f"🔗 Using database URL: {DATABASE_URL[:50]}...")

def fix_stuck_transactions():
    """Fix stuck transactions and WAL errors"""
    print("🔧 Fixing stuck transactions and WAL errors...")
    
    try:
        with psycopg2.connect(DATABASE_URL) as conn:
            with conn.cursor() as cur:
                # 1. Abandon stuck transactions in ATTEMPTING status
                print("1. Abandoning stuck ATTEMPTING transactions...")
                cur.execute("""
                    UPDATE emergency_transaction_log 
                    SET status = 'ABANDONED', 
                        failure_reason = 'Manual reset - stuck in ATTEMPTING status',
                        completed_at = NOW()
                    WHERE status = 'ATTEMPTING' 
                    AND attempted_at < NOW() - INTERVAL '30 minutes'
                """)
                attempting_abandoned = cur.rowcount
                print(f"   ✅ Abandoned {attempting_abandoned} stuck ATTEMPTING transactions")
                
                # 2. Clear failed WAL operations
                print("2. Clearing failed WAL operations...")
                cur.execute("""
                    UPDATE unified_wal_writes 
                    SET status = 'abandoned', 
                        error_message = 'Manual cleanup - failed operations cleared'
                    WHERE status = 'failed' 
                    AND retry_count >= 3
                """)
                wal_failed_cleared = cur.rowcount
                print(f"   ✅ Cleared {wal_failed_cleared} failed WAL operations")
                
                # 3. Clear stuck pending WAL operations
                print("3. Clearing stuck pending WAL operations...")
                cur.execute("""
                    UPDATE unified_wal_writes 
                    SET status = 'abandoned',
                        error_message = 'Manual cleanup - stuck pending operations cleared'
                    WHERE status IN ('executed', 'pending')
                    AND timestamp < NOW() - INTERVAL '2 hours'
                """)
                wal_pending_cleared = cur.rowcount
                print(f"   ✅ Cleared {wal_pending_cleared} stuck pending WAL operations")
                
                conn.commit()
                
                # 4. Get final status
                print("4. Getting final system status...")
                cur.execute("""
                    SELECT 
                        COUNT(*) FILTER (WHERE status IN ('FAILED', 'ATTEMPTING') AND retry_count < max_retries) as pending_recovery,
                        COUNT(*) FILTER (WHERE status = 'COMPLETED') as completed,
                        COUNT(*) FILTER (WHERE status = 'RECOVERED') as recovered,
                        COUNT(*) FILTER (WHERE status = 'ABANDONED') as abandoned,
                        COUNT(*) FILTER (WHERE status = 'ATTEMPTING') as attempting
                    FROM emergency_transaction_log
                """)
                result = cur.fetchone()
                
                print("📊 Final Transaction Safety Status:")
                print(f"   Pending Recovery: {result[0]}")
                print(f"   Completed: {result[1]}")
                print(f"   Recovered: {result[2]}")
                print(f"   Abandoned: {result[3]}")
                print(f"   Still Attempting: {result[4]}")
                
                # WAL status
                cur.execute("""
                    SELECT 
                        COUNT(*) FILTER (WHERE status = 'pending') as pending_writes,
                        COUNT(*) FILTER (WHERE status = 'failed') as failed_writes,
                        COUNT(*) FILTER (WHERE status = 'abandoned') as abandoned_writes
                    FROM unified_wal_writes
                """)
                wal_result = cur.fetchone()
                
                print("📊 Final WAL Status:")
                print(f"   Pending Writes: {wal_result[0]}")
                print(f"   Failed Writes: {wal_result[1]}")
                print(f"   Abandoned Writes: {wal_result[2]}")
                
                return {
                    "transactions_abandoned": attempting_abandoned,
                    "wal_failed_cleared": wal_failed_cleared,
                    "wal_pending_cleared": wal_pending_cleared,
                    "final_transaction_status": {
                        "pending_recovery": result[0],
                        "completed": result[1],
                        "recovered": result[2],
                        "abandoned": result[3],
                        "attempting": result[4]
                    },
                    "final_wal_status": {
                        "pending_writes": wal_result[0],
                        "failed_writes": wal_result[1],
                        "abandoned_writes": wal_result[2]
                    }
                }
                
    except Exception as e:
        print(f"❌ Error fixing stuck transactions: {e}")
        import traceback
        traceback.print_exc()
        return None

if __name__ == "__main__":
    print("🔧 Starting manual fix for stuck transactions and WAL errors...")
    result = fix_stuck_transactions()
    
    if result:
        print("\n✅ System cleanup completed successfully!")
        print("📄 Summary:")
        print(json.dumps(result, indent=2))
    else:
        print("\n❌ System cleanup failed!")
        exit(1) 