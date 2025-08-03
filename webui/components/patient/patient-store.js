import { fetchApi, callJsonApi } from '/js/api.js';

export function createPatientStore() {
  return {
    searchQuery: '',
    selectedPatient: null,
    recentPatients: [],
    searchResults: [],
    isSearching: false,
    isLoading: false,
    error: null,
    
    // Patient cache
    patientCache: new Map(),
    
    // Search functionality - integrates with EMR/DrChrono API
    async search() {
      if (!this.searchQuery.trim()) {
        this.searchResults = [];
        return;
      }
      
      this.isSearching = true;
      this.error = null;
      
      try {
        // Check if we have DrChrono integration configured
        const drchronoStore = Alpine.store('drchrono');
        if (drchronoStore && drchronoStore.isConnected()) {
          // Use DrChrono API for patient search
          const response = await callJsonApi('/patient_search', {
            query: this.searchQuery,
            source: 'drchrono'
          });
          
          if (response.success) {
            this.searchResults = response.patients.map(this.normalizePatientData);
          } else {
            throw new Error(response.message || 'Failed to search patients');
          }
        } else {
          // Fall back to generic patient search API
          const response = await callJsonApi('/patient_search', {
            query: this.searchQuery,
            source: 'generic'
          });
          
          if (response.success) {
            this.searchResults = response.patients.map(this.normalizePatientData);
          } else {
            // If no patient database is configured, show helpful message
            this.error = 'Patient database not configured. Please set up DrChrono integration in Settings.';
            this.searchResults = [];
          }
        }
        
        // Cache search results
        this.searchResults.forEach(patient => {
          this.patientCache.set(patient.id, patient);
        });
        
      } catch (error) {
        console.error('Patient search failed:', error);
        this.error = error.message || 'Failed to search patients';
        this.searchResults = [];
      }
      
      this.isSearching = false;
    },

    // Normalize patient data from different sources
    normalizePatientData(rawPatient) {
      // Handle DrChrono format
      if (rawPatient.chart_id) {
        return {
          id: rawPatient.chart_id,
          name: `${rawPatient.first_name} ${rawPatient.last_name}`,
          mrn: rawPatient.chart_id,
          dob: rawPatient.date_of_birth,
          age: this.calculateAge(rawPatient.date_of_birth),
          phone: rawPatient.cell_phone || rawPatient.home_phone,
          email: rawPatient.email,
          allergies: rawPatient.allergies || [],
          medications: rawPatient.current_medications || [],
          lastVisit: rawPatient.last_appointment_date,
          nextAppt: rawPatient.next_appointment_date,
          conditions: rawPatient.problems || [],
          labs: rawPatient.lab_results || [],
          recentActivity: rawPatient.recent_activities || [],
          source: 'drchrono',
          rawData: rawPatient
        };
      }
      
      // Handle generic format (already normalized)
      return {
        ...rawPatient,
        source: rawPatient.source || 'generic'
      };
    },

    // Calculate age from date of birth
    calculateAge(dob) {
      if (!dob) return null;
      const today = new Date();
      const birthDate = new Date(dob);
      let age = today.getFullYear() - birthDate.getFullYear();
      const m = today.getMonth() - birthDate.getMonth();
      if (m < 0 || (m === 0 && today.getDate() < birthDate.getDate())) {
        age--;
      }
      return age;
    },
    
    async selectPatient(patient) {
      this.isLoading = true;
      this.error = null;
      
      try {
        // Load full patient details if not already cached
        if (!this.patientCache.has(patient.id) || !this.patientCache.get(patient.id).fullDetails) {
          await this.loadPatientDetails(patient.id);
        }
        
        this.selectedPatient = this.patientCache.get(patient.id) || patient;
        
        // Add to recent patients (max 5)
        this.recentPatients = [
          this.selectedPatient,
          ...this.recentPatients.filter(p => p.id !== patient.id)
        ].slice(0, 5);
        
        // Store in localStorage
        localStorage.setItem('clinical_recent_patients', JSON.stringify(this.recentPatients));
        
      } catch (error) {
        console.error('Failed to select patient:', error);
        this.error = error.message || 'Failed to load patient details';
      }
      
      this.isLoading = false;
    },

    // Load full patient details
    async loadPatientDetails(patientId) {
      try {
        const response = await callJsonApi('/patient_details', {
          patient_id: patientId
        });
        
        if (response.success) {
          const normalizedPatient = this.normalizePatientData(response.patient);
          normalizedPatient.fullDetails = true;
          this.patientCache.set(patientId, normalizedPatient);
        } else {
          throw new Error(response.message || 'Failed to load patient details');
        }
      } catch (error) {
        console.error('Failed to load patient details:', error);
        throw error;
      }
    },
    
    clearSelection() {
      this.selectedPatient = null;
      this.searchQuery = '';
      this.searchResults = [];
    },
    
    // Quick actions
    async messagePatient(patient) {
      try {
        // Integrate with inbox/messaging system
        const inboxStore = Alpine.store('inbox');
        if (inboxStore) {
          // Create new message draft
          const newMessage = {
            id: `msg-${Date.now()}`,
            type: 'message',
            patient: patient.name,
            patientId: patient.id,
            subject: `Message to ${patient.name}`,
            status: 'draft',
            priority: 'normal',
            timestamp: new Date().toISOString(),
            content: ''
          };
          
          inboxStore.addDraft(newMessage);
          
          // Show success notification
          if (window.toast) {
            window.toast(`New message draft created for ${patient.name}`, 'success', 3000);
          }
        }
      } catch (error) {
        console.error('Failed to create message:', error);
        if (window.toast) {
          window.toast('Failed to create message', 'error', 3000);
        }
      }
    },
    
    async scheduleAppointment(patient) {
      try {
        // Integrate with DrChrono or generic scheduling API
        const response = await callJsonApi('/schedule_appointment', {
          patient_id: patient.id,
          patient_name: patient.name
        });
        
        if (response.success) {
          if (response.external_url) {
            // Open external scheduling system
            window.open(response.external_url, '_blank');
          } else if (response.appointment) {
            // Handle internal appointment creation
            if (window.toast) {
              window.toast(`Appointment scheduled for ${patient.name}`, 'success', 3000);
            }
          }
        } else {
          throw new Error(response.message || 'Failed to schedule appointment');
        }
      } catch (error) {
        console.error('Failed to schedule appointment:', error);
        if (window.toast) {
          window.toast('Failed to schedule appointment', 'error', 3000);
        }
      }
    },
    
    async openChart(patient) {
      try {
        // Integrate with EMR chart viewer
        const response = await callJsonApi('/open_chart', {
          patient_id: patient.id
        });
        
        if (response.success && response.chart_url) {
          // Open external EMR chart
          window.open(response.chart_url, '_blank');
        } else {
          // Fallback: show patient details in current interface
          await this.selectPatient(patient);
          if (window.toast) {
            window.toast(`Showing available details for ${patient.name}`, 'info', 3000);
          }
        }
      } catch (error) {
        console.error('Failed to open chart:', error);
        if (window.toast) {
          window.toast('Failed to open chart', 'error', 3000);
        }
      }
    },
    
    // Format helpers
    formatAge(patient) {
      if (patient.age) {
        return patient.dob ? `${patient.age}yo (${patient.dob})` : `${patient.age}yo`;
      }
      return patient.dob || 'Age unknown';
    },
    
    formatAllergies(allergies) {
      return allergies.length ? allergies.join(', ') : 'NKDA';
    },
    
    getStatusClass(status) {
      switch(status) {
        case 'high': return 'danger';
        case 'mild-high': return 'warning';
        case 'normal': return 'success';
        default: return '';
      }
    },
    
    // Initialize
    async init() {
      // Load recent patients from localStorage
      const stored = localStorage.getItem('clinical_recent_patients');
      if (stored) {
        try {
          this.recentPatients = JSON.parse(stored);
          
          // Add to cache
          this.recentPatients.forEach(patient => {
            this.patientCache.set(patient.id, patient);
          });
        } catch (e) {
          console.error('Failed to load recent patients:', e);
        }
      }
      
      // Pre-select first recent patient if any
      if (this.recentPatients.length > 0) {
        this.selectedPatient = this.recentPatients[0];
      }
      
      // Check if patient database is configured
      try {
        const response = await callJsonApi('/patient_config_check', {});
        if (!response.configured) {
          console.warn('Patient database not configured');
        }
      } catch (error) {
        console.warn('Unable to check patient database configuration:', error);
      }
    }
  }
}