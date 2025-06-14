#!/usr/bin/env python3
"""
Database and Log Cleanup Service
Automated cleanup of PostgreSQL data with configurable retention policies
"""

import os
import time
import logging
import psycopg2
from datetime import datetime, timedelta

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class DatabaseCleanupService:
    def __init__(self):
        self.database_url = os.getenv("DATABASE_URL")
        
        # Retention policies (days) - configurable via environment variables
        self.retention_policies = {
            'health_metrics': int(os.getenv("HEALTH_METRICS_RETENTION_DAYS", "7")),
            'performance_metrics': int(os.getenv("PERFORMANCE_METRICS_RETENTION_DAYS", "30")), 
            'sync_history': int(os.getenv("SYNC_HISTORY_RETENTION_DAYS", "90")),
            'failover_events': int(os.getenv("FAILOVER_EVENTS_RETENTION_DAYS", "180")),
            'sync_tasks': int(os.getenv("SYNC_TASKS_RETENTION_DAYS", "30")),
            'upgrade_recommendations': int(os.getenv("UPGRADE_RECOMMENDATIONS_RETENTION_DAYS", "365")),
            'sync_workers': int(os.getenv("SYNC_WORKERS_RETENTION_DAYS", "7")),
        }
        
        logger.info(f"🧹 Cleanup Service initialized with retention policies: {self.retention_policies}")
    
    def cleanup_table(self, table_name, retention_days):
        """Clean up old records from a table"""
        if not self.database_url:
            logger.warning(f"No DATABASE_URL - skipping {table_name}")
            return {'deleted': 0, 'error': 'No database connection'}
        
        date_columns = {
            'health_metrics': 'checked_at',
            'performance_metrics': 'metric_timestamp', 
            'sync_history': 'sync_started_at',
            'failover_events': 'occurred_at',
            'sync_tasks': 'created_at',
            'sync_workers': 'last_heartbeat',
            'upgrade_recommendations': 'created_at'
        }
        
        date_column = date_columns.get(table_name, 'created_at')
        cutoff_date = datetime.now() - timedelta(days=retention_days)
        
        try:
            with psycopg2.connect(self.database_url) as conn:
                with conn.cursor() as cursor:
                    # Count records to delete
                    cursor.execute(f"SELECT COUNT(*) FROM {table_name} WHERE {date_column} < %s", [cutoff_date])
                    count_to_delete = cursor.fetchone()[0]
                    
                    if count_to_delete == 0:
                        logger.info(f"✅ {table_name}: No old records to clean")
                        return {'deleted': 0, 'error': None}
                    
                    # Delete old records
                    cursor.execute(f"DELETE FROM {table_name} WHERE {date_column} < %s", [cutoff_date])
                    deleted_count = cursor.rowcount
                    conn.commit()
                    
                    # Get remaining count
                    cursor.execute(f"SELECT COUNT(*) FROM {table_name}")
                    remaining = cursor.fetchone()[0]
                    
                    logger.info(f"🗑️ {table_name}: Deleted {deleted_count:,} old records, {remaining:,} remaining")
                    return {'deleted': deleted_count, 'remaining': remaining, 'error': None}
                    
        except Exception as e:
            logger.error(f"❌ Failed to cleanup {table_name}: {e}")
            return {'deleted': 0, 'error': str(e)}
    
    def run_cleanup(self):
        """Run cleanup for all tables"""
        logger.info("🚀 Starting database cleanup cycle")
        
        total_deleted = 0
        results = {}
        
        for table_name, retention_days in self.retention_policies.items():
            result = self.cleanup_table(table_name, retention_days)
            results[table_name] = result
            total_deleted += result['deleted']
        
        # Run VACUUM to reclaim space
        if self.database_url and total_deleted > 0:
            try:
                with psycopg2.connect(self.database_url) as conn:
                    conn.autocommit = True
                    with conn.cursor() as cursor:
                        for table_name in self.retention_policies.keys():
                            try:
                                cursor.execute(f"VACUUM ANALYZE {table_name}")
                                logger.info(f"✅ Optimized {table_name}")
                            except Exception as e:
                                logger.warning(f"⚠️ Failed to optimize {table_name}: {e}")
            except Exception as e:
                logger.error(f"❌ Database optimization failed: {e}")
        
        logger.info(f"✅ Cleanup complete: {total_deleted:,} total records deleted")
        return {'total_deleted': total_deleted, 'results': results}
    
    def get_size_report(self):
        """Get database size report"""
        if not self.database_url:
            return {'error': 'No database connection'}
        
        try:
            with psycopg2.connect(self.database_url) as conn:
                with conn.cursor() as cursor:
                    tables = []
                    for table_name in self.retention_policies.keys():
                        try:
                            cursor.execute(f"SELECT COUNT(*) FROM {table_name}")
                            record_count = cursor.fetchone()[0]
                            
                            cursor.execute(f"SELECT pg_size_pretty(pg_total_relation_size('{table_name}'))")
                            size = cursor.fetchone()[0]
                            
                            tables.append({
                                'name': table_name,
                                'records': record_count,
                                'size': size,
                                'retention_days': self.retention_policies[table_name]
                            })
                        except Exception as e:
                            logger.warning(f"Failed to get size for {table_name}: {e}")
                    
                    return {'tables': tables, 'timestamp': datetime.now().isoformat()}
        except Exception as e:
            return {'error': str(e)}

def main():
    import argparse
    
    parser = argparse.ArgumentParser(description="Database Cleanup Service")
    parser.add_argument("--run", action="store_true", help="Run cleanup once")
    parser.add_argument("--report", action="store_true", help="Show size report")
    
    args = parser.parse_args()
    
    # Set DATABASE_URL if not provided
    if not os.getenv("DATABASE_URL"):
        os.environ["DATABASE_URL"] = "postgresql://chroma_user:xqIF9T5U6LhySuSw86JqWYf7qtyGDXy8@dpg-d16mkandiees73db52u0-a.oregon-postgres.render.com/chroma_ha"
    
    service = DatabaseCleanupService()
    
    if args.report:
        report = service.get_size_report()
        if 'error' not in report:
            print(f"📊 Database Size Report")
            for table in report['tables']:
                print(f"  {table['name']}: {table['records']:,} records, {table['size']}, {table['retention_days']} day retention")
        else:
            print(f"❌ Error: {report['error']}")
    
    elif args.run:
        service.run_cleanup()
    
    else:
        parser.print_help()

if __name__ == "__main__":
    main() 