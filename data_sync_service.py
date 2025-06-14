#!/usr/bin/env python3
"""
ChromaDB Data Synchronization Service
Syncs data from primary to replica instance for true redundancy
"""

import os
import time
import logging
import schedule
import chromadb
from datetime import datetime
from typing import List, Dict

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class ChromaDataSync:
    def __init__(self):
        self.primary_url = os.getenv("PRIMARY_URL", "https://chroma-primary.onrender.com")
        self.replica_url = os.getenv("REPLICA_URL", "https://chroma-replica.onrender.com")
        self.sync_interval = int(os.getenv("SYNC_INTERVAL", "300"))  # 5 minutes
        
        # Initialize clients
        self.primary_client = None
        self.replica_client = None
        
        self.connect_clients()
        
    def connect_clients(self):
        """Connect to both ChromaDB instances"""
        try:
            # Extract host from URL for ChromaDB client
            primary_host = self.primary_url.replace("https://", "").replace("http://", "")
            replica_host = self.replica_url.replace("https://", "").replace("http://", "")
            
            self.primary_client = chromadb.HttpClient(
                host=primary_host,
                port=443 if "https" in self.primary_url else 8000,
                ssl="https" in self.primary_url
            )
            
            self.replica_client = chromadb.HttpClient(
                host=replica_host,
                port=443 if "https" in self.replica_url else 8000,
                ssl="https" in self.replica_url
            )
            
            logger.info("Connected to both ChromaDB instances")
            
        except Exception as e:
            logger.error(f"Failed to connect to ChromaDB instances: {e}")
            raise

    def get_all_collections(self, client) -> List[str]:
        """Get list of all collections from a ChromaDB instance"""
        try:
            collections = client.list_collections()
            return [col.name for col in collections]
        except Exception as e:
            logger.error(f"Failed to list collections: {e}")
            return []

    def sync_collection(self, collection_name: str) -> bool:
        """Sync a single collection from primary to replica"""
        try:
            # Get primary collection
            primary_collection = self.primary_client.get_collection(collection_name)
            
            # Get all data from primary
            result = primary_collection.get(include=['documents', 'metadatas', 'embeddings'])
            
            if not result['ids']:
                logger.info(f"Collection {collection_name} is empty, skipping")
                return True
            
            # Get or create replica collection
            try:
                replica_collection = self.replica_client.get_collection(collection_name)
            except:
                # Collection doesn't exist, create it
                replica_collection = self.replica_client.create_collection(collection_name)
                logger.info(f"Created collection {collection_name} on replica")
            
            # Clear replica collection (full sync approach)
            try:
                existing_ids = replica_collection.get()['ids']
                if existing_ids:
                    replica_collection.delete(ids=existing_ids)
                    logger.info(f"Cleared {len(existing_ids)} existing documents from replica")
            except Exception as e:
                logger.warning(f"Could not clear replica collection: {e}")
            
            # Add all documents to replica
            if result['documents']:
                replica_collection.add(
                    ids=result['ids'],
                    documents=result['documents'],
                    metadatas=result['metadatas'] if result['metadatas'] else None,
                    embeddings=result['embeddings'] if result['embeddings'] else None
                )
                
                logger.info(f"Synced {len(result['ids'])} documents to collection {collection_name}")
            
            return True
            
        except Exception as e:
            logger.error(f"Failed to sync collection {collection_name}: {e}")
            return False

    def perform_full_sync(self):
        """Perform full synchronization from primary to replica"""
        try:
            start_time = time.time()
            logger.info("Starting full data synchronization...")
            
            # Get all collections from primary
            primary_collections = self.get_all_collections(self.primary_client)
            
            if not primary_collections:
                logger.info("No collections found on primary instance")
                return
            
            # Sync each collection
            synced_collections = 0
            total_documents = 0
            
            for collection_name in primary_collections:
                if self.sync_collection(collection_name):
                    synced_collections += 1
                    
                    # Count documents synced
                    try:
                        replica_collection = self.replica_client.get_collection(collection_name)
                        doc_count = len(replica_collection.get()['ids'])
                        total_documents += doc_count
                    except:
                        pass
            
            # Clean up collections that exist on replica but not on primary
            replica_collections = self.get_all_collections(self.replica_client)
            for collection_name in replica_collections:
                if collection_name not in primary_collections:
                    try:
                        self.replica_client.delete_collection(collection_name)
                        logger.info(f"Deleted orphaned collection {collection_name} from replica")
                    except Exception as e:
                        logger.warning(f"Could not delete collection {collection_name}: {e}")
            
            sync_time = time.time() - start_time
            logger.info(f"Sync completed: {synced_collections}/{len(primary_collections)} collections, "
                       f"{total_documents} total documents, {sync_time:.2f}s")
            
        except Exception as e:
            logger.error(f"Full sync failed: {e}")

    def health_check(self):
        """Check if both instances are healthy"""
        try:
            # Test primary
            primary_collections = self.get_all_collections(self.primary_client)
            
            # Test replica  
            replica_collections = self.get_all_collections(self.replica_client)
            
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