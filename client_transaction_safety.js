/**
 * Client-Side Transaction Safety for ChromaDB Load Balancer
 * Provides automatic retry and recovery for operations during timing gaps
 */

class TransactionSafetyClient {
    constructor(loadBalancerUrl, options = {}) {
        this.loadBalancerUrl = loadBalancerUrl.replace(/\/$/, ''); // Remove trailing slash
        this.options = {
            maxRetries: options.maxRetries || 3,
            initialRetryDelay: options.initialRetryDelay || 30000, // 30 seconds
            maxRetryDelay: options.maxRetryDelay || 120000, // 2 minutes
            pollInterval: options.pollInterval || 5000, // 5 seconds
            pollTimeout: options.pollTimeout || 300000, // 5 minutes
            ...options
        };
        
        this.pendingTransactions = new Map();
        this.eventListeners = {};
    }
    
    /**
     * Generate a unique transaction ID for tracking
     */
    generateTransactionId() {
        return `tx_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`;
    }
    
    /**
     * Add event listener for transaction events
     */
    on(event, callback) {
        if (!this.eventListeners[event]) {
            this.eventListeners[event] = [];
        }
        this.eventListeners[event].push(callback);
    }
    
    /**
     * Emit event to listeners
     */
    emit(event, data) {
        if (this.eventListeners[event]) {
            this.eventListeners[event].forEach(callback => {
                try {
                    callback(data);
                } catch (error) {
                    console.error('Event listener error:', error);
                }
            });
        }
    }
    
    /**
     * Upload file with transaction safety
     */
    async uploadFileWithSafety(file, collectionName = 'global', metadata = {}) {
        const transactionId = this.generateTransactionId();
        
        try {
            this.emit('transaction:started', {
                transactionId,
                operation: 'file_upload',
                file: file.name,
                collection: collectionName
            });
            
            const result = await this.executeWithRetry(
                () => this.uploadFile(file, collectionName, metadata),
                transactionId,
                'file_upload'
            );
            
            this.emit('transaction:completed', {
                transactionId,
                operation: 'file_upload',
                result
            });
            
            return result;
            
        } catch (error) {
            this.emit('transaction:failed', {
                transactionId,
                operation: 'file_upload',
                error: error.message
            });
            throw error;
        }
    }
    
    /**
     * Delete file with transaction safety
     */
    async deleteFileWithSafety(fileId, collectionName = 'global') {
        const transactionId = this.generateTransactionId();
        
        try {
            this.emit('transaction:started', {
                transactionId,
                operation: 'file_delete',
                fileId,
                collection: collectionName
            });
            
            const result = await this.executeWithRetry(
                () => this.deleteFile(fileId, collectionName),
                transactionId,
                'file_delete'
            );
            
            this.emit('transaction:completed', {
                transactionId,
                operation: 'file_delete',
                result
            });
            
            return result;
            
        } catch (error) {
            this.emit('transaction:failed', {
                transactionId,
                operation: 'file_delete',
                error: error.message
            });
            throw error;
        }
    }
    
    /**
     * Execute operation with automatic retry and recovery
     */
    async executeWithRetry(operation, transactionId, operationType) {
        let lastError = null;
        
        for (let attempt = 0; attempt < this.options.maxRetries; attempt++) {
            try {
                // Add transaction tracking headers
                const headers = {
                    'X-Transaction-ID': transactionId,
                    'X-Operation-Type': operationType,
                    'X-Attempt': attempt + 1
                };
                
                const result = await operation(headers);
                
                // Remove from pending transactions on success
                this.pendingTransactions.delete(transactionId);
                
                return result;
                
            } catch (error) {
                lastError = error;
                
                console.warn(`Attempt ${attempt + 1} failed for transaction ${transactionId}:`, error.message);
                
                // Check if this looks like a timing gap error
                if (this.isTimingGapError(error)) {
                    console.info(`Timing gap detected for transaction ${transactionId}, will retry...`);
                    
                    // Store transaction for recovery
                    this.pendingTransactions.set(transactionId, {
                        operation,
                        operationType,
                        startTime: Date.now(),
                        attempts: attempt + 1,
                        lastError: error.message
                    });
                    
                    this.emit('transaction:timing_gap', {
                        transactionId,
                        operation: operationType,
                        attempt: attempt + 1,
                        error: error.message
                    });
                    
                    // Wait before retry with exponential backoff
                    const delay = Math.min(
                        this.options.initialRetryDelay * Math.pow(2, attempt),
                        this.options.maxRetryDelay
                    );
                    
                    console.info(`Waiting ${delay/1000}s before retry...`);
                    await this.sleep(delay);
                    
                } else {
                    // Non-timing gap error, throw immediately
                    throw error;
                }
            }
        }
        
        // All retries exhausted
        this.pendingTransactions.delete(transactionId);
        throw new Error(`Transaction failed after ${this.options.maxRetries} attempts. Last error: ${lastError.message}`);
    }
    
