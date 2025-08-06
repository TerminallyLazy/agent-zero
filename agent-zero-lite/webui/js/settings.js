const settingsModalProxy = {
    isOpen: false,
    settings: {},
    resolvePromise: null,
    activeTab: 'agent', // Default tab
    provider: 'cloudflared',

    // Computed property for filtered sections
    get filteredSections() {
        if (!this.settings || !this.settings.sections) return [];
        const filteredSections = this.settings.sections.filter(section => section.tab === this.activeTab);

        // If no sections match the current tab (or all tabs are missing), show all sections
        if (filteredSections.length === 0) {
            return this.settings.sections;
        }

        return filteredSections;
    },

    // Switch tab method
    switchTab(tabName) {
        // Update our component state
        this.activeTab = tabName;

        // Update the store safely
        const rootStore = Alpine.store('root');
        if (rootStore) {
            rootStore.activeTab = tabName;
        }

        localStorage.setItem('settingsActiveTab', tabName);

        // Auto-scroll active tab into view after a short delay to ensure DOM updates
        setTimeout(() => {
            const activeTab = document.querySelector('.settings-tab.active');
            if (activeTab) {
                activeTab.scrollIntoView({ behavior: 'smooth', block: 'nearest', inline: 'center' });
            }

            // When switching to the scheduler tab, initialize Flatpickr components
            if (tabName === 'scheduler') {
                console.log('Switching to scheduler tab, initializing Flatpickr');
                const schedulerElement = document.querySelector('[x-data="schedulerSettings"]');
                if (schedulerElement) {
                    const schedulerData = Alpine.$data(schedulerElement);
                    if (schedulerData) {
                        // Start polling
                        if (typeof schedulerData.startPolling === 'function') {
                            schedulerData.startPolling();
                        }

                        // Initialize Flatpickr if editing or creating
                        if (typeof schedulerData.initFlatpickr === 'function') {
                            // Check if we're creating or editing and initialize accordingly
                            if (schedulerData.isCreating) {
                                schedulerData.initFlatpickr('create');
                            } else if (schedulerData.isEditing) {
                                schedulerData.initFlatpickr('edit');
                            }
                        }

                        // Force an immediate fetch
                        if (typeof schedulerData.fetchTasks === 'function') {
                            schedulerData.fetchTasks();
                        }
                    }
                }
            }

            // When switching to the tunnel tab, initialize tunnelSettings
            if (tabName === 'tunnel') {
                console.log('Switching to tunnel tab, initializing tunnelSettings');
                const tunnelElement = document.querySelector('[x-data="tunnelSettings"]');
                if (tunnelElement) {
                    const tunnelData = Alpine.$data(tunnelElement);
                    if (tunnelData && typeof tunnelData.checkTunnelStatus === 'function') {
                        // Check tunnel status
                        tunnelData.checkTunnelStatus();
                    }
                }
            }
        }, 10);
    },

    async openModal() {
        console.log('Settings modal proxy opening');
        const modalEl = document.getElementById('settingsModal');
        const modalAD = Alpine.$data(modalEl);
        
        console.log('Modal element:', modalEl);
        console.log('Modal Alpine data:', modalAD);

        // First, ensure the store is updated properly
        const rootStore = Alpine.store('root');
        if (rootStore) {
            // Set isOpen first to ensure proper state
            rootStore.isOpen = true;
        }

        //get settings from backend
        try {
            // Check if sendJsonData is available
            if (typeof globalThis.sendJsonData !== 'function') {
                throw new Error('sendJsonData function not available');
            }
            
            const set = await globalThis.sendJsonData("/api/settings_get", null);

            // First load the settings data without setting the active tab
            const settings = {
                "title": "Settings",
                "buttons": [
                    {
                        "id": "save",
                        "title": "Save",
                        "classes": "btn btn-ok"
                    },
                    {
                        "id": "cancel",
                        "title": "Cancel",
                        "type": "secondary",
                        "classes": "btn btn-cancel"
                    }
                ],
                "sections": set.settings.sections
            }

            // Update modal data
            modalAD.isOpen = true;
            modalAD.settings = settings;

            // Now set the active tab after the modal is open
            // This ensures Alpine reactivity works as expected
            setTimeout(() => {
                // Get stored tab or default to 'agent'
                const savedTab = localStorage.getItem('settingsActiveTab') || 'agent';
                console.log(`Setting initial tab to: ${savedTab}`);

                // Directly set the active tab
                modalAD.activeTab = savedTab;

                // Also update the store
                if (store) {
                    store.activeTab = savedTab;
                }

                localStorage.setItem('settingsActiveTab', savedTab);

                // Add a small delay *after* setting the tab to ensure scrolling works
                setTimeout(() => {
                    const activeTabElement = document.querySelector('.settings-tab.active');
                    if (activeTabElement) {
                        activeTabElement.scrollIntoView({ behavior: 'smooth', block: 'nearest', inline: 'center' });
                    }
                    // Debug log
                    const schedulerTab = document.querySelector('.settings-tab[title="Task Scheduler"]');
                    console.log(`Current active tab after direct set: ${modalAD.activeTab}`);
                    console.log('Scheduler tab active after direct initialization?',
                        schedulerTab && schedulerTab.classList.contains('active'));

                    // Explicitly start polling if we're on the scheduler tab
                    if (modalAD.activeTab === 'scheduler') {
                        console.log('Settings opened directly to scheduler tab, initializing polling');
                        const schedulerElement = document.querySelector('[x-data="schedulerSettings"]');
                        if (schedulerElement) {
                            const schedulerData = Alpine.$data(schedulerElement);
                            if (schedulerData && typeof schedulerData.startPolling === 'function') {
                                schedulerData.startPolling();
                                // Also force an immediate fetch
                                if (typeof schedulerData.fetchTasks === 'function') {
                                    schedulerData.fetchTasks();
                                }
                            }
                        }
                    }
                }, 10); // Small delay just for scrolling

            }, 5); // Keep a minimal delay for modal opening reactivity

            // Add a watcher to disable the Save button when a task is being created or edited
            const schedulerComponent = document.querySelector('[x-data="schedulerSettings"]');
            if (schedulerComponent) {
                // Watch for changes to the scheduler's editing state
                const checkSchedulerEditingState = () => {
                    const schedulerData = Alpine.$data(schedulerComponent);
                    if (schedulerData) {
                        // If we're on the scheduler tab and creating/editing a task, disable the Save button
                        const saveButton = document.querySelector('.modal-footer button.btn-ok');
                        if (saveButton && modalAD.activeTab === 'scheduler' &&
                            (schedulerData.isCreating || schedulerData.isEditing)) {
                            saveButton.disabled = true;
                            saveButton.classList.add('btn-disabled');
                        } else if (saveButton) {
                            saveButton.disabled = false;
                            saveButton.classList.remove('btn-disabled');
                        }
                    }
                };

                // Add a mutation observer to detect changes in the scheduler component's state
                const observer = new MutationObserver(checkSchedulerEditingState);
                observer.observe(schedulerComponent, { attributes: true, subtree: true, childList: true });

                // Also watch for tab changes to update button state
                modalAD.$watch('activeTab', checkSchedulerEditingState);

                // Initial check
                setTimeout(checkSchedulerEditingState, 100);
            }

            return new Promise(resolve => {
                this.resolvePromise = resolve;
            });

        } catch (e) {
            console.error("Error getting settings", e);
            window.toastFetchError("Error getting settings", e);
            
            // Even if settings fetch failed, still open the modal with minimal data
            const rootStore = Alpine.store('root');
            if (rootStore) {
                rootStore.isOpen = true;
            }
            
            modalAD.isOpen = true;
            modalAD.settings = {
                "title": "Settings",
                "buttons": [
                    {
                        "id": "save",
                        "title": "Save",
                        "classes": "btn btn-ok"
                    },
                    {
                        "id": "cancel",
                        "title": "Cancel",
                        "type": "secondary",
                        "classes": "btn btn-cancel"
                    }
                ],
                "sections": [
                    {
                        "title": "API Configuration",
                        "description": "Configure your API keys and settings. <strong>Note:</strong> Settings backend is currently not available.",
                        "tab": "agent",
                        "fields": [
                            {
                                "title": "OpenAI API Key",
                                "description": "Your OpenAI API key for chat completions",
                                "type": "password",
                                "value": "Please configure in backend",
                                "readonly": true,
                                "classes": "input-field"
                            },
                            {
                                "title": "Model Configuration",
                                "description": "Current model settings",
                                "type": "text",
                                "value": "Backend configuration needed",
                                "readonly": true,
                                "classes": "input-field"
                            }
                        ]
                    },
                    {
                        "title": "External Services",
                        "description": "Configure external integrations and services",
                        "tab": "external", 
                        "fields": [
                            {
                                "title": "Status",
                                "description": "External services configuration",
                                "type": "text",
                                "value": "Backend configuration needed",
                                "readonly": true,
                                "classes": "input-field"
                            }
                        ]
                    },
                    {
                        "title": "Developer Settings",
                        "description": "Debug and development options",
                        "tab": "developer",
                        "fields": [
                            {
                                "title": "Debug Mode",
                                "description": "Enable debug logging",
                                "type": "switch",
                                "value": false,
                                "readonly": true
                            }
                        ]
                    },
                    {
                        "title": "Backup & Restore",
                        "description": "Backup and restore your settings",
                        "tab": "backup",
                        "fields": [
                            {
                                "title": "Backup Status",
                                "description": "Current backup configuration",
                                "type": "text",
                                "value": "Backend configuration needed",
                                "readonly": true,
                                "classes": "input-field"
                            }
                        ]
                    }
                ]  // Placeholder sections when API failed
            };
        }
    },

    async handleButton(buttonId) {
        if (buttonId === 'save') {
            await this.saveSettings();
        } else if (buttonId === 'cancel') {
            this.handleCancel();
        }
    },

    async saveSettings() {
        const modalEl = document.getElementById('settingsModal');
        const modalAD = Alpine.$data(modalEl);
        try {
            const resp = await window.sendJsonData("/api/settings_set", modalAD.settings);
            document.dispatchEvent(new CustomEvent('settings-updated', { detail: resp.settings }));
            
            // Show success message
            if (window.toastFrontendInfo) {
                window.toastFrontendInfo("Settings saved successfully", "Settings");
            }
            
            this.resolvePromise({
                status: 'saved',
                data: resp.settings
            });
        } catch (e) {
            window.toastFetchError("Error saving settings", e);
            return;
        }

        // Stop scheduler polling if it's running
        this.stopSchedulerPolling();
        
        // Close modal
        this.isOpen = false;
        const rootStore1 = Alpine.store('root');
        if (rootStore1) {
            setTimeout(() => {
                rootStore1.isOpen = false;
            }, 10);
        }

        // First update our component state
        this.isOpen = false;

        // Then safely update the store
        const rootStore2 = Alpine.store('root');
        if (rootStore2) {
            // Use a slight delay to avoid reactivity issues
            setTimeout(() => {
                rootStore2.isOpen = false;
            }, 10);
        }
    },

    async handleCancel() {
        this.resolvePromise({
            status: 'cancelled',
            data: null
        });

        // Stop scheduler polling if it's running
        this.stopSchedulerPolling();

        // First update our component state
        this.isOpen = false;

        // Then safely update the store
        const rootStore3 = Alpine.store('root');
        if (rootStore3) {
            // Use a slight delay to avoid reactivity issues
            setTimeout(() => {
                rootStore3.isOpen = false;
            }, 10);
        }
    },

    // Add a helper method to stop scheduler polling
    stopSchedulerPolling() {
        // Find the scheduler component and stop polling if it exists
        const schedulerElement = document.querySelector('[x-data="schedulerSettings"]');
        if (schedulerElement) {
            const schedulerData = Alpine.$data(schedulerElement);
            if (schedulerData && typeof schedulerData.stopPolling === 'function') {
                console.log('Stopping scheduler polling on modal close');
                schedulerData.stopPolling();
            }
        }
    },

    async handleFieldButton(field) {
        console.log(`Button clicked: ${field.id}`);

        if (field.id === "mcp_servers_config") {
            openModal("settings/mcp/client/mcp-servers.html");
        } else if (field.id === "backup_create") {
            openModal("settings/backup/backup.html");
        } else if (field.id === "backup_restore") {
            openModal("settings/backup/restore.html");
        } else if (field.id === "show_a2a_connection") {
            console.log('Opening A2A connection modal...');
            openModal("settings/external/a2a-connection.html");
        }
    }
};


