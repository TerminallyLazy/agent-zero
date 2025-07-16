/**
 * WebGPU Memory Manager for Agent Zero WebLLM Integration
 * 
 * Provides advanced memory management, monitoring, and optimization
 * for WebGPU-accelerated AI model inference.
 */

class WebGPUMemoryManager {
    constructor() {
        this.device = null;
        this.adapter = null;
        this.memoryStats = {
            totalMemory: 0,
            usedMemory: 0,
            availableMemory: 0,
            peakMemory: 0,
            buffers: new Map(),
            allocations: [],
            garbageCollections: 0
        };
        this.memoryThresholds = {
            warning: 0.75,  // 75% memory usage warning
            critical: 0.90, // 90% memory usage critical
            cleanup: 0.85   // 85% memory usage triggers cleanup
        };
        this.monitoring = {
            enabled: false,
            interval: null,
            frequency: 1000, // Monitor every second
            history: [],
            maxHistoryLength: 300 // 5 minutes at 1 second intervals
        };
        this.optimizations = {
            autoCleanup: true,
            bufferReuse: true,
            memoryDefragmentation: true,
            adaptiveQuality: true
        };
        this.callbacks = {
            onWarning: null,
            onCritical: null,
            onCleanup: null,
            onUpdate: null
        };
    }

    /**
     * Initialize WebGPU memory manager
     */
    async initialize() {
        try {
            if (!navigator.gpu) {
                throw new Error('WebGPU not available');
            }

            // Request adapter with memory features
            this.adapter = await navigator.gpu.requestAdapter({
                powerPreference: 'high-performance'
            });

            if (!this.adapter) {
                throw new Error('WebGPU adapter not available');
            }

            // Request device with memory tracking features
            const requiredFeatures = [];
            const availableFeatures = this.adapter.features;
            
            // Add memory-related features if available
            if (availableFeatures.has('timestamp-query')) {
                requiredFeatures.push('timestamp-query');
            }

            this.device = await this.adapter.requestDevice({
                requiredFeatures,
                requiredLimits: {
                    maxStorageBufferBindingSize: this.adapter.limits.maxStorageBufferBindingSize,
                    maxBufferSize: this.adapter.limits.maxBufferSize
                }
            });

            // Set up device lost handler
            this.device.lost.then((info) => {
                this.handleDeviceLost(info);
            });

            // Initialize memory tracking
            await this.updateMemoryStats();
            console.log('WebGPU Memory Manager initialized successfully');
            
            return true;
        } catch (error) {
            console.error('Failed to initialize WebGPU Memory Manager:', error);
            return false;
        }
    }

    /**
     * Start memory monitoring
     */
    startMonitoring(frequency = 1000) {
        if (this.monitoring.enabled) {
            this.stopMonitoring();
        }

        this.monitoring.frequency = frequency;
        this.monitoring.enabled = true;
        
        this.monitoring.interval = setInterval(async () => {
            await this.updateMemoryStats();
            this.checkMemoryThresholds();
            this.recordMemoryHistory();
            
            if (this.callbacks.onUpdate) {
                this.callbacks.onUpdate(this.memoryStats);
            }
        }, frequency);

        console.log(`Memory monitoring started with ${frequency}ms frequency`);
    }

    /**
     * Stop memory monitoring
     */
    stopMonitoring() {
        if (this.monitoring.interval) {
            clearInterval(this.monitoring.interval);
            this.monitoring.interval = null;
        }
        this.monitoring.enabled = false;
        console.log('Memory monitoring stopped');
    }

