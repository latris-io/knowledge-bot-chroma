#!/usr/bin/env python3
"""
Production-Safe Test Collection Management
Ensures test collections are clearly identified and safely cleaned up
IMPROVED: Enhanced cloud environment robustness with retry logic
"""

import time
import random
import string
import logging
import chromadb
from typing import List, Optional

logger = logging.getLogger(__name__)

class SafeTestCollectionManager:
    """
    Manages test collections with production-safe naming and cleanup
    """
    
    # Production safety: All test collections MUST start with this prefix
    TEST_PREFIX = "AUTOTEST_"
    
    def __init__(self, client: chromadb.HttpClient):
        self.client = client
        self.created_collections: List[str] = []
        self.session_id = self._generate_session_id()
        
    def _generate_session_id(self) -> str:
        """Generate unique session ID for this test run"""
        timestamp = int(time.time())
        random_suffix = ''.join(random.choices(string.ascii_lowercase + string.digits, k=6))
        return f"{timestamp}_{random_suffix}"
    
    def retry_operation(self, operation_func, max_retries: int = 3, backoff_factor: float = 1.0, operation_name: str = "operation"):
        """Retry an operation with exponential backoff for cloud resilience"""
        for attempt in range(max_retries):
            try:
                return operation_func()
            except Exception as e:
                error_str = str(e).lower()
                
                # Check if it's a temporary cloud issue
                is_temporary_error = any(temp_error in error_str for temp_error in [
                    'service unavailable', '503', '502', '504', 
                    'timeout', 'connection', 'proxy error',
                    'temporarily unavailable', 'try again'
                ])
                
                if attempt == max_retries - 1:  # Last attempt
                    if is_temporary_error:
                        logger.warning(f"⚠️ {operation_name} failed after {max_retries} attempts with temporary error: {e}")
                    raise e
                
                if is_temporary_error:
                    wait_time = backoff_factor * (2 ** attempt) + random.uniform(0, 1)  # Add jitter
                    logger.debug(f"🔄 {operation_name} temporary failure (attempt {attempt + 1}/{max_retries}), retrying in {wait_time:.1f}s: {e}")
                    time.sleep(wait_time)
                else:
                    # Non-temporary error, don't retry
                    raise e
    
    def create_test_collection_name(self, purpose: str) -> str:
        """
        Create a production-safe test collection name
        
        Format: AUTOTEST_[purpose]_[session_id]_[random]
        Example: AUTOTEST_basic_1705123456_abc123_xyz789
        """
        # Sanitize purpose (remove special chars, limit length)
        clean_purpose = ''.join(c for c in purpose if c.isalnum() or c in ['_', '-'])[:20]
        
        # Add extra randomness for uniqueness
        extra_random = ''.join(random.choices(string.ascii_lowercase + string.digits, k=6))
        
        collection_name = f"{self.TEST_PREFIX}{clean_purpose}_{self.session_id}_{extra_random}"
        
        # Track for cleanup
        self.created_collections.append(collection_name)
        
        logger.info(f"🧪 Created test collection name: {collection_name}")
        return collection_name
    
    def create_test_collection(self, purpose: str, metadata: Optional[dict] = None) -> chromadb.Collection:
        """
        Create a test collection with production-safe naming and retry logic
        """
        collection_name = self.create_test_collection_name(purpose)
        
        # Add test metadata
        test_metadata = {
            "test_collection": True,
            "test_session": self.session_id,
            "test_purpose": purpose,
            "created_at": time.time(),
            "safe_to_delete": True
        }
        
        if metadata:
            test_metadata.update(metadata)
        
        try:
            def create_collection():
                return self.client.get_or_create_collection(
                    name=collection_name,
                    metadata=test_metadata
                )
            
            collection = self.retry_operation(
                create_collection, 
                max_retries=3, 
                backoff_factor=1.0,
                operation_name=f"create collection {collection_name}"
            )
            logger.info(f"✅ Created test collection: {collection_name}")
            return collection
        except Exception as e:
            logger.error(f"❌ Failed to create test collection {collection_name}: {e}")
            # Remove from tracking if creation failed
            if collection_name in self.created_collections:
                self.created_collections.remove(collection_name)
            raise
    
    def is_test_collection(self, collection_name: str) -> bool:
        """
        Verify if a collection name is a test collection
        """
        return collection_name.startswith(self.TEST_PREFIX)
    
    def cleanup_session_collections(self) -> dict:
        """
        Clean up all collections created in this test session with improved error handling
        """
        logger.info(f"🧹 Cleaning up {len(self.created_collections)} test collections...")
        
        cleanup_results = {
            "attempted": 0,
            "successful": 0,
            "failed": 0,
            "temporary_failures": 0,
            "errors": []
        }
        
        for collection_name in self.created_collections.copy():
            cleanup_results["attempted"] += 1
            
            try:
                # Double-check it's a test collection before deletion
                if not self.is_test_collection(collection_name):
                    error_msg = f"SAFETY VIOLATION: Attempted to delete non-test collection: {collection_name}"
                    logger.error(error_msg)
                    cleanup_results["errors"].append(error_msg)
                    cleanup_results["failed"] += 1
                    continue
                
                # Delete the collection with retry logic
                def delete_collection():
                    self.client.delete_collection(collection_name)
                
                self.retry_operation(
                    delete_collection,
                    max_retries=3,
                    backoff_factor=2.0,  # Longer backoff for cleanup
                    operation_name=f"delete collection {collection_name}"
                )
                
                logger.info(f"🗑️ Deleted test collection: {collection_name}")
                cleanup_results["successful"] += 1
                
                # Remove from tracking
                self.created_collections.remove(collection_name)
                
            except Exception as e:
                error_str = str(e).lower()
                # Now that DELETE operations work reliably, be more specific about temporary failures
                is_temporary = any(temp_error in error_str for temp_error in [
                    'service unavailable', '503', '502', '504', 
                    'timeout', 'connection', 'proxy error',
                    'temporarily unavailable'  # Removed generic "delete" errors
                ])
                
                if is_temporary:
                    cleanup_results["temporary_failures"] += 1
                    error_msg = f"Temporary failure deleting {collection_name}: {str(e)[:100]}..."
                    logger.warning(f"⚠️ {error_msg}")
                else:
                    cleanup_results["failed"] += 1
                    error_msg = f"Failed to delete {collection_name}: {str(e)}"
                    logger.warning(error_msg)
                
                cleanup_results["errors"].append(error_msg)
        
        # Summary with improved reporting
        logger.info(f"🧹 Cleanup complete: {cleanup_results['successful']}/{cleanup_results['attempted']} collections deleted")
        
        if cleanup_results["temporary_failures"] > 0:
            logger.warning(f"⚠️ {cleanup_results['temporary_failures']} collections failed due to temporary cloud issues (may clean up automatically)")
        
        if cleanup_results["failed"] > 0:
            logger.warning(f"❌ {cleanup_results['failed']} collections could not be deleted")
        
        # Only log first few errors to avoid spam
        max_errors_to_show = 3
        errors_to_show = cleanup_results["errors"][:max_errors_to_show]
        for error in errors_to_show:
            logger.warning(f"  - {error}")
        
        if len(cleanup_results["errors"]) > max_errors_to_show:
            logger.warning(f"  ... and {len(cleanup_results['errors']) - max_errors_to_show} more errors")
        
        return cleanup_results
    
    def cleanup_all_test_collections(self, max_age_hours: float = 24) -> dict:
        """
        Clean up ALL test collections older than specified age with retry logic
        WARNING: Use with caution in production
        """
        logger.warning("🚨 DANGER: Attempting to clean up ALL old test collections")
        
        cleanup_results = {
            "scanned": 0,
            "found_test_collections": 0,
            "deleted": 0,
            "failed": 0,
            "temporary_failures": 0,
            "errors": []
        }
        
        try:
            def list_collections():
                return self.client.list_collections()
            
            # Get all collections with retry
            collections = self.retry_operation(
                list_collections,
                max_retries=3,
                backoff_factor=1.0,
                operation_name="list collections"
            )
            cleanup_results["scanned"] = len(collections)
            
            current_time = time.time()
            max_age_seconds = max_age_hours * 3600
            
            for collection in collections:
                collection_name = collection.name
                
                # Only process test collections
                if not self.is_test_collection(collection_name):
                    continue
                
                cleanup_results["found_test_collections"] += 1
                
                try:
                    # Check age based on collection metadata
                    metadata = collection.metadata or {}
                    created_at = metadata.get("created_at", 0)
                    
                    if created_at and (current_time - created_at) > max_age_seconds:
                        def delete_old_collection():
                            self.client.delete_collection(collection_name)
                        
                        self.retry_operation(
                            delete_old_collection,
                            max_retries=3,
                            backoff_factor=2.0,
                            operation_name=f"delete old collection {collection_name}"
                        )
                        
                        logger.info(f"🗑️ Deleted old test collection: {collection_name}")
                        cleanup_results["deleted"] += 1
                    else:
                        logger.debug(f"⏸️ Keeping recent test collection: {collection_name}")
                
                except Exception as e:
                    error_str = str(e).lower()
                    is_temporary = any(temp_error in error_str for temp_error in [
                        'service unavailable', '503', '502', '504', 
                        'timeout', 'connection', 'proxy error'
                    ])
                    
                    if is_temporary:
                        cleanup_results["temporary_failures"] += 1
                    else:
                        cleanup_results["failed"] += 1
                    
                    error_msg = f"Failed to process {collection_name}: {str(e)}"
                    cleanup_results["errors"].append(error_msg)
        
        except Exception as e:
            error_msg = f"Failed to list collections: {str(e)}"
            cleanup_results["errors"].append(error_msg)
            logger.error(error_msg)
        
        logger.info(f"🧹 Global cleanup: {cleanup_results['deleted']} old test collections deleted")
        if cleanup_results["temporary_failures"] > 0:
            logger.warning(f"⚠️ {cleanup_results['temporary_failures']} operations failed due to temporary issues")
        
        return cleanup_results
    
    def get_remaining_test_collections(self) -> List[str]:
        """
        Get list of test collections that still exist
        """
        return self.created_collections.copy()
    
    def __enter__(self):
        """Context manager entry"""
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit - always cleanup with improved error handling"""
        try:
            cleanup_results = self.cleanup_session_collections()
            
            # If there were only temporary failures, don't treat as critical
            if cleanup_results["failed"] == 0 and cleanup_results["temporary_failures"] > 0:
                logger.info("🔄 Some collections couldn't be cleaned due to temporary issues - they may clean up automatically")
        except Exception as e:
            logger.error(f"❌ Critical error during cleanup: {e}")
            # Don't raise exceptions during context exit to avoid masking original test errors

def create_production_safe_test_client(load_balancer_url: str) -> tuple[chromadb.HttpClient, SafeTestCollectionManager]:
    """
    Create a ChromaDB client and test collection manager for production-safe testing
    """
    # Initialize client
    host = load_balancer_url.replace("https://", "").replace("http://", "")
    ssl = load_balancer_url.startswith("https://")
    port = 443 if ssl else 8000
    
    client = chromadb.HttpClient(host=host, port=port, ssl=ssl)
    manager = SafeTestCollectionManager(client)
    
    logger.info(f"🔒 Production-safe test client created for session: {manager.session_id}")
    
    return client, manager

# Example usage
if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Test Collection Management")
    parser.add_argument("--cleanup-old", action="store_true", help="Clean up old test collections")
    parser.add_argument("--max-age", type=float, default=24, help="Max age in hours for cleanup")
    parser.add_argument("--url", default="https://chroma-load-balancer.onrender.com", help="Load balancer URL")
    
    args = parser.parse_args()
    
    client, manager = create_production_safe_test_client(args.url)
    
    if args.cleanup_old:
        logger.info(f"🧹 Cleaning up test collections older than {args.max_age} hours...")
        results = manager.cleanup_all_test_collections(args.max_age)
        print(f"Cleanup results: {results}")
    else:
        # Demo usage
        with manager:
            test_collection = manager.create_test_collection("demo")
            print(f"Created demo collection: {test_collection.name}")
            # Cleanup happens automatically when exiting context 