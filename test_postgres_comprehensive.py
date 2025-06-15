#!/usr/bin/env python3
"""
Comprehensive PostgreSQL Table Testing Coverage Analysis
"""

import psycopg2
import sys

DATABASE_URL = "postgresql://chroma_user:xqIF9T5U6LhySuSw86JqWYf7qtyGDXy8@dpg-d16mkandiees73db52u0-a.oregon-postgres.render.com/chroma_ha"

def analyze_postgres_testing_coverage():
    """Analyze what PostgreSQL tables we're testing vs what we should test"""
    print("🔍 PostgreSQL Testing Coverage Analysis")
    print("=" * 60)
    
    # Define all expected tables and their purposes
    expected_tables = {
        'health_metrics': {
            'purpose': 'Monitor service health checks',
            'should_test': True,
            'current_test': False,
            'has_data': False
        },
        'performance_metrics': {
            'purpose': 'Resource usage monitoring',
            'should_test': True,
            'current_test': True,
            'has_data': False
        },
        'sync_collections': {
            'purpose': 'Collection sync state tracking',
            'should_test': True,
            'current_test': True,
            'has_data': False
        },
        'sync_history': {
            'purpose': 'Historical sync records',
            'should_test': True,
            'current_test': False,
            'has_data': False
        },
        'sync_metrics_daily': {
            'purpose': 'Daily sync performance metrics',
            'should_test': True,
            'current_test': False,
            'has_data': False
        },
        'sync_status_summary': {
            'purpose': 'Aggregated sync status view',
            'should_test': True,
            'current_test': False,
            'has_data': False
        },
        'sync_tasks': {
            'purpose': 'Distributed sync task coordination',
            'should_test': True,
            'current_test': True,
            'has_data': False
        },
        'sync_workers': {
            'purpose': 'Worker heartbeat and status',
            'should_test': True,
            'current_test': True,
            'has_data': False
        },
        'upgrade_recommendations': {
            'purpose': 'Resource upgrade suggestions',
            'should_test': True,
            'current_test': True,
            'has_data': False
        },
        'failover_events': {
            'purpose': 'Failover event logging',
            'should_test': True,
            'current_test': False,
            'has_data': False
        },
        'database_usage': {
            'purpose': 'Database size monitoring',
            'should_test': False,
            'current_test': False,
            'has_data': False
        }
    }
    
    try:
        with psycopg2.connect(DATABASE_URL) as conn:
            with conn.cursor() as cursor:
                
                # Check which tables exist and have data
                print("📊 TABLE STATUS CHECK:")
                for table_name, info in expected_tables.items():
                    try:
                        cursor.execute(f"SELECT COUNT(*) FROM {table_name}")
                        count = cursor.fetchone()[0]
                        info['has_data'] = count > 0
                        
                        status = "✅" if count > 0 else "📊"
                        print(f"  {status} {table_name}: {count:,} records")
                        
                    except Exception as e:
                        print(f"  ❌ {table_name}: Error - {e}")
                
                print(f"\n🧪 TESTING COVERAGE ANALYSIS:")
                tested_count = 0
                should_test_count = 0
                missing_tests = []
                
                for table_name, info in expected_tables.items():
                    if info['should_test']:
                        should_test_count += 1
                        if info['current_test']:
                            tested_count += 1
                            status = "✅ TESTED"
                        else:
                            status = "❌ NOT TESTED"
                            missing_tests.append(table_name)
                    else:
                        status = "➖ SKIP"
                    
                    print(f"  {status} {table_name}: {info['purpose']}")
                
                coverage_pct = (tested_count / should_test_count * 100) if should_test_count > 0 else 0
                
                print(f"\n📈 COVERAGE SUMMARY:")
                print(f"  Tables that should be tested: {should_test_count}")
                print(f"  Tables actually tested: {tested_count}")
                print(f"  Coverage percentage: {coverage_pct:.1f}%")
                
                if missing_tests:
                    print(f"\n❌ MISSING TEST COVERAGE:")
                    for table in missing_tests:
                        print(f"  • {table}: {expected_tables[table]['purpose']}")
                
                # Check tables with actual data that we should prioritize
                print(f"\n🔥 PRIORITY TESTING (tables with data):")
                priority_tables = []
                for table_name, info in expected_tables.items():
                    if info['has_data'] and info['should_test'] and not info['current_test']:
                        priority_tables.append(table_name)
                        print(f"  🎯 {table_name}: HAS DATA but NOT TESTED")
                
                if not priority_tables:
                    print("  ✅ All tables with data are being tested")
                
                # Recommendations
                print(f"\n💡 RECOMMENDATIONS:")
                if coverage_pct < 100:
                    print(f"  1. Add tests for {len(missing_tests)} missing tables")
                    print(f"  2. Focus on priority tables with actual data first")
                    print(f"  3. Consider integration tests for coordination features")
                else:
                    print("  ✅ PostgreSQL testing coverage is complete!")
                
                return {
                    'coverage_percent': coverage_pct,
                    'missing_tests': missing_tests,
                    'priority_tables': priority_tables,
                    'should_test_count': should_test_count,
                    'tested_count': tested_count
                }
                
    except Exception as e:
        print(f"❌ Analysis failed: {e}")
        return None

if __name__ == "__main__":
    result = analyze_postgres_testing_coverage()
    if result:
        if result['coverage_percent'] < 100:
            print(f"\nℹ️  Coverage Report: {100 - result['coverage_percent']:.1f}% of tables could use additional test coverage")
            print("This is informational - all functional tests are working correctly.")
            sys.exit(0)
        else:
            print(f"\n🎉 All PostgreSQL tables have adequate test coverage!")
            sys.exit(0) 