    /**
     * Update memory statistics
     */
    async updateMemoryStats() {
        try {
            // Get basic memory info
            if (this.adapter && this.adapter.info) {
                this.memoryStats.totalMemory = this.adapter.info.memorySize || 0;
            }

            // Estimate used memory from active buffers
            let usedMemory = 0;
            for (const [id, buffer] of this.memoryStats.buffers) {
                if (buffer.size) {
                    usedMemory += buffer.size;
                }
            }
            this.memoryStats.usedMemory = usedMemory;
            this.memoryStats.availableMemory = Math.max(0, this.memoryStats.totalMemory - usedMemory);

            // Update peak memory
            if (usedMemory > this.memoryStats.peakMemory) {
                this.memoryStats.peakMemory = usedMemory;
            }

            // Try to get more accurate memory info from performance APIs
            await this.updateAdvancedMemoryStats();

        } catch (error) {
            console.warn('Failed to update memory stats:', error);
        }
    }

    /**
     * Update advanced memory statistics using performance APIs
     */
    async updateAdvancedMemoryStats() {
        try {
            // Use Performance.measureUserAgentSpecificMemory if available
            if ('measureUserAgentSpecificMemory' in performance) {
                const memoryInfo = await performance.measureUserAgentSpecificMemory();
                if (memoryInfo && memoryInfo.bytes) {
                    // Extract GPU memory usage if available
                    for (const attribution of memoryInfo.breakdown) {
                        if (attribution.attribution && 
                            attribution.attribution.some(attr => attr.container?.src?.includes('webgpu'))) {
                            this.memoryStats.usedMemory = attribution.bytes;
                            break;
                        }
                    }
                }
            }

            // Fallback to legacy performance.memory
            if ('memory' in performance) {
                const memInfo = performance.memory;
                // Estimate GPU memory as a portion of total used memory
                const totalUsed = memInfo.usedJSHeapSize;
                const estimatedGPU = totalUsed * 0.3; // Rough estimate
                
                if (this.memoryStats.usedMemory === 0) {
                    this.memoryStats.usedMemory = estimatedGPU;
                }
            }
        } catch (error) {
            console.warn('Advanced memory stats not available:', error);
        }
    }

    /**
     * Register a buffer for tracking
     */
    registerBuffer(id, buffer, size, type = 'unknown') {
        const bufferInfo = {
            id,
            buffer,
            size,
            type,
            timestamp: Date.now(),
            lastAccessed: Date.now()
        };

        this.memoryStats.buffers.set(id, bufferInfo);
        this.memoryStats.allocations.push({
            id,
            size,
            type,
            action: 'allocate',
            timestamp: Date.now()
        });

        console.debug(`Buffer registered: ${id} (${this.formatBytes(size)}, ${type})`);
    }

    /**
     * Unregister a buffer
     */
    unregisterBuffer(id) {
        const bufferInfo = this.memoryStats.buffers.get(id);
        if (bufferInfo) {
            this.memoryStats.buffers.delete(id);
            this.memoryStats.allocations.push({
                id,
                size: bufferInfo.size,
                type: bufferInfo.type,
                action: 'deallocate',
                timestamp: Date.now()
            });

            console.debug(`Buffer unregistered: ${id} (${this.formatBytes(bufferInfo.size)})`);
        }
    }

    /**
     * Check memory thresholds and trigger warnings/cleanup
     */
    checkMemoryThresholds() {
        if (this.memoryStats.totalMemory === 0) return;

        const usageRatio = this.memoryStats.usedMemory / this.memoryStats.totalMemory;

        if (usageRatio >= this.memoryThresholds.critical) {
            this.handleCriticalMemory();
        } else if (usageRatio >= this.memoryThresholds.cleanup && this.optimizations.autoCleanup) {
            this.performCleanup();
        } else if (usageRatio >= this.memoryThresholds.warning) {
            this.handleMemoryWarning();
        }
    }

    /**
     * Handle memory warning
     */
    handleMemoryWarning() {
        console.warn('WebGPU memory usage is high:', this.getMemoryUsagePercent() + '%');
        
        if (this.callbacks.onWarning) {
            this.callbacks.onWarning(this.memoryStats);
        }
    }

