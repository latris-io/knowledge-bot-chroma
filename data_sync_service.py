#!/usr/bin/env python3
"""
ChromaDB Data Synchronization Service
Syncs data from primary to replica instance for true redundancy
Fixed: Uses direct HTTP requests with proper Accept-Encoding headers to avoid compression issues
"""

import os
import time
import logging
import schedule
import requests
import json
from datetime import datetime
from typing import List, Dict, Optional

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class ChromaDataSync:
    def __init__(self):
        self.primary_url = os.getenv("PRIMARY_URL", "https://chroma-primary.onrender.com")
        self.replica_url = os.getenv("REPLICA_URL", "https://chroma-replica.onrender.com")
        self.sync_interval = int(os.getenv("SYNC_INTERVAL", "300"))  # 5 minutes
        
        # Ensure URLs don't have trailing slashes
        self.primary_url = self.primary_url.rstrip('/')
        self.replica_url = self.replica_url.rstrip('/')
        
        logger.info(f"ChromaDB Sync Service initialized")
        logger.info(f"Primary: {self.primary_url}")
        logger.info(f"Replica: {self.replica_url}")
        
    def _make_request(self, method: str, url: str, **kwargs) -> requests.Response:
        """Make HTTP request with compression-fix headers"""
        # Apply the same fix that resolved load balancer compression issues
        headers = kwargs.get('headers', {})
        headers.update({
            'Accept-Encoding': '',  # Request uncompressed content
            'Accept': 'application/json',
            'Content-Type': 'application/json'
        })
        kwargs['headers'] = headers
        
        response = requests.request(method, url, **kwargs)
        response.raise_for_status()
        return response

    def get_all_databases(self, base_url: str) -> List[Dict]:
        """Get list of all databases from a ChromaDB instance"""
        try:
            url = f"{base_url}/api/v2/tenants/default_tenant/databases"
            response = self._make_request('GET', url)
            databases = response.json()
            logger.debug(f"Found {len(databases)} databases at {base_url}")
            return databases
        except Exception as e:
            logger.error(f"Failed to list databases from {base_url}: {e}")
            return []

    def create_database(self, base_url: str, database_name: str) -> bool:
        """Create a database if it doesn't exist"""
        try:
            url = f"{base_url}/api/v2/tenants/default_tenant/databases"
            data = {"name": database_name}
            response = self._make_request('POST', url, json=data)
            logger.info(f"Created database '{database_name}' on {base_url}")
            return True
        except Exception as e:
            logger.error(f"Failed to create database '{database_name}': {e}")
            return False

    def ensure_database_exists(self, base_url: str, database_name: str = "default_database") -> bool:
        """Ensure a database exists, create if missing"""
        databases = self.get_all_databases(base_url)
        
        # Check if database already exists
        for db in databases:
            if db.get('name') == database_name:
                logger.debug(f"Database '{database_name}' already exists on {base_url}")
                return True
        
        # Create the database
        logger.info(f"Database '{database_name}' missing on {base_url}, creating...")
        return self.create_database(base_url, database_name)

    def get_all_collections(self, base_url: str) -> List[Dict]:
        """Get list of all collections from a ChromaDB instance"""
        try:
            # First ensure the database exists
            if not self.ensure_database_exists(base_url):
                logger.error(f"Cannot access collections - database setup failed on {base_url}")
                return []
            
            url = f"{base_url}/api/v2/tenants/default_tenant/databases/default_database/collections"
            response = self._make_request('GET', url)
            collections = response.json()
            logger.debug(f"Found {len(collections)} collections at {base_url}")
            return collections
        except Exception as e:
            logger.error(f"Failed to list collections from {base_url}: {e}")
            return []

    def get_collection_data(self, base_url: str, collection_id: str) -> Optional[Dict]:
        """Get all data from a collection"""
        try:
            url = f"{base_url}/api/v2/tenants/default_tenant/databases/default_database/collections/{collection_id}/get"
            data = {
                "include": ["documents", "metadatas", "embeddings"],
                "limit": 10000  # Large limit to get all data
            }
            response = self._make_request('POST', url, json=data)
            result = response.json()
            logger.debug(f"Retrieved {len(result.get('ids', []))} documents from collection {collection_id}")
            return result
        except Exception as e:
            logger.error(f"Failed to get collection data from {base_url}/{collection_id}: {e}")
            return None

    def create_collection(self, base_url: str, collection_name: str) -> Optional[str]:
        """Create a new collection"""
        try:
            url = f"{base_url}/api/v2/tenants/default_tenant/databases/default_database/collections"
            data = {
                "name": collection_name,
                "metadata": {"synced_from": "primary"}
            }
            response = self._make_request('POST', url, json=data)
            result = response.json()
            collection_id = result.get('id')
            logger.info(f"Created collection '{collection_name}' with ID {collection_id}")
            return collection_id
        except Exception as e:
            logger.error(f"Failed to create collection '{collection_name}': {e}")
            return None

    def clear_collection(self, base_url: str, collection_id: str):
        """Clear all documents from a collection"""
        try:
            # First get all document IDs
            data = self.get_collection_data(base_url, collection_id)
            if not data or not data.get('ids'):
                return
            
            # Delete all documents
            url = f"{base_url}/api/v2/tenants/default_tenant/databases/default_database/collections/{collection_id}/delete"
            delete_data = {"ids": data['ids']}
            self._make_request('POST', url, json=delete_data)
            logger.info(f"Cleared {len(data['ids'])} documents from collection {collection_id}")
        except Exception as e:
            logger.warning(f"Could not clear collection {collection_id}: {e}")

    def add_documents_to_collection(self, base_url: str, collection_id: str, data: Dict):
        """Add documents to a collection"""
        try:
            if not data.get('ids'):
                return
                
            url = f"{base_url}/api/v2/tenants/default_tenant/databases/default_database/collections/{collection_id}/add"
            
            # Prepare data for ChromaDB API
            add_data = {
                "ids": data['ids'],
                "documents": data.get('documents'),
                "metadatas": data.get('metadatas'),
                "embeddings": data.get('embeddings')
            }
            
            # Remove None values
            add_data = {k: v for k, v in add_data.items() if v is not None}
            
            self._make_request('POST', url, json=add_data)
            logger.info(f"Added {len(data['ids'])} documents to collection {collection_id}")
        except Exception as e:
            logger.error(f"Failed to add documents to collection {collection_id}: {e}")

    def delete_collection(self, base_url: str, collection_name: str):
        """Delete a collection by name"""
        try:
            url = f"{base_url}/api/v2/tenants/default_tenant/databases/default_database/collections/{collection_name}"
            self._make_request('DELETE', url)
            logger.info(f"Deleted collection '{collection_name}'")
        except Exception as e:
            logger.warning(f"Could not delete collection '{collection_name}': {e}")

    def sync_collection(self, primary_collection: Dict, replica_collections: List[Dict]) -> bool:
        """Sync a single collection from primary to replica"""
        try:
            collection_name = primary_collection['name']
            collection_id = primary_collection['id']
            
            logger.info(f"Syncing collection '{collection_name}' ({collection_id})")
            
            # Get all data from primary collection
            primary_data = self.get_collection_data(self.primary_url, collection_id)
            if not primary_data:
                logger.error(f"Could not retrieve data from primary collection '{collection_name}'")
                return False
            
            # Find or create replica collection (always create structure, even if empty)
            replica_collection_id = None
            for replica_col in replica_collections:
                if replica_col['name'] == collection_name:
                    replica_collection_id = replica_col['id']
                    break
            
            if not replica_collection_id:
                # Create collection on replica
                replica_collection_id = self.create_collection(self.replica_url, collection_name)
                if not replica_collection_id:
                    return False
            
            # Clear replica collection (full sync approach)
            self.clear_collection(self.replica_url, replica_collection_id)
            
            # Add documents to replica only if primary has data
            if primary_data.get('ids'):
                self.add_documents_to_collection(self.replica_url, replica_collection_id, primary_data)
                logger.info(f"Successfully synced collection '{collection_name}' with {len(primary_data['ids'])} documents")
            else:
                logger.info(f"Collection '{collection_name}' is empty - created empty collection structure on replica")
            return True
            
        except Exception as e:
            logger.error(f"Failed to sync collection '{collection_name}': {e}")
            return False

    def perform_full_sync(self):
        """Perform full synchronization from primary to replica"""
        try:
            start_time = time.time()
            logger.info("Starting full data synchronization...")
            
            # Get all collections from both instances
            primary_collections = self.get_all_collections(self.primary_url)
            replica_collections = self.get_all_collections(self.replica_url)
            
            if not primary_collections:
                logger.info("No collections found on primary instance")
                return
            
            logger.info(f"Primary has {len(primary_collections)} collections")
            logger.info(f"Replica has {len(replica_collections)} collections")
            
            # Sync each collection from primary to replica
            synced_collections = 0
            total_documents = 0
            
            for primary_collection in primary_collections:
                if self.sync_collection(primary_collection, replica_collections):
                    synced_collections += 1
                    
                    # Count documents synced - find the correct replica collection ID
                    try:
                        # Find the replica collection with the same name
                        replica_collection_id = None
                        for replica_col in replica_collections:
                            if replica_col['name'] == primary_collection['name']:
                                replica_collection_id = replica_col['id']
                                break
                        
                        if replica_collection_id:
                            replica_data = self.get_collection_data(self.replica_url, replica_collection_id)
                            if replica_data:
                                total_documents += len(replica_data.get('ids', []))
                    except Exception as e:
                        logger.debug(f"Could not count documents for {primary_collection['name']}: {e}")
                        pass
            
            # Clean up collections that exist on replica but not on primary
            primary_names = {col['name'] for col in primary_collections}
            for replica_collection in replica_collections:
                if replica_collection['name'] not in primary_names:
                    self.delete_collection(self.replica_url, replica_collection['name'])
            
            sync_time = time.time() - start_time
            logger.info(f"Sync completed: {synced_collections}/{len(primary_collections)} collections, "
                       f"{total_documents} total documents, {sync_time:.2f}s")
            
        except Exception as e:
            logger.error(f"Full sync failed: {e}")

    def health_check(self):
        """Check if both instances are healthy"""
        try:
            # Test primary
            primary_collections = self.get_all_collections(self.primary_url)
            
            # Test replica  
            replica_collections = self.get_all_collections(self.replica_url)
            
            logger.info(f"Health check: Primary({len(primary_collections)} collections), "
                       f"Replica({len(replica_collections)} collections)")
            
            return True
            
        except Exception as e:
            logger.error(f"Health check failed: {e}")
            return False

    def run(self):
        """Main sync loop"""
        logger.info(f"Starting ChromaDB data sync service (interval: {self.sync_interval}s)")
        
        # Schedule regular sync
        schedule.every(self.sync_interval).seconds.do(self.perform_full_sync)
        schedule.every().hour.do(self.health_check)
        
        # Initial sync
        self.perform_full_sync()
        
        # Main loop
        while True:
            try:
                schedule.run_pending()
                time.sleep(10)
            except KeyboardInterrupt:
                logger.info("Sync service shutting down...")
                break
            except Exception as e:
                logger.error(f"Unexpected error in sync loop: {e}")
                time.sleep(60)

if __name__ == "__main__":
    sync_service = ChromaDataSync()
    sync_service.run() 