    /**
     * Check if error is likely a timing gap issue
     */
    isTimingGapError(error) {
        const errorMessage = error.message.toLowerCase();
        const statusCode = error.status || error.statusCode;
        
        // Check for timing gap indicators
        return (
            statusCode === 503 || // Service unavailable
            statusCode === 502 || // Bad gateway
            errorMessage.includes('service temporarily unavailable') ||
            errorMessage.includes('connection refused') ||
            errorMessage.includes('connection timeout') ||
            errorMessage.includes('bad gateway') ||
            errorMessage.includes('timing gap')
        );
    }
    
    /**
     * Poll for transaction completion (for server-side recovery)
     */
    async pollForTransactionCompletion(transactionId) {
        const startTime = Date.now();
        
        while (Date.now() - startTime < this.options.pollTimeout) {
            try {
                const response = await fetch(
                    `${this.loadBalancerUrl}/transaction/safety/transaction/${transactionId}`,
                    { method: 'GET' }
                );
                
                if (response.ok) {
                    const transactionData = await response.json();
                    
                    if (transactionData.status === 'COMPLETED' || transactionData.status === 'RECOVERED') {
                        console.info(`Transaction ${transactionId} completed via server-side recovery`);
                        
                        this.emit('transaction:recovered', {
                            transactionId,
                            status: transactionData.status,
                            recoveryTime: Date.now() - startTime
                        });
                        
                        return transactionData;
                    } else if (transactionData.status === 'ABANDONED') {
                        throw new Error(`Transaction ${transactionId} was abandoned by server`);
                    }
                }
                
                // Wait before next poll
                await this.sleep(this.options.pollInterval);
                
            } catch (error) {
                console.warn(`Polling error for transaction ${transactionId}:`, error.message);
                await this.sleep(this.options.pollInterval);
            }
        }
        
        throw new Error(`Transaction ${transactionId} polling timeout`);
    }
    
    /**
     * Upload file to ChromaDB via load balancer
     */
    async uploadFile(file, collectionName, metadata, headers = {}) {
        // Convert file to documents for ChromaDB
        const documents = await this.fileToDocuments(file, metadata);
        
        // Upload documents
        const response = await fetch(
            `${this.loadBalancerUrl}/api/v2/tenants/default_tenant/databases/default_database/collections/${collectionName}/add`,
            {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    ...headers
                },
                body: JSON.stringify(documents)
            }
        );
        
        if (!response.ok) {
            const errorText = await response.text();
            throw new Error(`Upload failed: ${response.status} ${errorText}`);
        }
        
        return await response.json();
    }
    
    /**
     * Delete file from ChromaDB via load balancer
     */
    async deleteFile(fileId, collectionName, headers = {}) {
        const response = await fetch(
            `${this.loadBalancerUrl}/api/v2/tenants/default_tenant/databases/default_database/collections/${collectionName}/delete`,
            {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    ...headers
                },
                body: JSON.stringify({
                    where: { "file_id": fileId }
                })
            }
        );
        
        if (!response.ok) {
            const errorText = await response.text();
            throw new Error(`Delete failed: ${response.status} ${errorText}`);
        }
        
        return await response.json();
    }
    
    /**
     * Convert file to ChromaDB documents format
     */
    async fileToDocuments(file, metadata = {}) {
        // Simple text extraction - in production, use proper document processing
        const text = await file.text();
        const chunks = this.chunkText(text, 1000); // 1000 char chunks
        
        const documents = {
            ids: [],
            documents: [],
            metadatas: []
        };
        
        chunks.forEach((chunk, index) => {
            const docId = `${file.name}_chunk_${index}`;
            documents.ids.push(docId);
            documents.documents.push(chunk);
            documents.metadatas.push({
                file_name: file.name,
                file_size: file.size,
                file_type: file.type,
                chunk_index: index,
                total_chunks: chunks.length,
                upload_time: new Date().toISOString(),
                ...metadata
            });
        });
        
        return documents;
    }
    
    /**
     * Chunk text into smaller pieces
     */
    chunkText(text, chunkSize = 1000) {
        const chunks = [];
        for (let i = 0; i < text.length; i += chunkSize) {
            chunks.push(text.slice(i, i + chunkSize));
        }
        return chunks;
    }
    
    /**
     * Get pending transactions
     */
    getPendingTransactions() {
        return Array.from(this.pendingTransactions.entries()).map(([id, data]) => ({
            transactionId: id,
            ...data
        }));
    }
    
    /**
     * Get transaction safety system status
     */
    async getSystemStatus() {
        try {
            const response = await fetch(`${this.loadBalancerUrl}/transaction/safety/status`);
            if (response.ok) {
                return await response.json();
            } else {
                throw new Error(`Status check failed: ${response.status}`);
            }
        } catch (error) {
            console.error('Failed to get system status:', error);
            return { available: false, error: error.message };
        }
    }
    
    /**
     * Sleep for specified milliseconds
     */
    sleep(ms) {
        return new Promise(resolve => setTimeout(resolve, ms));
    }
}