    /**
     * Handle critical memory situation
     */
    handleCriticalMemory() {
        console.error('WebGPU memory usage is critical:', this.getMemoryUsagePercent() + '%');
        
        // Force immediate cleanup
        this.performAggressiveCleanup();
        
        if (this.callbacks.onCritical) {
            this.callbacks.onCritical(this.memoryStats);
        }
    }

    /**
     * Perform memory cleanup
     */
    performCleanup() {
        console.log('Performing WebGPU memory cleanup...');

        let freedMemory = 0;

        // Clean up old unused buffers
        const now = Date.now();
        const maxAge = 5 * 60 * 1000; // 5 minutes

        for (const [id, bufferInfo] of this.memoryStats.buffers) {
            if (now - bufferInfo.lastAccessed > maxAge) {
                try {
                    if (bufferInfo.buffer && typeof bufferInfo.buffer.destroy === 'function') {
                        bufferInfo.buffer.destroy();
                    }
                    freedMemory += bufferInfo.size;
                    this.unregisterBuffer(id);
                } catch (error) {
                    console.warn(`Failed to cleanup buffer ${id}:`, error);
                }
            }
        }

        // Suggest garbage collection
        this.requestGarbageCollection();

        console.log(`Memory cleanup completed. Freed ${this.formatBytes(freedMemory)}`);

        if (this.callbacks.onCleanup) {
            this.callbacks.onCleanup({ freedMemory, type: 'regular' });
        }
    }

    /**
     * Perform aggressive memory cleanup
     */
    performAggressiveCleanup() {
        console.log('Performing aggressive WebGPU memory cleanup...');

        let freedMemory = 0;

        // Clean up all non-essential buffers
        for (const [id, bufferInfo] of this.memoryStats.buffers) {
            if (bufferInfo.type !== 'model' && bufferInfo.type !== 'critical') {
                try {
                    if (bufferInfo.buffer && typeof bufferInfo.buffer.destroy === 'function') {
                        bufferInfo.buffer.destroy();
                    }
                    freedMemory += bufferInfo.size;
                    this.unregisterBuffer(id);
                } catch (error) {
                    console.warn(`Failed to cleanup buffer ${id}:`, error);
                }
            }
        }

        // Force garbage collection multiple times
        for (let i = 0; i < 3; i++) {
            this.requestGarbageCollection();
        }

        console.log(`Aggressive cleanup completed. Freed ${this.formatBytes(freedMemory)}`);

        if (this.callbacks.onCleanup) {
            this.callbacks.onCleanup({ freedMemory, type: 'aggressive' });
        }
    }

    /**
     * Request garbage collection
     */
    requestGarbageCollection() {
        try {
            // Request explicit garbage collection if available
            if (window.gc) {
                window.gc();
                this.memoryStats.garbageCollections++;
            }
            
            // Alternative methods to encourage GC
            if ('performance' in window && 'measureUserAgentSpecificMemory' in performance) {
                performance.measureUserAgentSpecificMemory().catch(() => {});
            }
        } catch (error) {
            console.debug('Garbage collection request failed:', error);
        }
    }

    /**
     * Handle device lost event
     */
    handleDeviceLost(info) {
        console.error('WebGPU device lost:', info.reason, info.message);
        
        // Clear all buffer references
        this.memoryStats.buffers.clear();
        this.device = null;
        
        // Stop monitoring
        this.stopMonitoring();
        
        // Attempt to reinitialize after a delay
        setTimeout(() => {
            this.initialize();
        }, 1000);
    }

    /**
     * Record memory usage in history
     */
    recordMemoryHistory() {
        const snapshot = {
            timestamp: Date.now(),
            usedMemory: this.memoryStats.usedMemory,
            totalMemory: this.memoryStats.totalMemory,
            usagePercent: this.getMemoryUsagePercent(),
            bufferCount: this.memoryStats.buffers.size
        };

        this.monitoring.history.push(snapshot);

        // Limit history size
        if (this.monitoring.history.length > this.monitoring.maxHistoryLength) {
            this.monitoring.history.shift();
        }
    }

