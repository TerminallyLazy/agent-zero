/**
 * Eden Clinical Inboxologist - Main Application
 * Alpine.js-based reactive UI for physician inbox management
 */

// API Configuration
const API_BASE = '/eden';

// Helper: Make API requests
async function api(endpoint, options = {}) {
    const url = `${API_BASE}${endpoint}`;
    const response = await fetch(url, {
        headers: {
            'Content-Type': 'application/json',
            ...options.headers,
        },
        ...options,
    });

    if (!response.ok) {
        throw new Error(`API Error: ${response.status}`);
    }

    return response.json();
}

// Category definitions
const CATEGORIES = [
    { id: 'lab', name: 'Lab Results', icon: '🧪' },
    { id: 'message', name: 'Messages', icon: '💬' },
    { id: 'refill', name: 'Refills', icon: '💊' },
    { id: 'referral', name: 'Referrals', icon: '📋' },
    { id: 'prior_auth', name: 'Prior Auth', icon: '📄' },
    { id: 'scheduling', name: 'Scheduling', icon: '📅' },
    { id: 'billing', name: 'Billing', icon: '💳' },
    { id: 'internal', name: 'Internal', icon: '🏥' },
];

// Mock data for development
const MOCK_CLUSTERS = [
    {
        id: 'cluster-1',
        patient: {
            id: 'patient-1',
            name: 'John Doe',
            initials: 'JD',
            dob: '1965-03-15',
        },
        avgConfidence: 87,
        priority: 1,
        reasoning: [
            'Task: Multiple items for John Doe',
            '✓ Patient well-known, 15 visits, no flags',
            '✓ All items routine categories',
            '⚠ One message requires clinical assessment',
            '→ Average Confidence: 87%',
        ],
        tasks: [
            {
                id: 'task-1',
                category: 'lab',
                status: 'auto_handled',
                confidence: 94,
                title: 'Lipid Panel - Normal',
                summary: 'All values within normal range. Total cholesterol 185, LDL 110, HDL 55, Triglycerides 120.',
                draftContent: 'Hi John, great news! Your recent cholesterol test results are in and everything looks good. Your total cholesterol is 185, which is well within the healthy range. Keep up the great work with your diet and exercise routine. - Dr. Rothschild',
                reasoning: [
                    'Task: LAB for John Doe',
                    '✓ Clear-cut lab result with standard parameters',
                    '✓ Matches policy: "Auto-send normal lipid panels"',
                    '✓ Patient well-known, 15 visits, no flags',
                    '✓ Low risk: routine lab',
                    '→ Confidence: 94%',
                ],
                confidenceFactors: [
                    { name: 'task_clarity', label: 'Task Clarity', score: 0.95 },
                    { name: 'policy_match', label: 'Policy Match', score: 1.0 },
                    { name: 'patient_history', label: 'Patient History', score: 0.92 },
                    { name: 'pattern_match', label: 'Pattern Match', score: 0.88 },
                    { name: 'risk_level', label: 'Risk Level', score: 0.96 },
                ],
                patient: { id: 'patient-1', name: 'John Doe' },
                resolvedAt: new Date(Date.now() - 3600000).toISOString(),
            },
            {
                id: 'task-2',
                category: 'message',
                status: 'needs_review',
                confidence: 72,
                title: 'Portal Message - Medication Question',
                summary: 'Patient asking about timing for taking lisinopril. Mentions occasional dizziness.',
                draftContent: 'Hi John, Thank you for reaching out about your lisinopril timing. It\'s best to take it at the same time each day - many patients prefer morning. Regarding the occasional dizziness, this can happen especially when standing up quickly. If it persists or worsens, please let us know. - Dr. Rothschild',
                reasoning: [
                    'Task: MESSAGE for John Doe',
                    '✓ Patient on lisinopril per chart',
                    '⚠ Mentions dizziness - potential side effect',
                    '⚠ Clinical judgment needed on symptom severity',
                    '→ Confidence: 72%',
                ],
                confidenceFactors: [
                    { name: 'task_clarity', label: 'Task Clarity', score: 0.75 },
                    { name: 'policy_match', label: 'Policy Match', score: 0.60 },
                    { name: 'patient_history', label: 'Patient History', score: 0.92 },
                    { name: 'pattern_match', label: 'Pattern Match', score: 0.65 },
                    { name: 'risk_level', label: 'Risk Level', score: 0.70 },
                ],
                patient: { id: 'patient-1', name: 'John Doe' },
            },
        ],
    },
    {
        id: 'cluster-2',
        patient: {
            id: 'patient-2',
            name: 'Sarah Lee',
            initials: 'SL',
            dob: '1978-08-22',
        },
        avgConfidence: 91,
        priority: 2,
        reasoning: [
            'Task: Refill request for Sarah Lee',
            '✓ Stable patient, regular visits',
            '✓ Medication within refill window',
            '✓ No contraindications in chart',
            '→ Average Confidence: 91%',
        ],
        tasks: [
            {
                id: 'task-3',
                category: 'refill',
                status: 'pending',
                confidence: 91,
                title: 'Metformin 500mg Refill Request',
                summary: 'Routine refill request. Patient is stable diabetic, A1C 6.8 last check. Last visit 2 months ago.',
                draftContent: null,
                reasoning: [
                    'Task: REFILL for Sarah Lee',
                    '✓ Active prescription, refill on schedule',
                    '✓ A1C stable at 6.8 (checked 2 months ago)',
                    '✓ No adverse events documented',
                    '✓ Matches policy: routine refill for stable patient',
                    '→ Confidence: 91%',
                ],
                confidenceFactors: [
                    { name: 'task_clarity', label: 'Task Clarity', score: 0.95 },
                    { name: 'policy_match', label: 'Policy Match', score: 0.90 },
                    { name: 'patient_history', label: 'Patient History', score: 0.95 },
                    { name: 'pattern_match', label: 'Pattern Match', score: 0.85 },
                    { name: 'risk_level', label: 'Risk Level', score: 0.90 },
                ],
                patient: { id: 'patient-2', name: 'Sarah Lee' },
            },
        ],
    },
    {
        id: 'cluster-3',
        patient: {
            id: 'patient-3',
            name: 'Michael Chen',
            initials: 'MC',
            dob: '1952-11-08',
        },
        avgConfidence: 45,
        priority: 0,
        reasoning: [
            'Task: LAB with abnormal values for Michael Chen',
            '⚠ A1C elevated at 9.2 (was 7.8)',
            '⚠ Patient is 72 years old - higher risk',
            '⚠ Trending worse from previous results',
            '→ Average Confidence: 45% - ESCALATED',
        ],
        tasks: [
            {
                id: 'task-4',
                category: 'lab',
                status: 'escalated',
                confidence: 45,
                title: 'A1C Result - Elevated 9.2',
                summary: 'A1C increased from 7.8 to 9.2. Glucose control deteriorating. Patient is 72 years old with history of neuropathy.',
                draftContent: null,
                reasoning: [
                    'Task: LAB for Michael Chen',
                    '⚠ A1C 9.2 exceeds threshold (policy: escalate if > 9)',
                    '⚠ Trending worse: 7.8 → 9.2 over 3 months',
                    '⚠ Patient age 72 - higher complication risk',
                    '⚠ History of diabetic neuropathy',
                    '→ Confidence: 45% - Escalated to physician',
                ],
                confidenceFactors: [
                    { name: 'task_clarity', label: 'Task Clarity', score: 0.90 },
                    { name: 'policy_match', label: 'Policy Match', score: 0.20 },
                    { name: 'patient_history', label: 'Patient History', score: 0.85 },
                    { name: 'pattern_match', label: 'Pattern Match', score: 0.30 },
                    { name: 'risk_level', label: 'Risk Level', score: 0.25 },
                ],
                patient: { id: 'patient-3', name: 'Michael Chen' },
            },
        ],
    },
    {
        id: 'cluster-4',
        patient: {
            id: 'patient-4',
            name: 'Emily Rodriguez',
            initials: 'ER',
            dob: '1990-04-12',
        },
        avgConfidence: 88,
        priority: 3,
        reasoning: [
            'Task: Scheduling request for Emily Rodriguez',
            '✓ Routine annual physical request',
            '✓ No urgent flags in chart',
            '→ Average Confidence: 88%',
        ],
        tasks: [
            {
                id: 'task-5',
                category: 'scheduling',
                status: 'auto_handled',
                confidence: 95,
                title: 'Annual Physical Request',
                summary: 'Patient requesting to schedule annual physical. Last visit 11 months ago.',
                draftContent: 'Hi Emily, I\'ve received your request for an annual physical. Our scheduling team will reach out shortly with available times. In the meantime, you can also book directly through the patient portal. - Dr. Rothschild',
                reasoning: [
                    'Task: SCHEDULING for Emily Rodriguez',
                    '✓ Routine annual physical request',
                    '✓ Due for annual visit (11 months since last)',
                    '✓ No urgent clinical concerns',
                    '→ Confidence: 95%',
                ],
                confidenceFactors: [
                    { name: 'task_clarity', label: 'Task Clarity', score: 0.98 },
                    { name: 'policy_match', label: 'Policy Match', score: 0.95 },
                    { name: 'patient_history', label: 'Patient History', score: 0.90 },
                    { name: 'pattern_match', label: 'Pattern Match', score: 0.92 },
                    { name: 'risk_level', label: 'Risk Level', score: 0.98 },
                ],
                patient: { id: 'patient-4', name: 'Emily Rodriguez' },
                resolvedAt: new Date(Date.now() - 7200000).toISOString(),
            },
            {
                id: 'task-6',
                category: 'message',
                status: 'auto_handled',
                confidence: 82,
                title: 'Records Request',
                summary: 'Patient requesting copy of vaccination records for new employer.',
                draftContent: 'Hi Emily, I\'ve received your request for vaccination records. Our records team will prepare these and have them ready within 2-3 business days. You\'ll receive a notification when they\'re available in your portal. - Dr. Rothschild',
                reasoning: [
                    'Task: MESSAGE for Emily Rodriguez',
                    '✓ Administrative request (records)',
                    '✓ Standard workflow applies',
                    '✓ No clinical decision required',
                    '→ Confidence: 82%',
                ],
                confidenceFactors: [
                    { name: 'task_clarity', label: 'Task Clarity', score: 0.85 },
                    { name: 'policy_match', label: 'Policy Match', score: 0.80 },
                    { name: 'patient_history', label: 'Patient History', score: 0.90 },
                    { name: 'pattern_match', label: 'Pattern Match', score: 0.78 },
                    { name: 'risk_level', label: 'Risk Level', score: 0.95 },
                ],
                patient: { id: 'patient-4', name: 'Emily Rodriguez' },
                resolvedAt: new Date(Date.now() - 5400000).toISOString(),
            },
        ],
    },
];

