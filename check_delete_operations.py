#!/usr/bin/env python3

import psycopg2
import os
from urllib.parse import urlparse

def check_delete_operations():
    """Check recent DELETE operations in WAL database"""
    try:
        # Parse database URL from environment
        result = urlparse(os.environ.get('DATABASE_URL', ''))
        
        if not result.scheme:
            print('❌ DATABASE_URL not set')
            return
        
        conn = psycopg2.connect(
            database=result.path[1:],
            user=result.username,
            password=result.password,
            host=result.hostname,
            port=result.port
        )

        with conn.cursor() as cur:
            print('🔍 Recent DELETE operations in WAL (last 15):')
            print('=' * 70)
            
            cur.execute('''
                SELECT id, method, path, status, created_at, retry_count, error_message, target_instance
                FROM unified_wal_writes 
                WHERE method = 'DELETE' 
                ORDER BY created_at DESC 
                LIMIT 15
            ''')
            
            delete_ops = cur.fetchall()
            
            if not delete_ops:
                print('❌ No DELETE operations found in WAL!')
                return
            
            for i, op in enumerate(delete_ops):
                id_val, method, path, status, created_at, retry_count, error_msg, target_instance = op
                print(f'{i+1}. {id_val[:8]} | {method} | {status} | Target: {target_instance}')
                print(f'   Time: {created_at} | Retries: {retry_count}')
                print(f'   Path: {path[:70]}')
                if error_msg:
                    print(f'   Error: {error_msg[:100]}')
                print()
            
            # Summary
            failed_deletes = sum(1 for op in delete_ops if op[3] == 'failed')
            successful_deletes = sum(1 for op in delete_ops if op[3] in ['synced', 'executed'])
            
            print(f'📊 DELETE Operation Summary:')
            print(f'   Total recent DELETEs: {len(delete_ops)}')
            print(f'   Failed: {failed_deletes}')
            print(f'   Successful: {successful_deletes}')

        conn.close()
        
    except Exception as e:
        print(f'❌ Error checking DELETE operations: {e}')

if __name__ == '__main__':
    check_delete_operations() 