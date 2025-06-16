#!/usr/bin/env python3
"""
PostgreSQL Database Cleanup Script
=================================

This script cleans up all stale data from PostgreSQL when starting fresh
with empty ChromaDB instances. It preserves table structures but clears
all data that references deleted collections.

⚠️  WARNING: This will clear all historical data and mappings!
✅  Safe to run: Preserves table structures and system functionality
"""

import psycopg2
import sys

def cleanup_postgresql():
    """Clean up all stale data from PostgreSQL database."""
    
    connection_string = 'postgresql://chroma_user:xqIF9T5U6LhySuSw86JqWYf7qtyGDXy8@dpg-d16mkandiees73db52u0-a.oregon-postgres.render.com/chroma_ha'
    
    try:
        print("🧹 POSTGRESQL CLEANUP - Starting fresh database cleanup...")
        print("=" * 60)
        
        conn = psycopg2.connect(connection_string)
        cur = conn.cursor()
        
        # 1. Check current state
        print("\n📊 BEFORE CLEANUP:")
        
        tables_to_check = [
            ('collection_id_mapping', 'Collection mappings'),
            ('unified_wal_writes', 'WAL entries'),
            ('collection_mappings', 'Legacy collection mappings'),
            ('sync_history', 'Sync history'),
            ('performance_metrics', 'Performance metrics'),
            ('health_metrics', 'Health metrics'),
            ('failover_events', 'Failover events'),
            ('replication_log', 'Replication log')
        ]
        
        for table, description in tables_to_check:
            try:
                cur.execute(f'SELECT COUNT(*) FROM {table}')
                count = cur.fetchone()[0]
                print(f"   {description}: {count}")
            except Exception as e:
                print(f"   {description}: Table not found or error")
        
        # 2. Clean up collection-related data
        print(f"\n🗑️  CLEANING UP COLLECTION DATA:")
        
        cleanup_commands = [
            # Primary collection mappings
            ("DELETE FROM collection_id_mapping", "Collection ID mappings"),
            ("DELETE FROM collection_mappings", "Legacy collection mappings"),
            
            # WAL system cleanup
            ("DELETE FROM unified_wal_writes", "All WAL entries"),
            ("DELETE FROM wal_pending_writes", "Pending WAL writes"),
            ("DELETE FROM wal_performance_metrics", "WAL performance metrics"),
            
            # Sync system cleanup  
            ("DELETE FROM sync_history", "Sync history"),
            ("DELETE FROM sync_status_summary", "Sync status summaries"),
            ("DELETE FROM sync_tasks", "Sync tasks"),
            ("DELETE FROM sync_collections", "Sync collections"),
            ("DELETE FROM instance_sync_state", "Instance sync state"),
            
            # Monitoring cleanup
            ("DELETE FROM performance_metrics", "Performance metrics"),
            ("DELETE FROM health_metrics", "Health metrics"),
            ("DELETE FROM failover_events", "Failover events"),
            ("DELETE FROM replication_log", "Replication log"),
            ("DELETE FROM sync_metrics_daily", "Daily sync metrics"),
            
            # Reset sequences/counters if they exist
            ("DELETE FROM database_usage", "Database usage tracking"),
        ]
        
        cleaned_tables = []
        for command, description in cleanup_commands:
            try:
                cur.execute(command)
                rows_affected = cur.rowcount
                if rows_affected > 0:
                    print(f"   ✅ {description}: {rows_affected} records deleted")
                    cleaned_tables.append(description)
                else:
                    print(f"   ➖ {description}: Already empty")
            except Exception as e:
                print(f"   ⚠️  {description}: {str(e)}")
        
        # 3. Commit changes
        conn.commit()
        print(f"\n✅ CLEANUP COMPLETED!")
        print(f"   📊 Tables cleaned: {len(cleaned_tables)}")
        print(f"   🔄 Database ready for fresh start")
        
        # 4. Verify cleanup
        print(f"\n📊 AFTER CLEANUP:")
        for table, description in tables_to_check:
            try:
                cur.execute(f'SELECT COUNT(*) FROM {table}')
                count = cur.fetchone()[0]
                status = "✅" if count == 0 else "⚠️"
                print(f"   {status} {description}: {count}")
            except Exception as e:
                print(f"   ➖ {description}: Table not found")
        
        cur.close()
        conn.close()
        
        print(f"\n🎉 POSTGRESQL CLEANUP SUCCESSFUL!")
        print(f"   Your database is now clean and ready for fresh ChromaDB collections.")
        print(f"   The load balancer will automatically create new mappings as needed.")
        
        return True
        
    except Exception as e:
        print(f"\n❌ CLEANUP FAILED: {str(e)}")
        print(f"   Please check your database connection and try again.")
        return False

if __name__ == "__main__":
    print("PostgreSQL Cleanup Script")
    print("=" * 30)
    
    response = input("\n⚠️  This will delete ALL historical data from PostgreSQL.\n   Continue? (yes/no): ")
    
    if response.lower() in ['yes', 'y']:
        success = cleanup_postgresql()
        sys.exit(0 if success else 1)
    else:
        print("\n❌ Cleanup cancelled by user.")
        sys.exit(1) 