const MOCK_ACTIVITY = [
    { id: 'act-1', type: 'auto', message: 'Auto-sent lipid results to John Doe' },
    { id: 'act-2', type: 'auto', message: 'Auto-responded to Emily Rodriguez scheduling' },
    { id: 'act-3', type: 'pending', message: 'Drafted response for John Doe message' },
    { id: 'act-4', type: 'escalated', message: 'Escalated Michael Chen A1C for review' },
    { id: 'act-5', type: 'processing', message: 'Processing incoming lab results...' },
];


// Main Alpine.js Application
document.addEventListener('alpine:init', () => {
    Alpine.data('edenApp', () => ({
        // State
        viewMode: 'clusters', // 'clusters' | 'lanes' | 'summary'
        selectedClusterId: null,
        showSettings: false,
        showNotifications: false,
        syncing: false,
        emrConnected: true, // Mock: assume connected

        // Data
        clusters: MOCK_CLUSTERS,
        categories: CATEGORIES.map(cat => ({
            ...cat,
            count: MOCK_CLUSTERS.flatMap(c => c.tasks).filter(t => t.category === cat.id).length,
        })),
        activeCategories: CATEGORIES.map(c => c.id),
        recentActivity: MOCK_ACTIVITY,
        notifications: [],

        // Settings
        confidenceThreshold: 85,
        notificationSettings: {
            email: true,
            push: true,
            sms: false,
        },
        policiesText: `Always escalate abnormal A1C above 9
Auto-approve routine refills for stable patients with visit in last 6 months
Never auto-send lab results containing 'malignancy' or 'cancer'
Route all messages mentioning chest pain to escalation immediately`,

        // Computed
        get stats() {
            const allTasks = this.clusters.flatMap(c => c.tasks);
            return {
                autoHandled: allTasks.filter(t => t.status === 'auto_handled').length,
                pending: allTasks.filter(t => t.status === 'pending' || t.status === 'needs_review').length,
                escalated: allTasks.filter(t => t.status === 'escalated').length,
                total: allTasks.length,
            };
        },

        get filteredClusters() {
            // Sort by priority (lower = more urgent)
            return [...this.clusters].sort((a, b) => a.priority - b.priority);
        },

        // Initialization
        init() {
            console.log('Eden Command Center initialized');
            this.loadData();
        },

        async loadData() {
            // In production, this would fetch from API
            // For now, using mock data
            try {
                // const data = await api('/clusters');
                // this.clusters = data.clusters;
            } catch (error) {
                console.error('Failed to load data:', error);
            }
        },

        // Actions
        selectCluster(id) {
            this.selectedClusterId = this.selectedClusterId === id ? null : id;
        },

        toggleCategory(id) {
            const idx = this.activeCategories.indexOf(id);
            if (idx > -1) {
                this.activeCategories.splice(idx, 1);
            } else {
                this.activeCategories.push(id);
            }
        },

        async syncInbox() {
            this.syncing = true;
            try {
                // await api('/emr/sync', { method: 'POST' });
                await new Promise(resolve => setTimeout(resolve, 2000)); // Mock delay
                this.recentActivity.unshift({
                    id: `act-${Date.now()}`,
                    type: 'processing',
                    message: 'Inbox synced successfully',
                });
            } catch (error) {
                console.error('Sync failed:', error);
            } finally {
                this.syncing = false;
            }
        },

        async approveTask(taskId) {
            try {
                // await api(`/tasks/${taskId}/approve`, { method: 'POST' });

                // Update local state
                for (const cluster of this.clusters) {
                    const task = cluster.tasks.find(t => t.id === taskId);
                    if (task) {
                        task.status = 'completed';
                        task.resolvedAt = new Date().toISOString();
                        this.recentActivity.unshift({
                            id: `act-${Date.now()}`,
                            type: 'auto',
                            message: `Approved ${task.title} for ${task.patient.name}`,
                        });
                        break;
                    }
                }

                // Recalculate category counts
                this.updateCategoryCounts();
            } catch (error) {
                console.error('Approve failed:', error);
            }
        },

        async editTask(taskId) {
            // For now, just show an alert. In production, open edit modal
            alert(`Edit task ${taskId} - Modal would open here`);
        },

        async escalateTask(taskId) {
            try {
                // await api(`/tasks/${taskId}/escalate`, { method: 'POST' });

                for (const cluster of this.clusters) {
                    const task = cluster.tasks.find(t => t.id === taskId);
                    if (task) {
                        task.status = 'escalated';
                        task.confidence = Math.min(task.confidence, 50);
                        this.recentActivity.unshift({
                            id: `act-${Date.now()}`,
                            type: 'escalated',
                            message: `Escalated ${task.title} for review`,
                        });
                        break;
                    }
                }
            } catch (error) {
                console.error('Escalate failed:', error);
            }
        },

        async connectEMR() {
            // In production, this would initiate OAuth flow
            window.location.href = '/eden/emr/connect';
        },

        async savePolicies() {
            try {
                // await api('/policies', {
                //     method: 'POST',
                //     body: JSON.stringify({ policies: this.policiesText }),
                // });
                alert('Policies saved successfully');
            } catch (error) {
                console.error('Save policies failed:', error);
            }
        },

        openTaskDetail(task) {
            // Navigate to cluster containing this task
            const cluster = this.clusters.find(c => c.tasks.some(t => t.id === task.id));
            if (cluster) {
                this.viewMode = 'clusters';
                this.selectedClusterId = cluster.id;
            }
        },

        // Helpers
        getTasksByCategory(categoryId) {
            return this.clusters
                .flatMap(c => c.tasks)
                .filter(t => t.category === categoryId);
        },

        getAutoHandledTasks() {
            return this.clusters
                .flatMap(c => c.tasks)
                .filter(t => t.status === 'auto_handled')
                .sort((a, b) => new Date(b.resolvedAt) - new Date(a.resolvedAt));
        },

        updateCategoryCounts() {
            this.categories = CATEGORIES.map(cat => ({
                ...cat,
                count: this.clusters.flatMap(c => c.tasks).filter(t => t.category === cat.id).length,
            }));
        },

        getCategoryIcon(category) {
            const cat = CATEGORIES.find(c => c.id === category);
            return cat ? cat.icon : '📋';
        },

        getCategoryBgClass(category) {
            return `category-bg-${category}`;
        },

        getStatusIcon(status) {
            switch (status) {
                case 'auto_handled':
                case 'completed':
                    return '✓';
                case 'needs_review':
                case 'pending':
                    return '⏳';
                case 'escalated':
                    return '⚠';
                default:
                    return '•';
            }
        },

        getStatusClass(status) {
            switch (status) {
                case 'auto_handled':
                case 'completed':
                    return 'text-success';
                case 'needs_review':
                case 'pending':
                    return 'text-pending';
                case 'escalated':
                    return 'text-escalated';
                default:
                    return 'text-slate';
            }
        },

        getConfidenceClass(confidence) {
            if (confidence >= 90) return 'confidence-high';
            if (confidence >= 75) return 'confidence-medium';
            if (confidence >= 60) return 'confidence-low';
            return 'confidence-critical';
        },

        getStatusBadgeClass(status) {
            return `status-${status}`;
        },

        formatTime(isoString) {
            if (!isoString) return '';
            const date = new Date(isoString);
            const now = new Date();
            const diffMs = now - date;
            const diffMins = Math.floor(diffMs / 60000);
            const diffHours = Math.floor(diffMs / 3600000);

            if (diffMins < 1) return 'Just now';
            if (diffMins < 60) return `${diffMins}m ago`;
            if (diffHours < 24) return `${diffHours}h ago`;
            return date.toLocaleDateString();
        },
    }));
});
