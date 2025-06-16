#!/usr/bin/env python3
"""
Comprehensive Database Cleanup Script
Removes all test data from ChromaDB collections and PostgreSQL WAL database
"""

import requests
import json
import time
import os
import sys
from datetime import datetime

class ComprehensiveDatabaseCleanup:
    def __init__(self, base_url="https://chroma-load-balancer.onrender.com"):
        self.base_url = base_url.rstrip('/')
        self.cleanup_results = {
            'collections_deleted': 0,
            'failed_collection_deletions': 0,
            'wal_entries_deleted': 0,
            'errors': []
        }
        
    def log_info(self, message):
        """Log with timestamp"""
        timestamp = datetime.now().strftime("%H:%M:%S")
        print(f"[{timestamp}] {message}")
        
    def log_error(self, message):
        """Log error with timestamp"""
        timestamp = datetime.now().strftime("%H:%M:%S")
        print(f"[{timestamp}] ❌ ERROR: {message}")
        self.cleanup_results['errors'].append(message)
    
    def get_all_collections(self):
        """Get all collections from both instances"""
        self.log_info("📋 Fetching all collections...")
        
        try:
            response = requests.get(
                f"{self.base_url}/api/v2/tenants/default_tenant/databases/default_database/collections",
                timeout=30
            )
            
            if response.status_code == 200:
                collections = response.json()
                self.log_info(f"   Found {len(collections)} total collections")
                return collections
            else:
                self.log_error(f"Failed to fetch collections: {response.status_code}")
                return []
                
        except Exception as e:
            self.log_error(f"Exception fetching collections: {e}")
            return []
    
    def identify_test_collections(self, collections):
        """Identify test collections by name patterns"""
        test_patterns = [
            'test_', 'AUTOTEST_', 'TEST_', 'doc_test_', 
            'delete_sync_', 'temp_', 'demo_', 'sample_',
            '_test', '_demo', 'verification_', 'debug_'
        ]
        
        test_collections = []
        
        for collection in collections:
            collection_name = collection.get('name', '')
            
            # Check if collection name matches test patterns
            is_test = any(pattern.lower() in collection_name.lower() for pattern in test_patterns)
            
            if is_test:
                test_collections.append(collection)
                
        self.log_info(f"   Identified {len(test_collections)} test collections for deletion")
        return test_collections
    
    def delete_test_collections(self, test_collections):
        """Delete identified test collections"""
        self.log_info("🧹 Deleting test collections...")
        
        for collection in test_collections:
            collection_name = collection.get('name', 'unknown')
            
            try:
                self.log_info(f"   Deleting: {collection_name}")
                
                response = requests.delete(
                    f"{self.base_url}/api/v2/tenants/default_tenant/databases/default_database/collections/{collection_name}",
                    timeout=30
                )
                
                if response.status_code in [200, 404]:  
                    self.cleanup_results['collections_deleted'] += 1
                    self.log_info(f"   ✅ Deleted: {collection_name}")
                else:
                    self.cleanup_results['failed_collection_deletions'] += 1
                    self.log_error(f"Failed to delete {collection_name}: {response.status_code}")
                    
            except Exception as e:
                self.cleanup_results['failed_collection_deletions'] += 1
                self.log_error(f"Exception deleting {collection_name}: {e}")
            
            time.sleep(0.5)
    
    def cleanup_wal_database(self):
        """Clean up WAL entries"""
        self.log_info("🗄️ Cleaning up WAL database...")
        
        try:
            cleanup_payload = {"max_age_hours": 1}
            
            response = requests.post(
                f"{self.base_url}/wal/cleanup",
                headers={"Content-Type": "application/json"},
                json=cleanup_payload,
                timeout=30
            )
            
            if response.status_code == 200:
                result = response.json()
                deleted_entries = result.get('deleted_entries', 0)
                self.cleanup_results['wal_entries_deleted'] = deleted_entries
                self.log_info(f"   ✅ Cleaned up {deleted_entries} WAL entries")
            else:
                self.log_error(f"WAL cleanup failed: {response.status_code}")
                
        except Exception as e:
            self.log_error(f"WAL cleanup exception: {e}")
    
    def run_comprehensive_cleanup(self):
        """Run the complete cleanup process"""
        self.log_info("🚀 Starting Comprehensive Database Cleanup")
        self.log_info(f"📍 Target URL: {self.base_url}")
        
        # Get all collections
        all_collections = self.get_all_collections()
        
        if not all_collections:
            self.log_error("Could not fetch collections. Aborting cleanup.")
            return False
        
        # Identify test collections
        test_collections = self.identify_test_collections(all_collections)
        
        if len(test_collections) == 0:
            self.log_info("✅ No test collections found to delete")
        else:
            # Delete test collections
            self.delete_test_collections(test_collections)
        
        # Clean up WAL database
        self.cleanup_wal_database()
        
        self.log_info(f"✅ Cleanup complete: {self.cleanup_results['collections_deleted']} collections deleted")
        return len(self.cleanup_results['errors']) == 0

def main():
    cleanup_tool = ComprehensiveDatabaseCleanup("https://chroma-load-balancer.onrender.com")
    success = cleanup_tool.run_comprehensive_cleanup()
    
    if success:
        print("🎉 All cleanup operations completed successfully!")
    else:
        print("⚠️ Some cleanup operations failed")
        exit(1)

if __name__ == "__main__":
    main() 