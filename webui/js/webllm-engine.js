/**
 * WebLLM Engine for Agent Zero
 * 
 * Provides client-side AI inference using WebLLM with WebGPU acceleration.
 * Integrates with Agent Zero's existing Alpine.js architecture.
 */

// Import WebLLM functions
let CreateMLCEngine;

// Initialize WebLLM imports when available
async function initWebLLM() {
    try {
        if (typeof window !== 'undefined' && window.CreateMLCEngine) {
            CreateMLCEngine = window.CreateMLCEngine;
            return true;
        }
        
        // Try dynamic import if module system is available
        const webllm = await import('https://cdn.jsdelivr.net/npm/@mlc-ai/web-llm@0.2.46/lib/index.js');
        CreateMLCEngine = webllm.CreateMLCEngine;
        window.CreateMLCEngine = CreateMLCEngine;
        return true;
    } catch (error) {
        console.warn('WebLLM library not available:', error);
        return false;
    }
}

class WebLLMEngine {
    constructor() {
        this.engine = null;
        this.isLoading = false;
        this.isReady = false;
        this.currentModel = null;
        
        // Define supported models using WebLLM's built-in model IDs
        // Starting with the most commonly available models
        this.supportedModels = [
            "TinyLlama-1.1B-Chat-v0.4-q4f32_1-MLC",
            "Llama-3.2-1B-Instruct-q4f32_1-MLC",
            "Llama-3.2-3B-Instruct-q4f32_1-MLC"
        ];
        
        // Use WebLLM's built-in model configurations instead of custom URLs
        // This ensures compatibility with the actual WebLLM model registry
        this.modelConfig = {};
        this.progressCallback = null;
        this.compatibility = this.checkCompatibility();
        this.memoryManager = null;
        this.performanceMetrics = {
            tokensPerSecond: 0,
            latency: 0,
            memoryEfficiency: 0,
            lastInferenceTime: 0
        };
        
        // Bind methods
        this.loadModel = this.loadModel.bind(this);
        this.generateResponse = this.generateResponse.bind(this);
        this.streamResponse = this.streamResponse.bind(this);
    }

    /**
     * Check browser compatibility for WebLLM
     */
    checkCompatibility() {
        const compatibility = {
            webgpu: false,
            webassembly: false,
            supported: false,
            limitations: [],
            browserInfo: this.getBrowserInfo(),
            instructions: []
        };

        // Check WebGPU support
        if ('gpu' in navigator) {
            compatibility.webgpu = true;
        } else {
            compatibility.limitations.push('WebGPU not available in this browser');
            compatibility.instructions = this.getWebGPUInstructions();
        }

        // Check WebAssembly support
        if (typeof WebAssembly === 'object' && typeof WebAssembly.instantiate === 'function') {
            compatibility.webassembly = true;
        } else {
            compatibility.limitations.push('WebAssembly not supported');
        }

        // Check overall support (WebAssembly is minimum requirement)
        compatibility.supported = compatibility.webassembly;

        // Add helpful information
        if (!compatibility.webgpu) {
            compatibility.limitations.push('GPU acceleration unavailable - CPU-only mode will be slower');
            compatibility.limitations.push('Visit webgpureport.org to check WebGPU status');
        }

        // Check memory availability (approximate)
        if (navigator.deviceMemory && navigator.deviceMemory < 4) {
            compatibility.limitations.push('Device may have insufficient memory for larger models');
        }

        return compatibility;
    }