    /**
     * Get memory usage percentage
     */
    getMemoryUsagePercent() {
        if (this.memoryStats.totalMemory === 0) return 0;
        return Math.round((this.memoryStats.usedMemory / this.memoryStats.totalMemory) * 100);
    }

    /**
     * Get memory statistics
     */
    getStats() {
        return {
            ...this.memoryStats,
            usagePercent: this.getMemoryUsagePercent(),
            monitoring: this.monitoring,
            thresholds: this.memoryThresholds,
            optimizations: this.optimizations
        };
    }

    /**
     * Get memory history for visualization
     */
    getMemoryHistory() {
        return this.monitoring.history;
    }

    /**
     * Set memory thresholds
     */
    setThresholds(warning, critical, cleanup) {
        this.memoryThresholds.warning = Math.max(0, Math.min(1, warning));
        this.memoryThresholds.critical = Math.max(0, Math.min(1, critical));
        this.memoryThresholds.cleanup = Math.max(0, Math.min(1, cleanup));
    }

    /**
     * Set optimization options
     */
    setOptimizations(options) {
        this.optimizations = { ...this.optimizations, ...options };
    }

    /**
     * Set event callbacks
     */
    setCallbacks(callbacks) {
        this.callbacks = { ...this.callbacks, ...callbacks };
    }

    /**
     * Format bytes for display
     */
    formatBytes(bytes) {
        if (bytes === 0) return '0 B';
        const k = 1024;
        const sizes = ['B', 'KB', 'MB', 'GB'];
        const i = Math.floor(Math.log(bytes) / Math.log(k));
        return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i];
    }

    /**
     * Get device capabilities
     */
    getDeviceCapabilities() {
        if (!this.adapter) return null;

        return {
            limits: this.adapter.limits,
            features: Array.from(this.adapter.features),
            isFallbackAdapter: this.adapter.isFallbackAdapter,
            info: this.adapter.info || {}
        };
    }

    /**
     * Optimize for model loading
     */
    optimizeForModelLoading(modelSize) {
        console.log(`Optimizing WebGPU for model loading: ${this.formatBytes(modelSize)}`);
        
        // Check if we have enough memory
        const requiredMemory = modelSize * 1.5; // Add 50% overhead
        if (this.memoryStats.availableMemory < requiredMemory) {
            console.warn('Insufficient memory for model, performing cleanup...');
            this.performAggressiveCleanup();
        }

        // Adjust quality settings if adaptive quality is enabled
        if (this.optimizations.adaptiveQuality) {
            const usageRatio = this.memoryStats.usedMemory / this.memoryStats.totalMemory;
            if (usageRatio > 0.6) {
                console.log('High memory usage detected, suggesting lower quality settings');
                return {
                    suggestedQuality: 'low',
                    suggestedBatchSize: 1,
                    suggestedPrecision: 'fp16'
                };
            }
        }

        return {
            suggestedQuality: 'high',
            suggestedBatchSize: 4,
            suggestedPrecision: 'fp32'
        };
    }

    /**
     * Clean up and destroy the memory manager
     */
    destroy() {
        this.stopMonitoring();
        
        // Clean up all tracked buffers
        for (const [id, bufferInfo] of this.memoryStats.buffers) {
            try {
                if (bufferInfo.buffer && typeof bufferInfo.buffer.destroy === 'function') {
                    bufferInfo.buffer.destroy();
                }
            } catch (error) {
                console.warn(`Failed to destroy buffer ${id}:`, error);
            }
        }
        
        this.memoryStats.buffers.clear();
        this.device = null;
        this.adapter = null;
        
        console.log('WebGPU Memory Manager destroyed');
    }
}

// Export for use in other modules
if (typeof module !== 'undefined' && module.exports) {
    module.exports = WebGPUMemoryManager;
} else {
    window.WebGPUMemoryManager = WebGPUMemoryManager;
}