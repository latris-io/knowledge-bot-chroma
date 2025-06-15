#!/usr/bin/env python3
import psycopg2
import os
from datetime import datetime

DATABASE_URL = "postgresql://chroma_user:xqIF9T5U6LhySuSw86JqWYf7qtyGDXy8@dpg-d16mkandiees73db52u0-a.oregon-postgres.render.com/chroma_ha"

def test_database():
    try:
        with psycopg2.connect(DATABASE_URL) as conn:
            with conn.cursor() as cursor:
                print('🎉 PostgreSQL connected successfully!')
                
                # Check database schema
                cursor.execute("SELECT table_name FROM information_schema.tables WHERE table_schema = 'public' ORDER BY table_name;")
                tables = [row[0] for row in cursor.fetchall()]
                print(f'\n📋 Database tables ({len(tables)}):')
                for table in tables:
                    print(f'   • {table}')
                
                if not tables:
                    print('⚠️  No tables found - database schema needs initialization')
                    return
                
                # Check sync collections
                if 'sync_collections' in tables:
                    cursor.execute("SELECT COUNT(*) FROM sync_collections;")
                    count = cursor.fetchone()[0]
                    print(f'\n📊 Sync Collections: {count} tracked')
                    
                    if count > 0:
                        cursor.execute("SELECT collection_name, sync_status, last_successful_sync FROM sync_collections ORDER BY updated_at DESC LIMIT 5;")
                        collections = cursor.fetchall()
                        print('   Recent collections:')
                        for col in collections:
                            print(f'     • {col[0]} - Status: {col[1]} - Last sync: {col[2]}')
                
                # Check sync tasks
                if 'sync_tasks' in tables:
                    cursor.execute("SELECT COUNT(*) FROM sync_tasks;")
                    count = cursor.fetchone()[0]
                    print(f'\n📋 Sync Tasks: {count} total')
                    
                    if count > 0:
                        cursor.execute("SELECT task_status, COUNT(*) FROM sync_tasks GROUP BY task_status;")
                        statuses = cursor.fetchall()
                        print('   Task statuses:')
                        for status in statuses:
                            print(f'     • {status[0]}: {status[1]} tasks')
                
                # Check workers
                if 'sync_workers' in tables:
                    cursor.execute("SELECT COUNT(*) FROM sync_workers WHERE worker_status = 'active';")
                    count = cursor.fetchone()[0]
                    print(f'\n👷 Active Workers: {count}')
                    
                    if count > 0:
                        cursor.execute("SELECT worker_id, last_heartbeat FROM sync_workers WHERE worker_status = 'active' ORDER BY last_heartbeat DESC;")
                        workers = cursor.fetchall()
                        print('   Active workers:')
                        for worker in workers:
                            print(f'     • {worker[0]} - Last seen: {worker[1]}')
                
                # Check performance metrics
                if 'performance_metrics' in tables:
                    cursor.execute("SELECT COUNT(*) FROM performance_metrics WHERE metric_timestamp > NOW() - INTERVAL '24 hours';")
                    count = cursor.fetchone()[0]
                    print(f'\n📊 Performance Metrics (24h): {count} records')
                
                # Check upgrade recommendations
                if 'upgrade_recommendations' in tables:
                    cursor.execute("SELECT COUNT(*) FROM upgrade_recommendations WHERE created_at > NOW() - INTERVAL '7 days';")
                    count = cursor.fetchone()[0]
                    print(f'\n💡 Recent Upgrade Recommendations: {count}')
                    
                    if count > 0:
                        cursor.execute("SELECT recommendation_type, urgency, reason FROM upgrade_recommendations WHERE created_at > NOW() - INTERVAL '7 days' ORDER BY created_at DESC LIMIT 3;")
                        recs = cursor.fetchall()
                        print('   Recent recommendations:')
                        for rec in recs:
                            print(f'     • {rec[0]} ({rec[1]}): {rec[2]}')
                
    except Exception as e:
        print(f'❌ Database test failed: {e}')

if __name__ == "__main__":
    print("🗄️  Testing PostgreSQL Coordination Database")
    print("=" * 50)
    test_database() 