    /**
     * Get browser information for WebGPU troubleshooting
     */
    getBrowserInfo() {
        const ua = navigator.userAgent;
        const browser = {
            name: 'Unknown',
            version: 'Unknown',
            webgpuSupport: 'Unknown'
        };

        if (ua.includes('Chrome')) {
            const match = ua.match(/Chrome\/(\d+)/);
            browser.name = 'Chrome';
            browser.version = match ? match[1] : 'Unknown';
            browser.webgpuSupport = parseInt(browser.version) >= 113 ? 'Should be supported' : 'Requires Chrome 113+';
        } else if (ua.includes('Firefox')) {
            const match = ua.match(/Firefox\/(\d+)/);
            browser.name = 'Firefox';
            browser.version = match ? match[1] : 'Unknown';
            browser.webgpuSupport = parseInt(browser.version) >= 113 ? 'Behind flag' : 'Requires Firefox 113+';
        } else if (ua.includes('Safari')) {
            browser.name = 'Safari';
            browser.webgpuSupport = 'Requires Safari Technology Preview or macOS 14+';
        }

        return browser;
    }

    /**
     * Get WebGPU enabling instructions
     */
    getWebGPUInstructions() {
        const browser = this.getBrowserInfo();
        const instructions = [];

        if (browser.name === 'Chrome') {
            instructions.push('1. Update to Chrome 113 or later');
            instructions.push('2. Go to chrome://flags/');
            instructions.push('3. Enable "Unsafe WebGPU" flag');
            instructions.push('4. Restart Chrome');
        } else if (browser.name === 'Firefox') {
            instructions.push('1. Update to Firefox 113 or later');
            instructions.push('2. Go to about:config');
            instructions.push('3. Set dom.webgpu.enabled to true');
            instructions.push('4. Restart Firefox');
        } else if (browser.name === 'Safari') {
            instructions.push('1. Update to macOS 14+ or use Safari Technology Preview');
            instructions.push('2. Enable WebGPU in Develop menu > Experimental Features');
        } else {
            instructions.push('Use Chrome 113+ or Firefox 113+ with WebGPU enabled');
        }

        instructions.push('5. Ensure GPU drivers are up to date');
        instructions.push('6. Check webgpureport.org for status');

        return instructions;
    }

    /**
     * Initialize WebLLM engine
     */
    async initialize() {
        if (!this.compatibility.supported) {
            throw new Error('WebLLM is not supported in this browser: ' + this.compatibility.limitations.join(', '));
        }

        try {
            // Initialize WebLLM imports
            const webllmAvailable = await initWebLLM();
            if (!webllmAvailable) {
                throw new Error('WebLLM library not available. Please check your internet connection.');
            }

            // Initialize memory manager if WebGPU is supported
            if (this.compatibility.webgpu && window.WebGPUMemoryManager) {
                this.memoryManager = new window.WebGPUMemoryManager();
                const memoryInitialized = await this.memoryManager.initialize();
                
                if (memoryInitialized) {
                    // Set up memory event callbacks
                    this.memoryManager.setCallbacks({
                        onWarning: (stats) => this.handleMemoryWarning(stats),
                        onCritical: (stats) => this.handleMemoryCritical(stats),
                        onCleanup: (info) => this.handleMemoryCleanup(info),
                        onUpdate: (stats) => this.updatePerformanceMetrics(stats)
                    });

                    // Start memory monitoring
                    this.memoryManager.startMonitoring(2000); // Monitor every 2 seconds
                    console.log('WebGPU Memory Manager initialized and monitoring started');
                } else {
                    console.warn('WebGPU Memory Manager initialization failed, continuing without memory management');
                }
            }

            console.log('WebLLM engine initialized successfully');
            return true;
        } catch (error) {
            console.error('Failed to initialize WebLLM engine:', error);
            throw error;
        }
    }

