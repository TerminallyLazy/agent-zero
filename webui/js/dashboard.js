// Dashboard functionality  
window.dashboardModal = {  
    isOpen: false,  
    csvPath: '',  
    chartType: 'auto',  
      
    openModal() {  
        this.isOpen = true;  
        document.getElementById('dashboard-modal').classList.remove('hidden');  
    },  
      
    closeModal() {  
        this.isOpen = false;  
        document.getElementById('dashboard-modal').classList.add('hidden');  
    },  
      
    async generateDashboard() {  
        if (!this.csvPath) {  
            toast('Please select a CSV file first', 'error');  
            return;  
        }  
          
        try {  
            const response = await fetch('/dashboard_generate', {  
                method: 'POST',  
                headers: {  
                    'Content-Type': 'application/json'  
                },  
                body: JSON.stringify({  
                    csv_path: this.csvPath,  
                    chart_type: this.chartType  
                })  
            });  
              
            const result = await response.json();  
              
            if (result.success) {  
                // Display the generated chart and insights  
                this.displayResults(result);  
                toast('Dashboard generated successfully!', 'success');  
            } else {  
                toast(result.error || 'Dashboard generation failed', 'error');  
            }  
        } catch (error) {  
            toast('Error generating dashboard: ' + error.message, 'error');  
        }  
    },  
      
    displayResults(result) {  
        const resultsDiv = document.getElementById('dashboard-results');  
        resultsDiv.innerHTML = `  
            <div class="dashboard-insights">  
                <h3>Generated Dashboard</h3>  
                <div class="dashboard-chart">  
                    <img src="/image_get?path=${result.chart_path}" alt="Generated Chart" style="max-width: 100%; height: auto;">  
                </div>  
                <div class="insight-section">  
                    <div class="insight-title">Analysis Results:</div>  
                    <p>${result.message}</p>  
                </div>  
            </div>  
        `;  
    }  
};