// Profile Management JavaScript for Agent Zero

const profilesSettings = {
    // Data
    profiles: [],
    activeProfile: null,
    activeProfileId: '',
    templates: [],
    
    // UI State
    showProfileModal: false,
    showImportModal: false,
    editingProfile: {},
    isLoading: false,
    error: null,

    // Initialize
    async init() {
        await this.loadProfiles();
        await this.loadTemplates();
    },

    // Load profiles from API
    async loadProfiles() {
        try {
            this.isLoading = true;
            this.error = null;

            const response = await sendJsonData('/profile_list', {});

            if (response.success) {
                this.profiles = response.profiles || [];
                this.activeProfileId = response.active_profile_id || 'default';
                this.activeProfile = this.profiles.find(p => p.id === this.activeProfileId) || null;
            } else {
                this.error = response.error || 'Failed to load profiles';
                console.error('Error loading profiles:', this.error);
            }
        } catch (error) {
            this.error = 'Network error loading profiles';
            console.error('Error loading profiles:', error);
        } finally {
            this.isLoading = false;
        }
    },

    // Load templates from API
    async loadTemplates() {
        try {
            const response = await sendJsonData('/profile_templates', {});

            if (response.success) {
                this.templates = response.templates || [];
                // Add templates to the profiles list for display
                this.profiles = [...this.profiles.filter(p => !p.is_template), ...this.templates];
            } else {
                console.error('Error loading templates:', response.error);
            }
        } catch (error) {
            console.error('Error loading templates:', error);
        }
    },

    // Create new profile
    createProfile() {
        this.editingProfile = {
            name: '',
            description: '',
            avatar: '🤖',
            prompts_subdir: '',
            memory_subdir: '',
            knowledge_subdirs: ['default'],
            chat_model_overrides: {},
            utility_model_overrides: {},
            embedding_model_overrides: {},
            browser_model_overrides: {},
            custom_tools: [],
            custom_extensions: [],
            custom_helpers: [],
            tools_dir: 'tools',
            helpers_dir: 'helpers',
            extensions_dir: 'extensions',
            assets_dir: 'assets',
            config_files: [],
            environment_vars: {},
            dependencies: [],
            version: '1.0.0',
            author: '',
            is_template: false,
            template_source: ''
        };
        this.showProfileModal = true;
    },

    // Edit existing profile
    editProfile(profile) {
        this.editingProfile = { ...profile };
        this.showProfileModal = true;
    },

    // Save profile (create or update)
    async saveProfile() {
        try {
            if (!this.editingProfile.name || !this.editingProfile.name.trim()) {
                toast('Profile name is required', 'error');
                return;
            }

            // Generate ID from name if creating new profile
            if (!this.editingProfile.id) {
                this.editingProfile.id = this.editingProfile.name.toLowerCase()
                    .replace(/[^a-z0-9]/g, '_')
                    .replace(/_+/g, '_')
                    .replace(/^_|_$/g, '');
            }

            // Set memory_subdir to profile ID if not specified
            if (!this.editingProfile.memory_subdir) {
                this.editingProfile.memory_subdir = this.editingProfile.id;
            }

            const isUpdate = !!this.profiles.find(p => p.id === this.editingProfile.id && !p.is_template);
            const endpoint = isUpdate ? '/profile_update' : '/profile_create';
            const payload = isUpdate
                ? { profile_id: this.editingProfile.id, profile_data: this.editingProfile }
                : { profile_data: this.editingProfile };

            const response = await sendJsonData(endpoint, payload);

            if (response.success) {
                toast(`Profile ${isUpdate ? 'updated' : 'created'} successfully`, 'success');
                this.showProfileModal = false;
                await this.loadProfiles();
            } else {
                toast(response.error || `Failed to ${isUpdate ? 'update' : 'create'} profile`, 'error');
            }
        } catch (error) {
            console.error('Error saving profile:', error);
            toast('Network error saving profile', 'error');
        }
    },

    // Cancel profile editing
    cancelProfileEdit() {
        this.showProfileModal = false;
        this.editingProfile = {};
    },

    // Switch to different profile
    async switchProfile(profileId) {
        try {
            const response = await sendJsonData('/profile_switch', { profile_id: profileId });

            if (response.success) {
                toast(response.message || 'Profile switched successfully', 'success');
                this.activeProfileId = profileId;
                this.activeProfile = response.active_profile;
                await this.loadProfiles();
            } else {
                toast(response.error || 'Failed to switch profile', 'error');
            }
        } catch (error) {
            console.error('Error switching profile:', error);
            toast('Network error switching profile', 'error');
        }
    },

    // Delete profile
    async deleteProfile(profileId) {
        if (!confirm('Are you sure you want to delete this profile? This action cannot be undone.')) {
            return;
        }

        try {
            const response = await sendJsonData('/profile_delete', { profile_id: profileId });

            if (response.success) {
                toast('Profile deleted successfully', 'success');
                await this.loadProfiles();
            } else {
                toast(response.error || 'Failed to delete profile', 'error');
            }
        } catch (error) {
            console.error('Error deleting profile:', error);
            toast('Network error deleting profile', 'error');
        }
    },

    // Export profile
    async exportProfile(profileId) {
        try {
            // Create a form to submit for file download
            const form = document.createElement('form');
            form.method = 'POST';
            form.action = '/profile_export';
            form.style.display = 'none';

            const input = document.createElement('input');
            input.name = 'profile_id';
            input.value = profileId;
            form.appendChild(input);

            document.body.appendChild(form);
            form.submit();
            document.body.removeChild(form);

            toast('Profile export started', 'success');
        } catch (error) {
            console.error('Error exporting profile:', error);
            toast('Error exporting profile', 'error');
        }
    },

    // Show import modal
    importProfile() {
        this.showImportModal = true;
    },

    // Cancel import
    cancelImport() {
        this.showImportModal = false;
    },

    // Handle file selection
    async handleFileSelect(event) {
        const file = event.target.files[0];
        if (file) {
            await this.uploadProfileFile(file);
        }
    },

    // Handle file drop
    async handleFileDrop(event) {
        const files = event.dataTransfer.files;
        if (files.length > 0) {
            await this.uploadProfileFile(files[0]);
        }
    },

    // Upload profile file
    async uploadProfileFile(file) {
        try {
            if (!file.name.toLowerCase().endsWith('.zip')) {
                toast('Only ZIP files are supported', 'error');
                return;
            }

            const formData = new FormData();
            formData.append('file', file);

            const response = await fetchApi('/profile_import', {
                method: 'POST',
                body: formData
            });

            const result = await response.json();

            if (result.success) {
                toast(result.message || 'Profile imported successfully', 'success');
                this.showImportModal = false;
                await this.loadProfiles();
            } else {
                toast(result.error || 'Failed to import profile', 'error');
            }
        } catch (error) {
            console.error('Error importing profile:', error);
            toast('Network error importing profile', 'error');
        }
    },

    // Create profile from template
    async createFromTemplate(template) {
        const name = prompt('Enter a name for the new profile:', template.name + ' Copy');
        if (!name) return;

        const description = prompt('Enter a description (optional):', 'Created from ' + template.name + ' template');

        try {
            const response = await sendJsonData('/profile_create_from_template', {
                template_id: template.id,
                profile_name: name,
                profile_description: description || ''
            });

            if (response.success) {
                toast(response.message || 'Profile created from template successfully', 'success');
                await this.loadProfiles();
            } else {
                toast(response.error || 'Failed to create profile from template', 'error');
            }
        } catch (error) {
            console.error('Error creating profile from template:', error);
            toast('Network error creating profile from template', 'error');
        }
    },

    // Format date for display
    formatDate(dateString) {
        try {
            const date = new Date(dateString);
            return date.toLocaleDateString();
        } catch {
            return 'Unknown';
        }
    }
};

// Initialize Alpine.js component
document.addEventListener('alpine:init', () => {
    Alpine.data('profilesSettings', () => ({
        ...profilesSettings,

        // Override init to be called automatically when component mounts
        async init() {
            await this.loadProfiles();
            await this.loadTemplates();
        }
    }));
});