    /**
     * Load a specific model
     */
    async loadModel(modelId, options = {}) {
        if (this.isLoading) {
            throw new Error('Another model is currently loading');
        }

        if (!this.supportedModels.includes(modelId)) {
            throw new Error(`Model ${modelId} is not in the supported models list`);
        }

        this.isLoading = true;
        this.isReady = false;

        try {
            // Get model size estimate for memory optimization
            const modelSizeEstimate = this.getModelSizeBytes(modelId);
            
            // Optimize memory for model loading
            if (this.memoryManager) {
                const optimization = this.memoryManager.optimizeForModelLoading(modelSizeEstimate);
                console.log('Memory optimization suggestions:', optimization);
                
                // Apply optimization suggestions to options
                if (optimization.suggestedQuality === 'low') {
                    options.lowMemoryMode = true;
                }
            }

            // Configure engine options - let WebLLM use its built-in model registry
            const engineConfig = {
                initProgressCallback: (report) => {
                    if (this.progressCallback) {
                        this.progressCallback({
                            progress: report.progress || 0,
                            timeElapsed: report.timeElapsed || 0,
                            text: report.text || 'Loading model...',
                            phase: report.phase || 'unknown'
                        });
                    }
                    console.log('Model loading progress:', report);
                    
                    // Update memory tracking during loading
                    if (this.memoryManager) {
                        this.memoryManager.updateMemoryStats();
                    }
                },
                // Don't pass custom appConfig - let WebLLM use its built-in model registry
                ...options
            };

            // Register model buffer for tracking
            if (this.memoryManager) {
                this.memoryManager.registerBuffer(
                    `model_${modelId}`,
                    null, // Buffer will be created by WebLLM
                    modelSizeEstimate,
                    'model'
                );
            }

            // Create MLCEngine instance with proper configuration
            this.engine = await CreateMLCEngine(modelId, engineConfig);
            
            this.currentModel = modelId;
            this.isReady = true;
            this.isLoading = false;

            console.log(`Model ${modelId} loaded successfully`);
            
            // Update performance metrics
            this.updatePerformanceMetrics();
            
            return true;

        } catch (error) {
            this.isLoading = false;
            this.isReady = false;
            
            // Clean up registered buffer on failure
            if (this.memoryManager) {
                this.memoryManager.unregisterBuffer(`model_${modelId}`);
            }
            
            console.error('Failed to load model:', error);
            throw error;
        }
    }

    /**
     * Generate a response (non-streaming)
     */
    async generateResponse(messages, options = {}) {
        if (!this.isReady || !this.engine) {
            throw new Error('Model not loaded. Call loadModel() first.');
        }

        try {
            const startTime = performance.now();

            // Register inference buffer if memory manager is available
            const inferenceId = `inference_${Date.now()}`;
            if (this.memoryManager) {
                const estimatedSize = this.estimateInferenceMemory(messages, options);
                this.memoryManager.registerBuffer(inferenceId, null, estimatedSize, 'inference');
            }

            const response = await this.engine.chat.completions.create({
                messages: this.formatMessages(messages),
                temperature: options.temperature || 0.7,
                max_tokens: options.max_tokens || 1000,
                stream: false,
                ...options
            });

            const endTime = performance.now();
            const inferenceTime = endTime - startTime;

            // Update performance metrics
            this.updateInferenceMetrics(response, inferenceTime);

            // Clean up inference buffer
            if (this.memoryManager) {
                this.memoryManager.unregisterBuffer(inferenceId);
            }

            return {
                content: response.choices[0].message.content,
                usage: response.usage || null,
                inferenceTime: inferenceTime,
                tokensPerSecond: this.performanceMetrics.tokensPerSecond
            };

        } catch (error) {
            // Clean up inference buffer on error
            if (this.memoryManager) {
                this.memoryManager.unregisterBuffer(inferenceId);
            }
            console.error('Failed to generate response:', error);
            throw error;
        }
    }

