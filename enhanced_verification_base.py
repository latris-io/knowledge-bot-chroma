#!/usr/bin/env python3
"""
Enhanced Verification Base Class
===============================

Shared verification methods for USE CASE 2 and USE CASE 3 testing.
Contains all document-level sync verification capabilities.
"""

import requests
from datetime import datetime

class EnhancedVerificationBase:
    """Base class with shared verification methods for USE CASE 2 and USE CASE 3"""
    
    def __init__(self):
        # These should be set by subclasses
        self.base_url = None
        self.primary_url = "https://chroma-primary.onrender.com"
        self.replica_url = "https://chroma-replica.onrender.com"
    
    def log(self, message, level="INFO"):
        """Log message with timestamp - to be overridden by subclasses"""
        timestamp = datetime.now().strftime("%H:%M:%S")
        print(f"[{timestamp}] {level}: {message}" if level != "INFO" else f"[{timestamp}] {message}")

    def get_collection_mappings(self):
        """Get collection mappings for UUID-based verification"""
        try:
            response = requests.get(f"{self.base_url}/admin/collection_mappings", timeout=10)
            if response.status_code == 200:
                data = response.json()
                mappings = data.get('collection_mappings', [])
                return mappings
            else:
                self.log(f"Failed to get collection mappings: {response.status_code}")
                return []
        except Exception as e:
            self.log(f"Error getting collection mappings: {e}")
            return []

    def get_document_count_from_instance(self, instance_url, collection_uuid):
        """Get document count from a specific instance using UUID"""
        try:
            response = requests.post(
                f"{instance_url}/api/v2/tenants/default_tenant/databases/default_database/collections/{collection_uuid}/get",
                json={"include": ["documents"]},
                timeout=10
            )
            
            if response.status_code == 200:
                result = response.json()
                documents = result.get('documents', [])
                return len(documents)
            else:
                return None
        except Exception as e:
            self.log(f"Error getting document count from {instance_url}: {e}")
            return None

    def verify_document_exists_on_instance(self, instance_url, collection_uuid, doc_id):
        """Verify a specific document exists on an instance and return full document data"""
        try:
            response = requests.post(
                f"{instance_url}/api/v2/tenants/default_tenant/databases/default_database/collections/{collection_uuid}/get",
                json={"ids": [doc_id], "include": ["documents", "metadatas", "embeddings"]},
                timeout=10
            )
            
            self.log(f"      API call: {response.status_code} for {instance_url[-20:]}.../{collection_uuid[:8]}")
            
            if response.status_code == 200:
                result = response.json()
                documents = result.get('documents', [])
                metadatas = result.get('metadatas', [])
                embeddings = result.get('embeddings', [])
                
                # ChromaDB API returns: documents=["content"], metadatas=[{meta}], embeddings=[[0.1, 0.2]]
                if len(documents) > 0 and documents[0]:
                    return {
                        'exists': True,
                        'content': documents[0],  # First document content
                        'metadata': metadatas[0] if metadatas and len(metadatas) > 0 else {},  # First metadata object
                        'embeddings': embeddings[0] if embeddings and len(embeddings) > 0 else None  # First embedding array
                    }
                else:
                    self.log(f"      Document exists but no content: documents={len(documents)}")
                    return {'exists': False}
            else:
                self.log(f"      API error {response.status_code}: {response.text}")
                return {'exists': False}
        except Exception as e:
            self.log(f"      Exception checking document on {instance_url}: {str(e)} ({type(e).__name__})")
            return {'exists': False}

    def compare_document_integrity(self, original_doc, primary_doc, replica_doc, doc_id):
        """Compare document integrity between original, primary, and replica"""
        integrity_issues = []
        
        # Check if documents exist on both instances
        if not primary_doc.get('exists', False):
            integrity_issues.append("Missing on primary")
        if not replica_doc.get('exists', False):
            integrity_issues.append("Missing on replica")
            
        if not primary_doc.get('exists', False) or not replica_doc.get('exists', False):
            return False, integrity_issues
            
        # Content integrity check
        original_content = original_doc['content']
        primary_content = primary_doc.get('content')
        replica_content = replica_doc.get('content')
        
        if primary_content != original_content:
            integrity_issues.append(f"Primary content mismatch: expected '{original_content}', got '{primary_content}'")
        if replica_content != original_content:
            integrity_issues.append(f"Replica content mismatch: expected '{original_content}', got '{replica_content}'")
        if primary_content != replica_content:
            integrity_issues.append(f"Primary/replica content differs: '{primary_content}' vs '{replica_content}'")
            
        # Metadata integrity check
        original_metadata = original_doc['metadata']
        primary_metadata = primary_doc.get('metadata', {})
        replica_metadata = replica_doc.get('metadata', {})
        
        # Check key metadata fields
        for key, expected_value in original_metadata.items():
            primary_value = primary_metadata.get(key)
            replica_value = replica_metadata.get(key)
            
            if primary_value != expected_value:
                integrity_issues.append(f"Primary metadata['{key}'] mismatch: expected '{expected_value}', got '{primary_value}'")
            if replica_value != expected_value:
                integrity_issues.append(f"Replica metadata['{key}'] mismatch: expected '{expected_value}', got '{replica_value}'")
            if primary_value != replica_value:
                integrity_issues.append(f"Primary/replica metadata['{key}'] differs: '{primary_value}' vs '{replica_value}'")
                
        # Embeddings integrity check (handle null/missing embeddings gracefully)
        original_embeddings = original_doc['embeddings']
        primary_embeddings = primary_doc.get('embeddings', [])
        replica_embeddings = replica_doc.get('embeddings', [])
        
        # Handle null embeddings from ChromaDB
        if primary_embeddings is None:
            primary_embeddings = []
        if replica_embeddings is None:
            replica_embeddings = []
            
        # Only check embeddings if we expected them to exist
        if original_embeddings and len(original_embeddings) > 0:
            if not primary_embeddings or len(primary_embeddings) == 0:
                integrity_issues.append(f"Primary embeddings missing: expected {original_embeddings}, got null/empty")
            elif primary_embeddings != original_embeddings:
                integrity_issues.append(f"Primary embeddings mismatch: expected {original_embeddings}, got {primary_embeddings}")
                
            if not replica_embeddings or len(replica_embeddings) == 0:
                integrity_issues.append(f"Replica embeddings missing: expected {original_embeddings}, got null/empty")
            elif replica_embeddings != original_embeddings:
                integrity_issues.append(f"Replica embeddings mismatch: expected {original_embeddings}, got {replica_embeddings}")
                
            if primary_embeddings != replica_embeddings:
                integrity_issues.append(f"Primary/replica embeddings differ: {primary_embeddings} vs {replica_embeddings}")
            
        return len(integrity_issues) == 0, integrity_issues

    def verify_document_via_load_balancer(self, collection_name, doc_id):
        """Verify document exists via load balancer as fallback"""
        try:
            response = requests.post(
                f"{self.base_url}/api/v2/tenants/default_tenant/databases/default_database/collections/{collection_name}/get",
                json={"ids": [doc_id], "include": ["documents", "metadatas", "embeddings"]},
                timeout=10
            )
            
            if response.status_code == 200:
                result = response.json()
                documents = result.get('documents', [])
                metadatas = result.get('metadatas', [])
                embeddings = result.get('embeddings', [])
                
                # ChromaDB API returns: documents=["content"], metadatas=[{meta}], embeddings=[[0.1, 0.2]]
                if len(documents) > 0 and documents[0]:
                    return {
                        'exists': True,
                        'content': documents[0],  # First document content
                        'metadata': metadatas[0] if metadatas and len(metadatas) > 0 else {},  # First metadata object
                        'embeddings': embeddings[0] if embeddings and len(embeddings) > 0 else None  # First embedding array
                    }
            
            return {'exists': False}
        except Exception as e:
            self.log(f"      Load balancer verification failed: {str(e)} ({type(e).__name__})")
            return {'exists': False} 