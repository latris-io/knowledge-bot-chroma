#!/usr/bin/env python3
"""
Transaction Safety Service
Prevents data loss during timing gaps by implementing:
1. Pre-execution transaction logging
2. Automatic transaction recovery 
3. Timing gap detection and handling
"""

import os
import time
import json
import uuid
import logging
import psycopg2
import psycopg2.extras
import threading
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass
from enum import Enum
import requests

logger = logging.getLogger(__name__)

class TransactionStatus(Enum):
    ATTEMPTING = "ATTEMPTING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    RECOVERED = "RECOVERED"
    ABANDONED = "ABANDONED"

class OperationType(Enum):
    FILE_UPLOAD = "file_upload"
    FILE_DELETE = "file_delete"
    COLLECTION_CREATE = "collection_create"
    COLLECTION_DELETE = "collection_delete"
    DOCUMENT_ADD = "document_add"
    DOCUMENT_UPDATE = "document_update"
    DOCUMENT_DELETE = "document_delete"
    QUERY = "query"

@dataclass
class Transaction:
    transaction_id: str
    client_session: str
    client_ip: str
    method: str
    path: str
    data: Optional[bytes]
    headers: Dict[str, str]
    status: TransactionStatus
    operation_type: OperationType
    target_instance: Optional[str] = None
    user_identifier: Optional[str] = None
    failure_reason: Optional[str] = None
    response_status: Optional[int] = None
    response_data: Optional[Dict] = None
    retry_count: int = 0
    max_retries: int = 3
    is_timing_gap_failure: bool = False
    created_at: Optional[datetime] = None
    attempted_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    next_retry_at: Optional[datetime] = None