    /**
     * Generate a streaming response
     */
    async* streamResponse(messages, options = {}) {
        if (!this.isReady || !this.engine) {
            throw new Error('Model not loaded. Call loadModel() first.');
        }

        try {
            const stream = await this.engine.chat.completions.create({
                messages: this.formatMessages(messages),
                temperature: options.temperature || 0.7,
                max_tokens: options.max_tokens || 1000,
                stream: true,
                stream_options: { include_usage: true },
                ...options
            });

            let fullResponse = "";
            for await (const chunk of stream) {
                const delta = chunk.choices[0]?.delta?.content || "";
                if (delta) {
                    fullResponse += delta;
                    yield {
                        delta: delta,
                        content: fullResponse,
                        usage: chunk.usage || null,
                        finished: chunk.choices[0]?.finish_reason !== null
                    };
                }
            }

        } catch (error) {
            console.error('Failed to stream response:', error);
            throw error;
        }
    }

    /**
     * Format messages for WebLLM
     */
    formatMessages(messages) {
        if (!Array.isArray(messages)) {
            throw new Error('Messages must be an array');
        }

        return messages.map(msg => {
            // Handle different message formats
            if (typeof msg === 'string') {
                return { role: 'user', content: msg };
            }
            
            if (msg.role && msg.content) {
                return {
                    role: msg.role,
                    content: msg.content
                };
            }

            throw new Error('Invalid message format');
        });
    }

    /**
     * Get current model information
     */
    getModelInfo() {
        return {
            currentModel: this.currentModel,
            isReady: this.isReady,
            isLoading: this.isLoading,
            supportedModels: this.supportedModels,
            compatibility: this.compatibility
        };
    }

    /**
     * Estimate memory usage for a model
     */
    estimateMemoryUsage(modelId) {
        // Rough estimates based on model size
        const memoryEstimates = {
            "Llama-3.2-3B-Instruct-q4f32_1-MLC": "~2.5GB",
            "Llama-3.2-1B-Instruct-q4f32_1-MLC": "~1.2GB",
            "gemma-2-2b-it-q4f32_1-MLC": "~1.8GB",
            "Phi-3.5-mini-instruct-q4f32_1-MLC": "~2.1GB",
            "TinyLlama-1.1B-Chat-v0.4-q4f32_1-MLC": "~1.0GB"
        };

        return memoryEstimates[modelId] || "Unknown";
    }

    /**
     * Unload current model to free memory
     */
    async unloadModel() {
        if (this.engine) {
            // Unregister model buffer
            if (this.memoryManager && this.currentModel) {
                this.memoryManager.unregisterBuffer(`model_${this.currentModel}`);
            }

            // Note: WebLLM doesn't have explicit unload, but we can null the reference
            this.engine = null;
            this.currentModel = null;
            this.isReady = false;
            
            // Perform memory cleanup
            if (this.memoryManager) {
                this.memoryManager.performCleanup();
            } else {
                // Fallback: suggest garbage collection
                if (window.gc) {
                    window.gc();
                }
            }

            console.log('Model unloaded and memory cleaned up');
        }
    }

    /**
     * Get model size in bytes for memory estimation
     */
    getModelSizeBytes(modelId) {
        const sizeMap = {
            "Llama-3.2-3B-Instruct-q4f32_1-MLC": 2.5 * 1024 * 1024 * 1024, // 2.5GB
            "Llama-3.2-1B-Instruct-q4f32_1-MLC": 1.2 * 1024 * 1024 * 1024, // 1.2GB
            "gemma-2-2b-it-q4f32_1-MLC": 1.8 * 1024 * 1024 * 1024, // 1.8GB
            "Phi-3.5-mini-instruct-q4f32_1-MLC": 2.1 * 1024 * 1024 * 1024, // 2.1GB
            "TinyLlama-1.1B-Chat-v0.4-q4f32_1-MLC": 1.0 * 1024 * 1024 * 1024 // 1.0GB
        };
        return sizeMap[modelId] || 2.0 * 1024 * 1024 * 1024; // Default 2GB
    }

    /**
     * Estimate memory needed for inference
     */
    estimateInferenceMemory(messages, options) {
        const tokensEstimate = messages.reduce((total, msg) => total + (msg.content?.length || 0), 0) / 4; // Rough token estimate
        const maxTokens = options.max_tokens || 1000;
        const totalTokens = tokensEstimate + maxTokens;
        
        // Estimate: 4 bytes per token for activations + overhead
        return totalTokens * 4 * 2; // 2x overhead factor
    }

