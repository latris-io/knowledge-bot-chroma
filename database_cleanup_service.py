#!/usr/bin/env python3
"""
Database and Log Cleanup Service
Automated cleanup of PostgreSQL data and log files with configurable retention policies
"""

import os
import time
import logging
import psycopg2
import schedule
from datetime import datetime, timedelta
from typing import Dict, List
import glob
import shutil

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class DatabaseCleanupService:
    """Automated cleanup service for PostgreSQL data and system logs"""
    
    def __init__(self):
        self.database_url = os.getenv("DATABASE_URL")
        
        # Configurable retention policies (days)
        self.retention_policies = {
            # High-frequency monitoring data (short retention)
            'health_metrics': int(os.getenv("HEALTH_METRICS_RETENTION_DAYS", "7")),
            'performance_metrics': int(os.getenv("PERFORMANCE_METRICS_RETENTION_DAYS", "30")),
            
            # Medium-frequency operational data
            'sync_history': int(os.getenv("SYNC_HISTORY_RETENTION_DAYS", "90")),
            'failover_events': int(os.getenv("FAILOVER_EVENTS_RETENTION_DAYS", "180")),
            'sync_tasks': int(os.getenv("SYNC_TASKS_RETENTION_DAYS", "30")),
            
            # Low-frequency strategic data (longer retention)
            'upgrade_recommendations': int(os.getenv("UPGRADE_RECOMMENDATIONS_RETENTION_DAYS", "365")),
            'sync_metrics_daily': int(os.getenv("DAILY_METRICS_RETENTION_DAYS", "365")),
            
            # Worker tracking (medium retention)
            'sync_workers': int(os.getenv("SYNC_WORKERS_RETENTION_DAYS", "7")),  # Only keep recent heartbeats
        }
        
        # Log file cleanup settings
        self.log_retention_days = int(os.getenv("LOG_RETENTION_DAYS", "14"))
        self.max_log_size_mb = int(os.getenv("MAX_LOG_SIZE_MB", "100"))
        
        # Cleanup schedule
        self.cleanup_interval_hours = int(os.getenv("CLEANUP_INTERVAL_HOURS", "6"))
        
        logger.info("🧹 Database Cleanup Service initialized")
        logger.info(f"📊 Retention policies: {self.retention_policies}")
        logger.info(f"📝 Log retention: {self.log_retention_days} days")
        logger.info(f"⏰ Cleanup interval: {self.cleanup_interval_hours} hours")
    
    def cleanup_database_table(self, table_name: str, retention_days: int, date_column: str = None) -> Dict:
        """Clean up old records from a specific table"""
        if not self.database_url:
            logger.warning(f"⚠️ No DATABASE_URL - skipping {table_name} cleanup")
            return {'deleted': 0, 'error': 'No database connection'}
        
        # Determine the date column to use for cleanup
        date_columns = {
            'health_metrics': 'checked_at',
            'performance_metrics': 'metric_timestamp',
            'sync_history': 'sync_started_at',
            'failover_events': 'occurred_at',
            'sync_tasks': 'created_at',
            'sync_workers': 'last_heartbeat',
            'upgrade_recommendations': 'created_at',
            'sync_metrics_daily': 'created_at'
        }
        
        if not date_column:
            date_column = date_columns.get(table_name, 'created_at')
        
        cutoff_date = datetime.now() - timedelta(days=retention_days)
        
        try:
            with psycopg2.connect(self.database_url) as conn:
                with conn.cursor() as cursor:
                    # Count records to be deleted
                    cursor.execute(f"""
                        SELECT COUNT(*) FROM {table_name} 
                        WHERE {date_column} < %s
                    """, [cutoff_date])
                    
                    count_to_delete = cursor.fetchone()[0]
                    
                    if count_to_delete == 0:
                        logger.info(f"✅ {table_name}: No old records to clean up")
                        return {'deleted': 0, 'error': None}
                    
                    # Delete old records
                    cursor.execute(f"""
                        DELETE FROM {table_name} 
                        WHERE {date_column} < %s
                    """, [cutoff_date])
                    
                    deleted_count = cursor.rowcount
                    conn.commit()
                    
                    logger.info(f"🗑️ {table_name}: Deleted {deleted_count:,} records older than {retention_days} days")
                    
                    # Get remaining record count
                    cursor.execute(f"SELECT COUNT(*) FROM {table_name}")
                    remaining_count = cursor.fetchone()[0]
                    
                    logger.info(f"📊 {table_name}: {remaining_count:,} records remaining")
                    
                    return {
                        'deleted': deleted_count,
                        'remaining': remaining_count,
                        'retention_days': retention_days,
                        'cutoff_date': cutoff_date.isoformat(),
                        'error': None
                    }
                    
        except Exception as e:
            logger.error(f"❌ Failed to cleanup {table_name}: {e}")
            return {'deleted': 0, 'error': str(e)}
    
    def cleanup_all_tables(self) -> Dict:
        """Clean up all tables according to retention policies"""
        logger.info("🧹 Starting database cleanup cycle")
        
        cleanup_results = {
            'timestamp': datetime.now().isoformat(),
            'tables_cleaned': 0,
            'total_deleted': 0,
            'results': {},
            'errors': []
        }
        
        for table_name, retention_days in self.retention_policies.items():
            logger.info(f"🔄 Cleaning {table_name} (retention: {retention_days} days)")
            
            result = self.cleanup_database_table(table_name, retention_days)
            cleanup_results['results'][table_name] = result
            
            if result['error']:
                cleanup_results['errors'].append(f"{table_name}: {result['error']}")
            else:
                cleanup_results['tables_cleaned'] += 1
                cleanup_results['total_deleted'] += result['deleted']
        
        logger.info(f"✅ Database cleanup complete: {cleanup_results['total_deleted']:,} records deleted from {cleanup_results['tables_cleaned']} tables")
        
        if cleanup_results['errors']:
            logger.warning(f"⚠️ Cleanup errors: {len(cleanup_results['errors'])}")
            for error in cleanup_results['errors']:
                logger.warning(f"  - {error}")
        
        return cleanup_results
    
    def optimize_database(self):
        """Run database optimization after cleanup"""
        if not self.database_url:
            logger.warning("⚠️ No DATABASE_URL - skipping database optimization")
            return
        
        logger.info("🔧 Running database optimization")
        
        try:
            with psycopg2.connect(self.database_url) as conn:
                conn.autocommit = True
                with conn.cursor() as cursor:
                    # Vacuum analyze to reclaim space and update statistics
                    for table_name in self.retention_policies.keys():
                        try:
                            cursor.execute(f"VACUUM ANALYZE {table_name}")
                            logger.info(f"✅ Optimized {table_name}")
                        except Exception as e:
                            logger.warning(f"⚠️ Failed to optimize {table_name}: {e}")
                    
                    # Update database usage statistics
                    try:
                        cursor.execute("""
                            INSERT INTO database_usage (schemaname, tablename, size, size_bytes)
                            SELECT 
                                schemaname,
                                tablename,
                                pg_size_pretty(pg_total_relation_size(schemaname||'.'||tablename)) as size,
                                pg_total_relation_size(schemaname||'.'||tablename) as size_bytes
                            FROM pg_tables 
                            WHERE schemaname = 'public'
                            ON CONFLICT (schemaname, tablename) DO UPDATE SET
                                size = EXCLUDED.size,
                                size_bytes = EXCLUDED.size_bytes
                        """)
                        logger.info("📊 Updated database usage statistics")
                    except Exception as e:
                        logger.warning(f"⚠️ Failed to update usage stats: {e}")
                        
        except Exception as e:
            logger.error(f"❌ Database optimization failed: {e}")
    
    def cleanup_log_files(self) -> Dict:
        """Clean up old log files"""
        logger.info("📝 Starting log file cleanup")
        
        cleanup_results = {
            'files_deleted': 0,
            'space_freed_mb': 0,
            'errors': []
        }
        
        # Common log file locations and patterns
        log_patterns = [
            "/var/log/*.log",
            "/tmp/*.log",
            "*.log",
            "/app/logs/*.log",
            "./logs/*.log",
            "/opt/render/project/logs/*.log"
        ]
        
        cutoff_date = datetime.now() - timedelta(days=self.log_retention_days)
        cutoff_timestamp = cutoff_date.timestamp()
        
        for pattern in log_patterns:
            try:
                for log_file in glob.glob(pattern):
                    try:
                        # Check file age
                        file_stat = os.stat(log_file)
                        if file_stat.st_mtime < cutoff_timestamp:
                            file_size_mb = file_stat.st_size / (1024 * 1024)
                            os.remove(log_file)
                            cleanup_results['files_deleted'] += 1
                            cleanup_results['space_freed_mb'] += file_size_mb
                            logger.info(f"🗑️ Deleted old log file: {log_file} ({file_size_mb:.1f}MB)")
                        
                        # Check file size (even if recent, remove if too large)
                        elif file_stat.st_size > (self.max_log_size_mb * 1024 * 1024):
                            file_size_mb = file_stat.st_size / (1024 * 1024)
                            
                            # Truncate instead of delete for recent large files
                            with open(log_file, 'w') as f:
                                f.write(f"# Log truncated by cleanup service at {datetime.now()}\n")
                            
                            cleanup_results['space_freed_mb'] += file_size_mb
                            logger.info(f"✂️ Truncated large log file: {log_file} ({file_size_mb:.1f}MB)")
                    
                    except Exception as e:
                        cleanup_results['errors'].append(f"Error processing {log_file}: {str(e)}")
            
            except Exception as e:
                cleanup_results['errors'].append(f"Error with pattern {pattern}: {str(e)}")
        
        logger.info(f"✅ Log cleanup complete: {cleanup_results['files_deleted']} files deleted, {cleanup_results['space_freed_mb']:.1f}MB freed")
        
        if cleanup_results['errors']:
            logger.warning(f"⚠️ Log cleanup errors: {len(cleanup_results['errors'])}")
            for error in cleanup_results['errors'][:5]:  # Show only first 5 errors
                logger.warning(f"  - {error}")
        
        return cleanup_results
    
    def get_database_size_report(self) -> Dict:
        """Get current database size and usage report"""
        if not self.database_url:
            return {'error': 'No database connection'}
        
        try:
            with psycopg2.connect(self.database_url) as conn:
                with conn.cursor() as cursor:
                    # Get table sizes
                    cursor.execute("""
                        SELECT 
                            tablename,
                            pg_size_pretty(pg_total_relation_size('public.'||tablename)) as size,
                            pg_total_relation_size('public.'||tablename) as size_bytes,
                            (SELECT COUNT(*) FROM information_schema.tables WHERE table_name = tablename) as record_count
                        FROM pg_tables 
                        WHERE schemaname = 'public'
                        ORDER BY pg_total_relation_size('public.'||tablename) DESC
                    """)
                    
                    tables = []
                    total_size_bytes = 0
                    
                    for row in cursor.fetchall():
                        table_name, size_pretty, size_bytes, _ = row
                        
                        # Get actual record count
                        try:
                            cursor.execute(f"SELECT COUNT(*) FROM {table_name}")
                            record_count = cursor.fetchone()[0]
                        except:
                            record_count = 0
                        
                        tables.append({
                            'name': table_name,
                            'size': size_pretty,
                            'size_bytes': size_bytes,
                            'records': record_count
                        })
                        total_size_bytes += size_bytes
                    
                    return {
                        'total_size_mb': total_size_bytes / (1024 * 1024),
                        'total_size_pretty': f"{total_size_bytes / (1024 * 1024):.1f}MB",
                        'tables': tables,
                        'timestamp': datetime.now().isoformat()
                    }
                    
        except Exception as e:
            logger.error(f"❌ Failed to get database size report: {e}")
            return {'error': str(e)}
    
    def run_cleanup_cycle(self):
        """Run a complete cleanup cycle"""
        logger.info("🚀 Starting automated cleanup cycle")
        
        start_time = time.time()
        
        # 1. Database cleanup
        db_results = self.cleanup_all_tables()
        
        # 2. Database optimization
        self.optimize_database()
        
        # 3. Log file cleanup
        log_results = self.cleanup_log_files()
        
        # 4. Generate size report
        size_report = self.get_database_size_report()
        
        duration = time.time() - start_time
        
        # Summary report
        logger.info("📊 CLEANUP CYCLE SUMMARY")
        logger.info(f"  Duration: {duration:.1f}s")
        logger.info(f"  Database records deleted: {db_results['total_deleted']:,}")
        logger.info(f"  Log files deleted: {log_results['files_deleted']}")
        logger.info(f"  Disk space freed: {log_results['space_freed_mb']:.1f}MB")
        
        if size_report.get('total_size_pretty'):
            logger.info(f"  Current database size: {size_report['total_size_pretty']}")
        
        logger.info("✅ Cleanup cycle complete")
        
        return {
            'database': db_results,
            'logs': log_results,
            'size_report': size_report,
            'duration': duration
        }
    
    def start_scheduled_cleanup(self):
        """Start the scheduled cleanup service"""
        logger.info(f"⏰ Starting scheduled cleanup service (every {self.cleanup_interval_hours} hours)")
        
        # Schedule cleanup to run every N hours
        schedule.every(self.cleanup_interval_hours).hours.do(self.run_cleanup_cycle)
        
        # Run initial cleanup
        self.run_cleanup_cycle()
        
        # Keep service running
        while True:
            schedule.run_pending()
            time.sleep(60)  # Check every minute

def main():
    """Main function to run cleanup service"""
    import argparse
    
    parser = argparse.ArgumentParser(description="Database and Log Cleanup Service")
    parser.add_argument("--once", action="store_true", help="Run cleanup once and exit")
    parser.add_argument("--report", action="store_true", help="Show size report only")
    parser.add_argument("--schedule", action="store_true", help="Run as scheduled service")
    
    args = parser.parse_args()
    
    service = DatabaseCleanupService()
    
    if args.report:
        # Just show the size report
        report = service.get_database_size_report()
        if 'error' not in report:
            print(f"📊 Database Size Report ({report['timestamp']})")
            print(f"Total Size: {report['total_size_pretty']}")
            print("\nTable Breakdown:")
            for table in report['tables']:
                print(f"  {table['name']}: {table['size']} ({table['records']:,} records)")
        else:
            print(f"❌ Error: {report['error']}")
    
    elif args.once:
        # Run cleanup once
        service.run_cleanup_cycle()
    
    elif args.schedule:
        # Run as scheduled service
        service.start_scheduled_cleanup()
    
    else:
        # Show help
        parser.print_help()

if __name__ == "__main__":
    main() 