class TransactionSafetyService:
    """Service to ensure zero data loss during timing gaps and infrastructure failures"""
    
    def __init__(self, database_url: str):
        self.database_url = database_url
        self.db_lock = threading.RLock()
        self.recovery_interval = 30  # Check for recovery every 30 seconds
        self.recovery_thread = None
        self.is_running = False
        
        # Initialize database schema
        self._initialize_schema()
        
        # Start recovery service
        self.start_recovery_service()
        
        logger.info("🛡️ Transaction Safety Service initialized")
    
    def _initialize_schema(self):
        """Initialize the transaction safety database schema"""
        try:
            with self.get_db_connection() as conn:
                with conn.cursor() as cur:
                    # Read and execute schema from file
                    schema_file = os.path.join(os.path.dirname(__file__), 'transaction_safety_schema.sql')
                    if os.path.exists(schema_file):
                        with open(schema_file, 'r') as f:
                            schema_sql = f.read()
                        cur.execute(schema_sql)
                        conn.commit()
                        logger.info("✅ Transaction safety schema initialized")
                    else:
                        logger.warning("⚠️ Schema file not found, creating basic table")
                        self._create_basic_schema(cur)
                        conn.commit()
        except Exception as e:
            logger.error(f"❌ Failed to initialize transaction safety schema: {e}")
            raise
    
    def _create_basic_schema(self, cursor):
        """Create basic schema if file not found"""
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS emergency_transaction_log (
                transaction_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                client_session VARCHAR(100),
                client_ip VARCHAR(45),
                method VARCHAR(10) NOT NULL,
                path TEXT NOT NULL,
                data JSONB,
                headers JSONB,
                status VARCHAR(20) DEFAULT 'ATTEMPTING' NOT NULL,
                failure_reason TEXT,
                response_status INTEGER,
                response_data JSONB,
                created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
                attempted_at TIMESTAMP WITH TIME ZONE,
                completed_at TIMESTAMP WITH TIME ZONE,
                retry_count INTEGER DEFAULT 0,
                max_retries INTEGER DEFAULT 3,
                next_retry_at TIMESTAMP WITH TIME ZONE,
                is_timing_gap_failure BOOLEAN DEFAULT FALSE,
                target_instance VARCHAR(20),
                operation_type VARCHAR(50),
                user_identifier VARCHAR(100)
            )
        """)
    
    def get_db_connection(self):
        """Get database connection"""
        return psycopg2.connect(self.database_url)
    
    def classify_operation_type(self, method: str, path: str) -> OperationType:
        """Classify the operation type based on method and path"""
        if 'collections' in path:
            if method == 'POST' and path.endswith('/collections'):
                return OperationType.COLLECTION_CREATE
            elif method == 'DELETE' and '/collections/' in path:
                return OperationType.COLLECTION_DELETE
            elif method == 'POST' and '/add' in path:
                return OperationType.DOCUMENT_ADD
            elif method == 'POST' and '/update' in path:
                return OperationType.DOCUMENT_UPDATE
            elif method == 'DELETE' and '/delete' in path:
                return OperationType.DOCUMENT_DELETE
            elif method == 'POST' and '/query' in path:
                return OperationType.QUERY
        
        # File operations (inferred from common CMS patterns)
        if method == 'POST' and ('upload' in path or 'file' in path):
            return OperationType.FILE_UPLOAD
        elif method == 'DELETE' and ('file' in path or 'document' in path):
            return OperationType.FILE_DELETE
        
        # Default to document add for unclassified POST operations
        if method == 'POST':
            return OperationType.DOCUMENT_ADD
        elif method == 'DELETE':
            return OperationType.DOCUMENT_DELETE
        
        return OperationType.QUERY
    
    def extract_client_info(self, headers: Dict[str, str], remote_addr: str = None) -> Tuple[str, str, str]:
        """Extract client session, IP, and user identifier from headers"""
        client_session = (
            headers.get('X-Session-ID', '') or 
            headers.get('Session-ID', '') or 
            headers.get('X-Request-ID', '') or 
            str(uuid.uuid4())[:8]
        )
        
        client_ip = (
            headers.get('X-Forwarded-For', '').split(',')[0].strip() or
            headers.get('X-Real-IP', '') or
            remote_addr or
            'unknown'
        )
        
        user_identifier = (
            headers.get('X-User-ID', '') or
            headers.get('Authorization', '').split()[-1][:8] if headers.get('Authorization') else '' or
            client_session
        )
        
        return client_session, client_ip, user_identifier
    
    def log_transaction_attempt(self, method: str, path: str, data: Optional[bytes], 
                               headers: Dict[str, str], remote_addr: str = None,
                               target_instance: str = None) -> str:
        """
        Log transaction attempt BEFORE execution to prevent loss during timing gaps
        Returns transaction_id for tracking
        """
        transaction_id = str(uuid.uuid4())
        client_session, client_ip, user_identifier = self.extract_client_info(headers, remote_addr)
        operation_type = self.classify_operation_type(method, path)
        
        # Convert data to JSON for storage
        json_data = None
        if data:
            try:
                if isinstance(data, bytes):
                    # Try to decode as JSON first
                    try:
                        json_data = json.loads(data.decode('utf-8'))
                    except:
                        # If not JSON, store as base64 for binary data
                        import base64
                        json_data = {"_binary_data": base64.b64encode(data).decode('utf-8')}
                else:
                    json_data = data
            except Exception as e:
                logger.warning(f"Failed to serialize transaction data: {e}")
                json_data = {"_error": "Failed to serialize data"}
        
        try:
            with self.db_lock:
                with self.get_db_connection() as conn:
                    with conn.cursor() as cur:
                        cur.execute("""
                            INSERT INTO emergency_transaction_log 
                            (transaction_id, client_session, client_ip, method, path, data, 
                             headers, status, operation_type, target_instance, user_identifier,
                             created_at, attempted_at)
                            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, NOW(), NOW())
                        """, (
                            transaction_id,
                            client_session,
                            client_ip,
                            method,
                            path,
                            json.dumps(json_data) if json_data else None,
                            json.dumps(dict(headers)),
                            TransactionStatus.ATTEMPTING.value,
                            operation_type.value,
                            target_instance,
                            user_identifier
                        ))
                        conn.commit()
            
            logger.info(f"📝 Transaction {transaction_id[:8]} logged: {method} {path}")
            return transaction_id
            
        except Exception as e:
            logger.error(f"❌ Failed to log transaction attempt: {e}")
            # Return a fallback transaction ID even if logging fails
            return transaction_id
    
    def mark_transaction_completed(self, transaction_id: str, response_status: int = 200, 
                                  response_data: Dict = None):
        """Mark transaction as completed successfully"""
        try:
            with self.db_lock:
                with self.get_db_connection() as conn:
                    with conn.cursor() as cur:
                        cur.execute("""
                            UPDATE emergency_transaction_log 
                            SET status = %s, completed_at = NOW(), response_status = %s, 
                                response_data = %s
                            WHERE transaction_id = %s
                        """, (
                            TransactionStatus.COMPLETED.value,
                            response_status,
                            json.dumps(response_data) if response_data else None,
                            transaction_id
                        ))
                        conn.commit()
            
            logger.debug(f"✅ Transaction {transaction_id[:8]} completed")
            
        except Exception as e:
            logger.error(f"❌ Failed to mark transaction completed: {e}")
    
    def mark_transaction_failed(self, transaction_id: str, failure_reason: str, 
                               is_timing_gap: bool = False, response_status: int = None):
        """Mark transaction as failed with retry scheduling"""
        try:
            with self.db_lock:
                with self.get_db_connection() as conn:
                    with conn.cursor() as cur:
                        cur.execute("""
                            UPDATE emergency_transaction_log 
                            SET status = %s, failure_reason = %s, retry_count = retry_count + 1,
                                is_timing_gap_failure = %s, response_status = %s
                            WHERE transaction_id = %s
                        """, (
                            TransactionStatus.FAILED.value,
                            failure_reason[:500],  # Limit error message length
                            is_timing_gap,
                            response_status,
                            transaction_id
                        ))
                        conn.commit()
            
            logger.warning(f"⚠️ Transaction {transaction_id[:8]} failed: {failure_reason[:100]}")
            
        except Exception as e:
            logger.error(f"❌ Failed to mark transaction failed: {e}")
    
    def get_pending_recovery_transactions(self) -> List[Dict]:
        """Get transactions that need recovery (failed but within retry limits)"""
        try:
            with self.get_db_connection() as conn:
                with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                    cur.execute("""
                        SELECT * FROM pending_recovery_transactions
                        LIMIT 100
                    """)
                    return [dict(row) for row in cur.fetchall()]
        except Exception as e:
            logger.error(f"❌ Failed to get pending recovery transactions: {e}")
            return []
    
    def retry_transaction(self, transaction: Dict, load_balancer) -> bool:
        """Retry a failed transaction"""
        try:
            transaction_id = transaction['transaction_id']
            method = transaction['method']
            path = transaction['path']
            
            # Reconstruct data
            data = None
            if transaction['data']:
                try:
                    json_data = json.loads(transaction['data'])
                    if '_binary_data' in json_data:
                        import base64
                        data = base64.b64decode(json_data['_binary_data'])
                    elif '_error' not in json_data:
                        data = json.dumps(json_data).encode('utf-8')
                except:
                    pass
            
            # Reconstruct headers
            headers = {}
            if transaction['headers']:
                try:
                    headers = json.loads(transaction['headers'])
                except:
                    pass
            
            logger.info(f"🔄 Retrying transaction {transaction_id[:8]}: {method} {path}")
            
            # Execute the operation via load balancer
            response = load_balancer.forward_request_with_recovery(
                method=method,
                path=path,
                headers=headers,
                data=data or b'',
                original_transaction_id=transaction_id
            )
            
            if response and response.status_code < 400:
                self.mark_transaction_recovered(transaction_id, response.status_code)
                logger.info(f"✅ Transaction {transaction_id[:8]} recovered successfully")
                return True
            else:
                self.mark_transaction_failed(
                    transaction_id, 
                    f"Retry failed with status {response.status_code if response else 'None'}"
                )
                return False
                
        except Exception as e:
            self.mark_transaction_failed(transaction_id, f"Retry exception: {str(e)}")
            logger.error(f"❌ Failed to retry transaction: {e}")
            return False
    
    def mark_transaction_recovered(self, transaction_id: str, response_status: int):
        """Mark transaction as successfully recovered"""
        try:
            with self.db_lock:
                with self.get_db_connection() as conn:
                    with conn.cursor() as cur:
                        cur.execute("""
                            UPDATE emergency_transaction_log 
                            SET status = %s, completed_at = NOW(), response_status = %s
                            WHERE transaction_id = %s
                        """, (
                            TransactionStatus.RECOVERED.value,
                            response_status,
                            transaction_id
                        ))
                        conn.commit()
        except Exception as e:
            logger.error(f"❌ Failed to mark transaction recovered: {e}")
    
    def abandon_transaction(self, transaction_id: str, reason: str):
        """Mark transaction as abandoned after max retries"""
        try:
            with self.db_lock:
                with self.get_db_connection() as conn:
                    with conn.cursor() as cur:
                        cur.execute("""
                            UPDATE emergency_transaction_log 
                            SET status = %s, failure_reason = %s
                            WHERE transaction_id = %s
                        """, (
                            TransactionStatus.ABANDONED.value,
                            reason,
                            transaction_id
                        ))
                        conn.commit()
            
            logger.error(f"❌ Transaction {transaction_id[:8]} abandoned: {reason}")
        except Exception as e:
            logger.error(f"❌ Failed to abandon transaction: {e}")
    
    def start_recovery_service(self):
        """Start the automatic recovery service"""
        if self.recovery_thread and self.recovery_thread.is_alive():
            return
        
        self.is_running = True
        self.recovery_thread = threading.Thread(target=self._recovery_loop, daemon=True)
        self.recovery_thread.start()
        logger.info("🚀 Transaction recovery service started")
    
    def stop_recovery_service(self):
        """Stop the automatic recovery service"""
        self.is_running = False
        if self.recovery_thread:
            self.recovery_thread.join(timeout=10)
        logger.info("🛑 Transaction recovery service stopped")
    
    def _recovery_loop(self):
        """Main recovery loop - runs in background thread"""
        while self.is_running:
            try:
                self.process_recovery_queue()
                time.sleep(self.recovery_interval)
            except Exception as e:
                logger.error(f"❌ Recovery loop error: {e}")
                time.sleep(60)  # Wait longer on error
    
    def process_recovery_queue(self, load_balancer=None):
        """Process the queue of failed transactions for recovery"""
        # Use injected load balancer reference if available
        if not load_balancer:
            load_balancer = getattr(self, 'load_balancer', None)
        
        if not load_balancer:
            # No load balancer available for recovery
            return
            
        pending = self.get_pending_recovery_transactions()
        if not pending:
            return
        
        logger.info(f"🔄 Processing {len(pending)} pending recovery transactions")
        
        recovered = 0
        failed = 0
        abandoned = 0
        
        for transaction in pending:
            transaction_id = transaction['transaction_id']
            
            # Check if max retries exceeded
            if transaction['retry_count'] >= transaction['max_retries']:
                self.abandon_transaction(
                    transaction_id,
                    f"Max retries ({transaction['max_retries']}) exceeded"
                )
                abandoned += 1
                continue
            
            # Check if we're past the retry time
            if transaction['next_retry_at'] and datetime.now() < transaction['next_retry_at']:
                continue
            
            # Attempt recovery
            if self.retry_transaction(transaction, load_balancer):
                recovered += 1
            else:
                failed += 1
        
        if recovered > 0 or failed > 0 or abandoned > 0:
            logger.info(f"📊 Recovery results: ✅{recovered} recovered, ❌{failed} failed, 🚫{abandoned} abandoned")
    
    def get_transaction_status(self, transaction_id: str) -> Optional[Dict]:
        """Get current status of a transaction"""
        try:
            with self.get_db_connection() as conn:
                with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                    cur.execute("""
                        SELECT * FROM emergency_transaction_log 
                        WHERE transaction_id = %s
                    """, (transaction_id,))
                    row = cur.fetchone()
                    return dict(row) if row else None
        except Exception as e:
            logger.error(f"❌ Failed to get transaction status: {e}")
            return None
    
    def get_safety_summary(self) -> Dict:
        """Get transaction safety summary for monitoring"""
        try:
            with self.get_db_connection() as conn:
                with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                    cur.execute("SELECT * FROM transaction_safety_summary")
                    summary = [dict(row) for row in cur.fetchall()]
                    
                    # Get additional metrics
                    cur.execute("""
                        SELECT 
                            COUNT(*) as total_transactions,
                            COUNT(*) FILTER (WHERE is_timing_gap_failure = TRUE) as timing_gap_failures,
                            COUNT(*) FILTER (WHERE status = 'RECOVERED') as recovered_transactions
                        FROM emergency_transaction_log 
                        WHERE created_at > NOW() - INTERVAL '24 hours'
                    """)
                    metrics = dict(cur.fetchone())
                    
                    return {
                        "summary_by_status": summary,
                        "metrics": metrics,
                        "recovery_service_running": self.is_running
                    }
        except Exception as e:
            logger.error(f"❌ Failed to get safety summary: {e}")
            return {"error": str(e)}
    
    def cleanup_old_transactions(self, days_old: int = 7):
        """Clean up old completed transactions"""
        try:
            with self.db_lock:
                with self.get_db_connection() as conn:
                    with conn.cursor() as cur:
                        cur.execute("""
                            DELETE FROM emergency_transaction_log 
                            WHERE status IN ('COMPLETED', 'ABANDONED') 
                            AND created_at < NOW() - INTERVAL '%s days'
                        """, (days_old,))
                        deleted = cur.rowcount
                        conn.commit()
            
            logger.info(f"🧹 Cleaned up {deleted} old transactions")
            return deleted
        except Exception as e:
            logger.error(f"❌ Failed to cleanup old transactions: {e}")
            return 0 