// function initSettingsModal() {

//     window.openSettings = function () {
//         proxy.openModal().then(result => {
//             console.log(result);  // This will log the result when the modal is closed
//         });
//     }

//     return proxy
// }


// document.addEventListener('alpine:init', () => {
//     Alpine.store('settingsModal', initSettingsModal());
// });

// Wait for Alpine to be fully loaded before setting up stores
function setupAlpineStores() {
    console.log('Setting up Alpine stores...');
    console.log('Alpine object:', window.Alpine);
    console.log('Alpine.store function:', typeof Alpine.store);
    
    if (window.Alpine && typeof Alpine.store === 'function') {
        try {
            console.log('Creating Alpine root store...');
            Alpine.store('root', {
                activeTab: localStorage.getItem('settingsActiveTab') || 'agent',
                isOpen: false,

                toggleSettings() {
                    console.log('toggleSettings called');
                    this.isOpen = !this.isOpen;
                }
            });
            console.log('Alpine root store created successfully');
            
            // Test the store
            const testStore = Alpine.store('root');
            console.log('Root store test:', testStore);
            console.log('Store isOpen initial value:', testStore.isOpen);
        } catch (error) {
            console.error('Error creating Alpine store:', error);
        }
    } else {
        console.error('Alpine or Alpine.store not available');
        console.log('Retrying in 200ms...');
        setTimeout(setupAlpineStores, 200);
    }
}