    /**
     * Update inference performance metrics
     */
    updateInferenceMetrics(response, inferenceTime) {
        if (response.usage) {
            const tokensGenerated = response.usage.completion_tokens || 0;
            this.performanceMetrics.tokensPerSecond = tokensGenerated / (inferenceTime / 1000);
            this.performanceMetrics.latency = inferenceTime;
            this.performanceMetrics.lastInferenceTime = Date.now();
        }
    }

    /**
     * Update performance metrics with memory stats
     */
    updatePerformanceMetrics(memoryStats) {
        if (memoryStats && memoryStats.totalMemory > 0) {
            this.performanceMetrics.memoryEfficiency = 
                (memoryStats.totalMemory - memoryStats.usedMemory) / memoryStats.totalMemory;
        }
    }

    /**
     * Handle memory warning
     */
    handleMemoryWarning(stats) {
        console.warn('WebGPU memory warning:', stats);
        // Could trigger UI notification here
    }

    /**
     * Handle critical memory situation
     */
    handleMemoryCritical(stats) {
        console.error('WebGPU memory critical:', stats);
        // Could trigger aggressive cleanup or model unloading
        if (this.isReady) {
            console.log('Critical memory situation, considering model unload...');
        }
    }

    /**
     * Handle memory cleanup completion
     */
    handleMemoryCleanup(info) {
        console.log('Memory cleanup completed:', info);
    }

    /**
     * Get memory manager statistics
     */
    getMemoryStats() {
        return this.memoryManager ? this.memoryManager.getStats() : null;
    }

    /**
     * Get performance metrics
     */
    getPerformanceMetrics() {
        return {
            ...this.performanceMetrics,
            memoryStats: this.getMemoryStats()
        };
    }

    /**
     * Set progress callback for model loading
     */
    setProgressCallback(callback) {
        this.progressCallback = callback;
    }
}

// Global WebLLM engine instance
window.webllmEngine = new WebLLMEngine();