/**
 * UI Helper class for displaying transaction safety status
 */
class TransactionSafetyUI {
    constructor(client, containerId) {
        this.client = client;
        this.container = document.getElementById(containerId);
        this.setupEventListeners();
        this.createUI();
    }
    
    setupEventListeners() {
        this.client.on('transaction:started', (data) => {
            this.addTransactionToUI(data.transactionId, data.operation, 'PROCESSING');
        });
        
        this.client.on('transaction:completed', (data) => {
            this.updateTransactionInUI(data.transactionId, 'COMPLETED');
        });
        
        this.client.on('transaction:failed', (data) => {
            this.updateTransactionInUI(data.transactionId, 'FAILED', data.error);
        });
        
        this.client.on('transaction:timing_gap', (data) => {
            this.updateTransactionInUI(data.transactionId, 'RETRYING', `Attempt ${data.attempt}`);
        });
        
        this.client.on('transaction:recovered', (data) => {
            this.updateTransactionInUI(data.transactionId, 'RECOVERED');
        });
    }
    
    createUI() {
        this.container.innerHTML = `
            <div class="transaction-safety-panel">
                <h3>Transaction Safety Status</h3>
                <div class="system-status" id="system-status">
                    <span class="loading">Checking system status...</span>
                </div>
                <div class="transactions-list" id="transactions-list">
                    <h4>Active Transactions</h4>
                    <div id="transaction-items"></div>
                </div>
            </div>
        `;
        
        this.updateSystemStatus();
        
        // Refresh system status every 30 seconds
        setInterval(() => this.updateSystemStatus(), 30000);
    }
    
    async updateSystemStatus() {
        const statusElement = document.getElementById('system-status');
        
        try {
            const status = await this.client.getSystemStatus();
            
            if (status.available) {
                statusElement.innerHTML = `
                    <span class="status-indicator available">●</span>
                    Transaction Safety: Active
                    <small>(Recovery service running: ${status.service_running})</small>
                `;
                statusElement.className = 'system-status available';
            } else {
                statusElement.innerHTML = `
                    <span class="status-indicator unavailable">●</span>
                    Transaction Safety: Unavailable
                    <small>${status.message || status.error || ''}</small>
                `;
                statusElement.className = 'system-status unavailable';
            }
        } catch (error) {
            statusElement.innerHTML = `
                <span class="status-indicator error">●</span>
                Transaction Safety: Error
                <small>${error.message}</small>
            `;
            statusElement.className = 'system-status error';
        }
    }
    
    addTransactionToUI(transactionId, operation, status) {
        const container = document.getElementById('transaction-items');
        const element = document.createElement('div');
        element.id = `tx-${transactionId}`;
        element.className = `transaction-item ${status.toLowerCase()}`;
        element.innerHTML = `
            <div class="transaction-header">
                <span class="transaction-id">${transactionId.substring(0, 8)}...</span>
                <span class="transaction-operation">${operation}</span>
                <span class="transaction-status">${status}</span>
            </div>
            <div class="transaction-details">
                <small>Started: ${new Date().toLocaleTimeString()}</small>
            </div>
        `;
        
        container.appendChild(element);
        
        // Auto-remove completed transactions after 10 seconds
        if (status === 'COMPLETED' || status === 'FAILED') {
            setTimeout(() => {
                if (element.parentNode) {
                    element.parentNode.removeChild(element);
                }
            }, 10000);
        }
    }
    
    updateTransactionInUI(transactionId, status, details = '') {
        const element = document.getElementById(`tx-${transactionId}`);
        if (element) {
            element.className = `transaction-item ${status.toLowerCase()}`;
            const statusSpan = element.querySelector('.transaction-status');
            statusSpan.textContent = status;
            
            if (details) {
                const detailsDiv = element.querySelector('.transaction-details');
                detailsDiv.innerHTML += `<br><small>${details}</small>`;
            }
        }
    }
}

// Export for use in applications
if (typeof module !== 'undefined' && module.exports) {
    module.exports = { TransactionSafetyClient, TransactionSafetyUI };
} else if (typeof window !== 'undefined') {
    window.TransactionSafetyClient = TransactionSafetyClient;
    window.TransactionSafetyUI = TransactionSafetyUI;
} 