// Make settingsModalProxy globally available
window.settingsModalProxy = settingsModalProxy;

// Listen for alpine:init
document.addEventListener('alpine:init', function () {
    console.log('Settings: alpine:init event fired');
    setupAlpineStores();
});

// Also try setting up stores after a delay in case alpine:init doesn't fire
setTimeout(() => {
    if (window.Alpine && !Alpine.store('root')) {
        console.log('alpine:init may have been missed, trying to set up stores...');
        setupAlpineStores();
    }
}, 1000);

// Register Alpine components when Alpine is ready
function setupAlpineComponents() {
    if (window.Alpine && typeof Alpine.data === 'function') {
        console.log('Registering Alpine components...');
        
        Alpine.data('settingsModal', function () {
        return {
            settingsData: {},
            filteredSections: [],
            activeTab: 'agent',
            isLoading: true,

            // Add openModal method that delegates to the proxy
            async openModal() {
                return await settingsModalProxy.openModal();
            },

            // Add closeModal method that delegates to the proxy
            closeModal() {
                return settingsModalProxy.closeModal();
            },

            async init() {
                // Initialize with the store value
                this.activeTab = Alpine.store('root').activeTab || 'agent';

                // Watch store tab changes
                this.$watch('$store.root.activeTab', (newTab) => {
                    if (typeof newTab !== 'undefined') {
                        this.activeTab = newTab;
                        localStorage.setItem('settingsActiveTab', newTab);
                        this.updateFilteredSections();
                    }
                });

                // Load settings
                await this.fetchSettings();
                this.updateFilteredSections();
            },

            switchTab(tab) {
                // Update our component state
                this.activeTab = tab;

                // Update the store safely
                const rootStore4 = Alpine.store('root');
                if (rootStore4) {
                    rootStore4.activeTab = tab;
                }
            },

            async fetchSettings() {
                try {
                    this.isLoading = true;
                    const response = await fetchApi('/api/settings_get', {
                        method: 'POST',
                        headers: {
                            'Content-Type': 'application/json'
                        }
                    });

                    if (response.ok) {
                        const data = await response.json();
                        if (data && data.settings) {
                            this.settingsData = data.settings;
                        } else {
                            console.error('Invalid settings data format');
                        }
                    } else {
                        console.error('Failed to fetch settings:', response.statusText);
                    }
                } catch (error) {
                    console.error('Error fetching settings:', error);
                } finally {
                    this.isLoading = false;
                }
            },

            updateFilteredSections() {
                // Filter sections based on active tab
                if (this.activeTab === 'agent') {
                    this.filteredSections = this.settingsData.sections?.filter(section =>
                        section.tab === 'agent'
                    ) || [];
                } else if (this.activeTab === 'external') {
                    this.filteredSections = this.settingsData.sections?.filter(section =>
                        section.tab === 'external'
                    ) || [];
                } else if (this.activeTab === 'developer') {
                    this.filteredSections = this.settingsData.sections?.filter(section =>
                        section.tab === 'developer'
                    ) || [];
                } else if (this.activeTab === 'mcp') {
                    this.filteredSections = this.settingsData.sections?.filter(section =>
                        section.tab === 'mcp'
                    ) || [];
                } else if (this.activeTab === 'backup') {
                    this.filteredSections = this.settingsData.sections?.filter(section =>
                        section.tab === 'backup'
                    ) || [];
                } else {
                    // For any other tab, show nothing since those tabs have custom UI
                    this.filteredSections = [];
                }
            },

            async saveSettings() {
                try {
                    // First validate
                    for (const section of this.settingsData.sections) {
                        for (const field of section.fields) {
                            if (field.required && (!field.value || field.value.trim() === '')) {
                                showToast(`${field.title} in ${section.title} is required`, 'error');
                                return;
                            }
                        }
                    }

                    // Prepare data
                    const formData = {};
                    for (const section of this.settingsData.sections) {
                        for (const field of section.fields) {
                            formData[field.id] = field.value;
                        }
                    }

                    // Send request
                    const response = await fetchApi('/api/settings_save', {
                        method: 'POST',
                        headers: {
                            'Content-Type': 'application/json'
                        },
                        body: JSON.stringify(formData)
                    });

                    if (response.ok) {
                        showToast('Settings saved successfully', 'success');
                        // Refresh settings
                        await this.fetchSettings();
                    } else {
                        const errorData = await response.json();
                        throw new Error(errorData.error || 'Failed to save settings');
                    }
                } catch (error) {
                    console.error('Error saving settings:', error);
                    showToast('Failed to save settings: ' + error.message, 'error');
                }
            },

            // Handle special button field actions
            handleFieldButton(field) {
                if (field.action === 'test_connection') {
                    this.testConnection(field);
                } else if (field.action === 'reveal_token') {
                    this.revealToken(field);
                } else if (field.action === 'generate_token') {
                    this.generateToken(field);
                } else {
                    console.warn('Unknown button action:', field.action);
                }
            },

            // Test API connection
            async testConnection(field) {
                try {
                    field.testResult = 'Testing...';
                    field.testStatus = 'loading';

                    // Find the API key field
                    let apiKey = '';
                    for (const section of this.settingsData.sections) {
                        for (const f of section.fields) {
                            if (f.id === field.target) {
                                apiKey = f.value;
                                break;
                            }
                        }
                    }

                    if (!apiKey) {
                        throw new Error('API key is required');
                    }

                    // Send test request
                    const response = await fetchApi('/api/test_connection', {
                        method: 'POST',
                        headers: {
                            'Content-Type': 'application/json'
                        },
                        body: JSON.stringify({
                            service: field.service,
                            api_key: apiKey
                        })
                    });

                    const data = await response.json();

                    if (response.ok && data.success) {
                        field.testResult = 'Connection successful!';
                        field.testStatus = 'success';
                    } else {
                        throw new Error(data.error || 'Connection failed');
                    }
                } catch (error) {
                    console.error('Connection test failed:', error);
                    field.testResult = `Failed: ${error.message}`;
                    field.testStatus = 'error';
                }
            },

            // Reveal token temporarily
            revealToken(field) {
                // Find target field
                for (const section of this.settingsData.sections) {
                    for (const f of section.fields) {
                        if (f.id === field.target) {
                            // Toggle field type
                            f.type = f.type === 'password' ? 'text' : 'password';

                            // Update button text
                            field.value = f.type === 'password' ? 'Show' : 'Hide';

                            break;
                        }
                    }
                }
            },

            // Generate random token
            generateToken(field) {
                // Find target field
                for (const section of this.settingsData.sections) {
                    for (const f of section.fields) {
                        if (f.id === field.target) {
                            // Generate random token
                            const chars = 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789';
                            let token = '';
                            for (let i = 0; i < 32; i++) {
                                token += chars.charAt(Math.floor(Math.random() * chars.length));
                            }

                            // Set field value
                            f.value = token;
                            break;
                        }
                    }
                }
            },

            closeModal() {
                // Stop scheduler polling before closing the modal
                const schedulerElement = document.querySelector('[x-data="schedulerSettings"]');
                if (schedulerElement) {
                    const schedulerData = Alpine.$data(schedulerElement);
                    if (schedulerData && typeof schedulerData.stopPolling === 'function') {
                        console.log('Stopping scheduler polling on modal close');
                        schedulerData.stopPolling();
                    }
                }

                this.$store.root.isOpen = false;
            }
        };
    });
});