// Alpine.js store for WebLLM
document.addEventListener('alpine:init', () => {
    Alpine.store('webllm', {
        // State
        engine: window.webllmEngine,
        isInitialized: false,
        currentModel: null,
        isLoading: false,
        loadingProgress: 0,
        loadingText: '',
        error: null,
        compatibility: null,

        // Initialize
        async init() {
            try {
                this.compatibility = this.engine.checkCompatibility();
                if (this.compatibility.supported) {
                    await this.engine.initialize();
                    this.isInitialized = true;
                }
            } catch (error) {
                this.error = error.message;
                console.error('WebLLM initialization failed:', error);
            }
        },

        // Load model
        async loadModel(modelId) {
            if (!this.isInitialized) {
                throw new Error('WebLLM not initialized');
            }

            this.isLoading = true;
            this.loadingProgress = 0;
            this.loadingText = 'Starting model download...';
            this.error = null;

            // Set progress callback
            this.engine.setProgressCallback((progress) => {
                this.loadingProgress = progress.progress * 100;
                this.loadingText = progress.text;
            });

            try {
                await this.engine.loadModel(modelId);
                this.currentModel = modelId;
                this.isLoading = false;
                this.loadingProgress = 100;
                this.loadingText = 'Model loaded successfully';
            } catch (error) {
                this.error = error.message;
                this.isLoading = false;
                this.loadingProgress = 0;
                this.loadingText = '';
                throw error;
            }
        },

        // Generate response
        async generateResponse(messages, options = {}) {
            if (!this.currentModel) {
                throw new Error('No model loaded');
            }

            try {
                return await this.engine.generateResponse(messages, options);
            } catch (error) {
                this.error = error.message;
                throw error;
            }
        },

        // Stream response
        async* streamResponse(messages, options = {}) {
            if (!this.currentModel) {
                throw new Error('No model loaded');
            }

            try {
                for await (const chunk of this.engine.streamResponse(messages, options)) {
                    yield chunk;
                }
            } catch (error) {
                this.error = error.message;
                throw error;
            }
        },

        // Unload model
        async unloadModel() {
            await this.engine.unloadModel();
            this.currentModel = null;
            this.loadingProgress = 0;
            this.loadingText = '';
        },

        // Get model info
        getModelInfo() {
            return this.engine.getModelInfo();
        },

        // Check if WebLLM is available and compatible
        isAvailable() {
            return this.compatibility && this.compatibility.supported;
        },

        // Get compatibility info
        getCompatibility() {
            return this.compatibility;
        },

        // Test prompt functionality
        testPrompt: '',
        testResponse: '',
        
        // Memory and performance monitoring
        memoryStats: null,
        performanceMetrics: null,
        memoryHistory: [],
        showMemoryMonitor: false,

        // Test the model with a prompt
        async testModel() {
            if (!this.currentModel || !this.testPrompt.trim()) {
                return;
            }

            try {
                this.testResponse = '';
                const startTime = performance.now();
                
                const response = await this.generateResponse([
                    { role: 'user', content: this.testPrompt }
                ]);
                
                const endTime = performance.now();
                this.testResponse = response.content;
                
                // Update performance display
                this.updatePerformanceDisplay(response, endTime - startTime);
                
            } catch (error) {
                this.error = 'Test failed: ' + error.message;
                this.testResponse = '';
            }
        },

        // Update performance metrics display
        updatePerformanceDisplay(response, inferenceTime) {
            this.performanceMetrics = {
                tokensPerSecond: response.tokensPerSecond || 0,
                inferenceTime: Math.round(inferenceTime),
                memoryUsage: this.memoryStats?.usagePercent || 0,
                lastUpdate: new Date().toLocaleTimeString()
            };
        },

        // Toggle memory monitor display
        toggleMemoryMonitor() {
            this.showMemoryMonitor = !this.showMemoryMonitor;
            if (this.showMemoryMonitor) {
                this.startMemoryMonitoring();
            } else {
                this.stopMemoryMonitoring();
            }
        },

        // Start memory monitoring updates
        startMemoryMonitoring() {
            if (this.engine.memoryManager) {
                this.memoryUpdateInterval = setInterval(() => {
                    this.memoryStats = this.engine.getMemoryStats();
                    this.memoryHistory = this.engine.memoryManager.getMemoryHistory();
                }, 1000);
            }
        },

        // Stop memory monitoring updates
        stopMemoryMonitoring() {
            if (this.memoryUpdateInterval) {
                clearInterval(this.memoryUpdateInterval);
                this.memoryUpdateInterval = null;
            }
        },

        // Force memory cleanup
        async forceCleanup() {
            if (this.engine.memoryManager) {
                this.engine.memoryManager.performCleanup();
                this.memoryStats = this.engine.getMemoryStats();
            }
        },

        // Get memory usage color for UI
        getMemoryUsageColor() {
            if (!this.memoryStats) return '#666';
            const usage = this.memoryStats.usagePercent;
            if (usage >= 90) return '#dc3545'; // Critical - red
            if (usage >= 75) return '#fd7e14'; // Warning - orange
            if (usage >= 50) return '#ffc107'; // Caution - yellow
            return '#28a745'; // Good - green
        },

        // Format memory size for display
        formatMemorySize(bytes) {
            if (!bytes) return '0 B';
            const k = 1024;
            const sizes = ['B', 'KB', 'MB', 'GB'];
            const i = Math.floor(Math.log(bytes) / Math.log(k));
            return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i];
        }
    });
});

// Export for use in other modules
if (typeof module !== 'undefined' && module.exports) {
    module.exports = WebLLMEngine;
}