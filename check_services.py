#!/usr/bin/env python3
"""
Check PostgreSQL database for activity from deployed services
"""

import os
import psycopg2
from datetime import datetime

DATABASE_URL = "postgresql://chroma_user:xqIF9T5U6LhySuSw86JqWYf7qtyGDXy8@dpg-d16mkandiees73db52u0-a.oregon-postgres.render.com/chroma_ha"

def check_service_activity():
    """Check if monitoring and sync services are active"""
    print("🔍 Checking Service Activity in PostgreSQL")
    print("=" * 50)
    
    try:
        with psycopg2.connect(DATABASE_URL) as conn:
            with conn.cursor() as cursor:
                
                print("1. 📊 HEALTH METRICS:")
                cursor.execute("SELECT COUNT(*), MAX(timestamp) FROM health_metrics")
                count, latest = cursor.fetchone()
                print(f"   Records: {count}, Latest: {latest or 'None'}")
                
                print("\n2. 📈 PERFORMANCE METRICS:")
                cursor.execute("SELECT COUNT(*), MAX(metric_timestamp) FROM performance_metrics")
                count, latest = cursor.fetchone()
                print(f"   Records: {count}, Latest: {latest or 'None'}")
                
                print("\n3. 🔄 SYNC HISTORY:")
                cursor.execute("SELECT COUNT(*), MAX(sync_timestamp) FROM sync_history")
                count, latest = cursor.fetchone()
                print(f"   Records: {count}, Latest: {latest or 'None'}")
                
                print("\n4. 👷 SYNC WORKERS:")
                cursor.execute("SELECT COUNT(*), MAX(last_heartbeat) FROM sync_workers")
                count, latest = cursor.fetchone()
                print(f"   Workers: {count}, Last heartbeat: {latest or 'None'}")
                
                print("\n5. 📋 SYNC TASKS:")
                cursor.execute("SELECT COUNT(*), task_status, MAX(created_at) FROM sync_tasks GROUP BY task_status")
                tasks = cursor.fetchall()
                if tasks:
                    for count, status, created in tasks:
                        print(f"   {status}: {count} tasks, latest: {created}")
                else:
                    print("   No tasks found")
                
                # Overall assessment
                cursor.execute("""
                    SELECT 
                        (SELECT COUNT(*) FROM health_metrics WHERE timestamp > NOW() - INTERVAL '1 hour') as recent_health,
                        (SELECT COUNT(*) FROM performance_metrics WHERE metric_timestamp > NOW() - INTERVAL '1 hour') as recent_perf,
                        (SELECT COUNT(*) FROM sync_workers WHERE last_heartbeat > NOW() - INTERVAL '5 minutes') as active_workers
                """)
                
                recent_health, recent_perf, active_workers = cursor.fetchone()
                
                print(f"\n📊 RECENT ACTIVITY (last hour):")
                print(f"   Health checks: {recent_health}")
                print(f"   Performance metrics: {recent_perf}")
                print(f"   Active workers: {active_workers}")
                
                if recent_health + recent_perf + active_workers > 0:
                    print("\n✅ SERVICES ARE ACTIVE!")
                else:
                    print("\n❌ NO RECENT ACTIVITY - Services may be idle or stopped")
                
    except Exception as e:
        print(f"❌ Database check failed: {e}")

if __name__ == "__main__":
    check_service_activity() 