// Show toast notification - now uses new notification system
function showToast(message, type = 'info') {
    // Use new frontend notification system based on type
    if (window.Alpine && window.Alpine.store && window.Alpine.store('notificationStore')) {
        const store = window.Alpine.store('notificationStore');
        switch (type.toLowerCase()) {
            case 'error':
                return store.frontendError(message, "Settings", 5);
            case 'success':
                return store.frontendInfo(message, "Settings", 3);
            case 'warning':
                return store.frontendWarning(message, "Settings", 4);
            case 'info':
            default:
                return store.frontendInfo(message, "Settings", 3);
        }
    } else {
        // Fallback if Alpine/store not ready
        console.log(`SETTINGS ${type.toUpperCase()}: ${message}`);
        return null;
    }
        };
    });
        
    console.log('Alpine components registered');
    } else {
        console.error('Alpine.data not available');
        setTimeout(setupAlpineComponents, 200);
    }
}

// Call setup functions
document.addEventListener('alpine:init', setupAlpineComponents);
setTimeout(() => {
    if (window.Alpine && typeof Alpine.data === 'function') {
        setupAlpineComponents();
    }
}, 1200);

// Global function to save settings (backup method)
window.saveSettings = function() {
    if (settingsModalProxy && typeof settingsModalProxy.saveSettings === 'function') {
        settingsModalProxy.saveSettings();
    } else {
        console.error('Settings modal not available');
    }
};

// Keyboard shortcut for saving settings
document.addEventListener('keydown', function(e) {
    if (e.ctrlKey && e.key === 's' && settingsModalProxy.isOpen) {
        e.preventDefault();
        window.saveSettings();
    }
});
