#!/usr/bin/env python3
import psycopg2

conn = psycopg2.connect('postgresql://chroma_user:xqIF9T5U6LhySuSw86JqWYf7qtyGDXy8@dpg-d16mkandiees73db52u0-a.oregon-postgres.render.com/chroma_ha')
cur = conn.cursor()

# Check which tables have data
tables = [
    'collection_id_mapping', 'collection_mappings', 'database_usage', 'failover_events',
    'health_metrics', 'instance_sync_state', 'performance_metrics', 'replication_log',
    'sync_collections', 'sync_history', 'sync_metrics_daily', 'sync_status_summary',
    'sync_tasks', 'sync_workers', 'unified_wal_writes', 'upgrade_recommendations',
    'wal_pending_writes', 'wal_performance_metrics'
]

print('📊 POSTGRESQL TABLE ANALYSIS:')
print('=' * 50)
active_tables = []
empty_tables = []
error_tables = []

for table in tables:
    try:
        cur.execute(f'SELECT COUNT(*) FROM {table}')
        count = cur.fetchone()[0]
        if count > 0:
            active_tables.append((table, count))
            print(f'✅ {table}: {count} records')
        else:
            empty_tables.append(table)
            print(f'➖ {table}: 0 records')
    except Exception as e:
        error_tables.append((table, str(e)))
        print(f'❌ {table}: ERROR - {str(e)[:50]}...')

print(f'\n📈 SUMMARY:')
print(f'   Active tables (with data): {len(active_tables)}')
print(f'   Empty tables: {len(empty_tables)}')
print(f'   Error/Missing tables: {len(error_tables)}')

# Check recent activity in active tables
print(f'\n🕐 RECENT ACTIVITY CHECK:')
for table, count in active_tables:
    try:
        if table == 'unified_wal_writes':
            cur.execute(f"SELECT MAX(created_at) FROM {table}")
            last_activity = cur.fetchone()[0]
            print(f'   {table}: Last activity {last_activity}')
        elif table == 'collection_id_mapping':
            cur.execute(f"SELECT MAX(updated_at) FROM {table}")
            last_activity = cur.fetchone()[0]
            print(f'   {table}: Last updated {last_activity}')
        elif table == 'wal_performance_metrics':
            cur.execute(f"SELECT MAX(metric_timestamp) FROM {table}")
            last_activity = cur.fetchone()[0]
            print(f'   {table}: Last metric {last_activity}')
    except Exception as e:
        print(f'   {table}: Cannot check timestamp - {str(e)[:30]}...')

cur.close()
conn.close() 