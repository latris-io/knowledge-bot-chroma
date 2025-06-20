#!/usr/bin/env python3
"""
Transaction Safety Deployment Script
Deploys the transaction safety schema and validates the system
"""

import os
import sys
import uuid
import logging
import psycopg2
import psycopg2.extras
from typing import Optional

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class TransactionSafetyDeployer:
    """Deploy and validate transaction safety system"""
    
    def __init__(self, database_url: Optional[str] = None):
        self.database_url = database_url or os.getenv('DATABASE_URL')
        if not self.database_url:
            raise ValueError("DATABASE_URL environment variable not set")
    
    def get_db_connection(self):
        """Get database connection"""
        return psycopg2.connect(self.database_url)
    
    def deploy_schema(self):
        """Deploy the transaction safety schema"""
        logger.info("🚀 Deploying transaction safety schema...")
        
        try:
            # Read schema file
            schema_file = 'transaction_safety_schema.sql'
            if not os.path.exists(schema_file):
                logger.error(f"❌ Schema file not found: {schema_file}")
                return False
            
            with open(schema_file, 'r') as f:
                schema_sql = f.read()
            
            # Execute schema
            with self.get_db_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute(schema_sql)
                    conn.commit()
            
            logger.info("✅ Transaction safety schema deployed successfully")
            return True
            
        except Exception as e:
            logger.error(f"❌ Failed to deploy schema: {e}")
            return False
    
    def validate_schema(self):
        """Validate that the schema was deployed correctly"""
        logger.info("🔍 Validating transaction safety schema...")
        
        try:
            with self.get_db_connection() as conn:
                with conn.cursor() as cur:
                    # Check if main table exists
                    cur.execute("""
                        SELECT EXISTS (
                            SELECT FROM information_schema.tables 
                            WHERE table_name = 'emergency_transaction_log'
                        )
                    """)
                    
                    table_exists = cur.fetchone()[0]
                    
                    if not table_exists:
                        logger.error("❌ emergency_transaction_log table does not exist")
                        return False
                    
                    # Check if indexes exist
                    cur.execute("""
                        SELECT indexname FROM pg_indexes 
                        WHERE tablename = 'emergency_transaction_log'
                    """)
                    
                    indexes = [row[0] for row in cur.fetchall()]
                    expected_indexes = [
                        'idx_emergency_tx_status',
                        'idx_emergency_tx_created', 
                        'idx_emergency_tx_retry',
                        'idx_emergency_tx_session',
                        'idx_emergency_tx_timing_gap'
                    ]
                    
                    missing_indexes = [idx for idx in expected_indexes if idx not in indexes]
                    if missing_indexes:
                        logger.warning(f"⚠️ Missing indexes: {missing_indexes}")
                    
                    # Check if views exist
                    cur.execute("""
                        SELECT EXISTS (
                            SELECT FROM information_schema.views 
                            WHERE table_name = 'transaction_safety_summary'
                        )
                    """)
                    
                    view_exists = cur.fetchone()[0]
                    
                    if not view_exists:
                        logger.error("❌ transaction_safety_summary view does not exist")
                        return False
                    
                    logger.info("✅ Schema validation successful")
                    return True
                    
        except Exception as e:
            logger.error(f"❌ Schema validation failed: {e}")
            return False
    
    def test_basic_functionality(self):
        """Test basic transaction logging functionality"""
        logger.info("🧪 Testing basic transaction safety functionality...")
        
        try:
            with self.get_db_connection() as conn:
                with conn.cursor() as cur:
                    # Insert a test transaction with proper UUID
                    test_transaction_id = str(uuid.uuid4())
                    
                    cur.execute("""
                        INSERT INTO emergency_transaction_log 
                        (transaction_id, method, path, status, operation_type, client_session)
                        VALUES (%s, %s, %s, %s, %s, %s)
                    """, (
                        test_transaction_id,
                        'POST',
                        '/api/v2/test',
                        'ATTEMPTING',
                        'file_upload',
                        'test_session'
                    ))
                    
                    # Update transaction to completed
                    cur.execute("""
                        UPDATE emergency_transaction_log 
                        SET status = 'COMPLETED', completed_at = NOW()
                        WHERE transaction_id = %s
                    """, (test_transaction_id,))
                    
                    # Verify the transaction exists
                    cur.execute("""
                        SELECT status, operation_type FROM emergency_transaction_log 
                        WHERE transaction_id = %s
                    """, (test_transaction_id,))
                    
                    result = cur.fetchone()
                    if not result or result[0] != 'COMPLETED':
                        logger.error("❌ Transaction logging test failed")
                        return False
                    
                    # Test the summary view
                    cur.execute("SELECT * FROM transaction_safety_summary LIMIT 1")
                    summary = cur.fetchone()
                    
                    if not summary:
                        logger.warning("⚠️ No data in transaction_safety_summary view")
                    
                    # Clean up test data
                    cur.execute("""
                        DELETE FROM emergency_transaction_log 
                        WHERE transaction_id = %s
                    """, (test_transaction_id,))
                    
                    conn.commit()
                    
                    logger.info("✅ Basic functionality test passed")
                    return True
                    
        except Exception as e:
            logger.error(f"❌ Basic functionality test failed: {e}")
            return False
    
    def display_deployment_summary(self):
        """Display deployment summary and next steps"""
        logger.info("\n" + "="*60)
        logger.info("TRANSACTION SAFETY DEPLOYMENT COMPLETE")
        logger.info("="*60)
        
        try:
            with self.get_db_connection() as conn:
                with conn.cursor() as cur:
                    # Get table info
                    cur.execute("""
                        SELECT 
                            schemaname,
                            tablename,
                            tableowner
                        FROM pg_tables 
                        WHERE tablename = 'emergency_transaction_log'
                    """)
                    
                    table_info = cur.fetchone()
                    if table_info:
                        schema, table, owner = table_info
                        logger.info(f"📊 Table: {schema}.{table} (owner: {owner})")
                    
                    # Get current stats
                    cur.execute("SELECT COUNT(*) FROM emergency_transaction_log")
                    transaction_count = cur.fetchone()[0]
                    
                    logger.info(f"📈 Current transactions logged: {transaction_count}")
                    
        except Exception as e:
            logger.warning(f"⚠️ Could not retrieve deployment stats: {e}")
        
        logger.info("\n📋 Next Steps:")
        logger.info("1. Restart the load balancer to initialize transaction safety service")
        logger.info("2. Test with: python test_transaction_safety.py --url <load_balancer_url>")
        logger.info("3. Monitor transaction safety status at: <load_balancer_url>/transaction/safety/status")
        logger.info("4. Integrate client-side transaction safety in your CMS application")
        
        logger.info("\n🔗 Useful Endpoints:")
        logger.info("- Transaction Safety Status: GET /transaction/safety/status")
        logger.info("- Transaction Details: GET /transaction/safety/transaction/<id>")
        logger.info("- Manual Recovery: POST /transaction/safety/recovery/trigger")
        logger.info("- Cleanup Old Transactions: POST /transaction/safety/cleanup")
    
    def run_full_deployment(self):
        """Run complete deployment process"""
        logger.info("🚀 Starting transaction safety deployment...")
        
        success = True
        
        # Step 1: Deploy schema
        if not self.deploy_schema():
            success = False
        
        # Step 2: Validate schema
        if success and not self.validate_schema():
            success = False
        
        # Step 3: Test basic functionality
        if success and not self.test_basic_functionality():
            success = False
        
        # Step 4: Display summary
        if success:
            self.display_deployment_summary()
            logger.info("🎉 Transaction safety deployment completed successfully!")
            return True
        else:
            logger.error("❌ Transaction safety deployment failed!")
            return False

def main():
    """Main deployment function"""
    import argparse
    
    parser = argparse.ArgumentParser(description="Deploy transaction safety system")
    parser.add_argument("--database-url", help="Database URL (overrides environment variable)")
    parser.add_argument("--validate-only", action="store_true", help="Only validate existing schema")
    parser.add_argument("--test-only", action="store_true", help="Only run functionality tests")
    
    args = parser.parse_args()
    
    try:
        deployer = TransactionSafetyDeployer(args.database_url)
        
        if args.validate_only:
            success = deployer.validate_schema()
        elif args.test_only:
            success = deployer.test_basic_functionality()
        else:
            success = deployer.run_full_deployment()
        
        sys.exit(0 if success else 1)
        
    except Exception as e:
        logger.error(f"❌ Deployment failed with exception: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main() 