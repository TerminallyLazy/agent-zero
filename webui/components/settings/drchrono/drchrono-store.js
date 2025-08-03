import { fetchApi, callJsonApi } from '/js/api.js';

export function createDrChronoStore() {
  return {
    // Configuration
    environment: 'production', // sandbox, production, custom
    endpoints: {
      sandbox: 'https://drchrono.com/api',
      production: 'https://drchrono.com/api',
      custom: ''
    },
    
    // Pre-configured credentials
    clientId: 'kWzevEWcIvT1Ih12csjmzxoCIsbt09clOJ48vHhU',
    clientSecret: 'tCF9oArAfBYbxafeauUYWnoLXTqpjPzbrJQH1hCJuLy2jkI22M4Ai9RnaeBLqgFT6ff3fBQLMNgYK5dWlyWs1Pp1EBNYzyV1GfNTn8X4Vd2EVNpOWOCoAJxA9x7aFQoN',
    redirectUri: 'http://localhost:5000/callback.html',
    practiceId: '',
    accessToken: '',
    refreshToken: '',
    
    // OAuth state
    isAuthenticating: false,
    authError: null,
    
    // UI State
    showSecret: false,
    isTesting: false,
    testResult: null,
    lastTestTime: null,
    hasUnsavedChanges: false,
    
    // Get current endpoint
    get currentEndpoint() {
      if (this.environment === 'custom') {
        return this.endpoints.custom;
      }
      return this.endpoints[this.environment];
    },
    
    // Toggle secret visibility
    toggleSecretVisibility() {
      this.showSecret = !this.showSecret;
    },
    
    // Mark as changed
    markChanged() {
      this.hasUnsavedChanges = true;
    },
    
    // Test connection to DrChrono API
    async testConnection() {
      if (!this.accessToken) {
        this.testResult = {
          success: false,
          message: 'No access token. Please authenticate with DrChrono first.',
          timestamp: new Date().toISOString()
        };
        return;
      }
      
      this.isTesting = true;
      this.testResult = null;
      
      try {
        // Test API connection via backend (avoids CORS issues)
        const response = await callJsonApi('/drchrono_test', {
          access_token: this.accessToken,
          base_url: this.currentEndpoint
        });
        
        if (response.success) {
          this.testResult = {
            success: true,
            message: response.message,
            timestamp: new Date().toISOString(),
            userData: response.user_data
          };
          
          // Get practice information
          await this.fetchPracticeInfo();
        } else {
          this.testResult = {
            success: false,
            message: response.message,
            timestamp: new Date().toISOString()
          };
        }
      } catch (error) {
        this.testResult = {
          success: false,
          message: `Connection failed: ${error.message}`,
          timestamp: new Date().toISOString()
        };
      }
      
      this.lastTestTime = new Date();
      this.isTesting = false;
    },
    
    // Fetch practice information
    async fetchPracticeInfo() {
      try {
        // Use backend API to avoid CORS issues
        const response = await callJsonApi('/drchrono_test', {
          access_token: this.accessToken,
          base_url: this.currentEndpoint
        });
        
        if (response.success && response.user_data && response.user_data.practice) {
          this.practiceId = response.user_data.practice.toString();
        }
      } catch (error) {
        console.error('Failed to fetch practice info:', error);
      }
    },
    
    // Save configuration
    async save() {
      const config = {
        environment: this.environment,
        practiceId: this.practiceId,
        lastTestTime: this.lastTestTime
      };
      
      // Store non-sensitive config in localStorage
      localStorage.setItem('drchrono_config', JSON.stringify(config));
      
      // Update clinical API
      if (this.accessToken) {
        await this.updateClinicalAPI();
      }
      
      this.hasUnsavedChanges = false;
      if (window.toast) {
        window.toast('DrChrono settings saved successfully', 'success', 3000);
      }
    },
    
    // Reset to defaults
    reset() {
      if (!confirm('Reset all DrChrono settings to defaults?')) return;
      
      this.environment = 'sandbox';
      this.endpoints.custom = '';
      this.clientId = '';
      this.clientSecret = '';
      this.redirectUri = '';
      this.practiceId = '';
      this.accessToken = '';
      this.refreshToken = '';
      this.testResult = null;
      this.lastTestTime = null;
      this.hasUnsavedChanges = false;
      
      // Clear from storage
      localStorage.removeItem('drchrono_config');
      localStorage.removeItem('drchrono_access_token');
      localStorage.removeItem('drchrono_refresh_token');
    },
    
    // OAuth flow initiation
    async initiateOAuth() {
      if (!this.clientId || !this.redirectUri) {
        alert('DrChrono credentials not configured properly');
        return;
      }
      
      this.isAuthenticating = true;
      this.authError = null;
      
      // Create OAuth authorization URL
      const authUrl = `${this.currentEndpoint}/o/authorize/?` + 
        `response_type=code&` +
        `client_id=${this.clientId}&` +
        `redirect_uri=${encodeURIComponent(this.redirectUri)}&` +
        `scope=patients:read+patients:write+clinical:read+clinical:write+user:read`;
      
      // Open OAuth in popup
      const popup = window.open(
        authUrl,
        'drchrono_auth',
        'width=600,height=700,scrollbars=yes,resizable=yes'
      );
      
      // Listen for popup completion
      const checkClosed = setInterval(() => {
        if (popup.closed) {
          clearInterval(checkClosed);
          this.isAuthenticating = false;
          
          // Check if we received tokens
          const storedToken = localStorage.getItem('drchrono_access_token');
          if (storedToken) {
            this.accessToken = storedToken;
            this.refreshToken = localStorage.getItem('drchrono_refresh_token') || '';
            this.testConnection(); // Test the new connection
          }
        }
      }, 1000);
    },
    
    // Handle OAuth callback (called from callback page)
    async handleOAuthCallback(code, state) {
      try {
        // Exchange authorization code for access token via backend
        const tokenResponse = await callJsonApi('/drchrono_oauth', {
          code: code,
          client_id: this.clientId,
          client_secret: this.clientSecret,
          redirect_uri: this.redirectUri
        });
        
        if (!tokenResponse.success) {
          throw new Error(tokenResponse.message || 'Token exchange failed');
        }
        
        // Store tokens
        this.accessToken = tokenResponse.access_token;
        this.refreshToken = tokenResponse.refresh_token;
        
        // Save to localStorage
        localStorage.setItem('drchrono_access_token', this.accessToken);
        if (this.refreshToken) {
          localStorage.setItem('drchrono_refresh_token', this.refreshToken);
        }
        
        // Update clinical API with DrChrono config
        await this.updateClinicalAPI();
        
        return { success: true };
      } catch (error) {
        this.authError = error.message;
        return { success: false, error: error.message };
      }
    },
    
    // Update Clinical API with DrChrono configuration
    async updateClinicalAPI() {
      try {
        await callJsonApi('/drchrono_config', {
          base_url: this.currentEndpoint,
          access_token: this.accessToken,
          refresh_token: this.refreshToken,
          client_id: this.clientId,
          client_secret: this.clientSecret
        });
      } catch (error) {
        console.error('Failed to update clinical API config:', error);
      }
    },
    
    // Check if DrChrono is connected
    isConnected() {
      return !!(this.accessToken && this.testResult?.success);
    },
    
    // Refresh access token
    async refreshAccessToken() {
      if (!this.refreshToken) {
        throw new Error('No refresh token available');
      }
      
      try {
        const response = await fetch(`${this.currentEndpoint}/o/token/`, {
          method: 'POST',
          headers: {
            'Content-Type': 'application/x-www-form-urlencoded',
          },
          body: new URLSearchParams({
            grant_type: 'refresh_token',
            refresh_token: this.refreshToken,
            client_id: this.clientId,
            client_secret: this.clientSecret
          })
        });
        
        if (!response.ok) {
          throw new Error(`Token refresh failed: ${response.status}`);
        }
        
        const tokenData = await response.json();
        
        // Update tokens
        this.accessToken = tokenData.access_token;
        if (tokenData.refresh_token) {
          this.refreshToken = tokenData.refresh_token;
        }
        
        // Save to localStorage
        localStorage.setItem('drchrono_access_token', this.accessToken);
        if (this.refreshToken) {
          localStorage.setItem('drchrono_refresh_token', this.refreshToken);
        }
        
        return true;
      } catch (error) {
        console.error('Token refresh failed:', error);
        // Clear invalid tokens
        this.accessToken = '';
        this.refreshToken = '';
        localStorage.removeItem('drchrono_access_token');
        localStorage.removeItem('drchrono_refresh_token');
        throw error;
      }
    },
    
    // Disconnect from DrChrono
    disconnect() {
      if (!confirm('Disconnect from DrChrono? You will need to re-authenticate.')) {
        return;
      }
      
      this.accessToken = '';
      this.refreshToken = '';
      this.practiceId = '';
      this.testResult = null;
      this.authError = null;
      
      // Clear from storage
      localStorage.removeItem('drchrono_access_token');
      localStorage.removeItem('drchrono_refresh_token');
    },
    
    // Format helpers
    formatTestTime() {
      if (!this.lastTestTime) return 'Never tested';
      
      const diff = Date.now() - this.lastTestTime;
      if (diff < 60000) return 'Just now';
      if (diff < 3600000) return `${Math.floor(diff / 60000)}m ago`;
      if (diff < 86400000) return `${Math.floor(diff / 3600000)}h ago`;
      return this.lastTestTime.toLocaleDateString();
    },
    
    // Initialize
    async init() {
      // Load saved configuration
      const saved = localStorage.getItem('drchrono_config');
      if (saved) {
        try {
          const config = JSON.parse(saved);
          // Only load non-credential settings
          if (config.environment) this.environment = config.environment;
          if (config.practiceId) this.practiceId = config.practiceId;
          
          // Convert stored date string back to Date object
          if (config.lastTestTime) {
            this.lastTestTime = new Date(config.lastTestTime);
          }
        } catch (e) {
          console.error('Failed to load DrChrono config:', e);
        }
      }
      
      // Load tokens
      this.accessToken = localStorage.getItem('drchrono_access_token') || '';
      this.refreshToken = localStorage.getItem('drchrono_refresh_token') || '';
      
      // Update clinical API if we have tokens
      if (this.accessToken) {
        await this.updateClinicalAPI();
        // Test connection on startup
        await this.testConnection();
      }
      
      this.hasUnsavedChanges = false;
    },
    
    // Manual authorization code entry (for development/testing)
    async enterManualCode() {
      const code = prompt('Enter the authorization code from DrChrono OAuth callback:');
      if (!code) return;
      
      try {
        this.isAuthenticating = true;
        this.authError = null;
        
        const result = await this.handleOAuthCallback(code, null);
        if (result.success) {
          alert('Successfully connected to DrChrono!');
          await this.testConnection();
        } else {
          this.authError = result.error;
        }
      } catch (error) {
        this.authError = error.message;
      } finally {
        this.isAuthenticating = false;
      }
    },
    
    // Load tokens from drchrono_tokens.json file
    async loadTokensFromFile() {
      try {
        this.isAuthenticating = true;
        this.authError = null;
        
        const response = await callJsonApi('/drchrono_load_tokens', {});
        
        if (response.success) {
          this.accessToken = response.access_token;
          this.refreshToken = response.refresh_token;
          
          // Save to localStorage
          localStorage.setItem('drchrono_access_token', this.accessToken);
          if (this.refreshToken) {
            localStorage.setItem('drchrono_refresh_token', this.refreshToken);
          }
          
          // Update clinical API with DrChrono config
          await this.updateClinicalAPI();
          
          alert('Successfully loaded DrChrono tokens from file!');
          await this.testConnection();
        } else {
          this.authError = response.message;
        }
      } catch (error) {
        this.authError = error.message;
      } finally {
        this.isAuthenticating = false;
      }
    }
  }
}