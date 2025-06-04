import json  
import pandas as pd  
import matplotlib.pyplot as plt  
from pathlib import Path  
from python.helpers.tool import Tool, Response  
from python.helpers.files import get_abs_path  
from python.helpers.chart_utils import (  
    fix_legends, create_color_palette, enhance_plot,   
    fix_pie_chart, fix_multiple_series  
)  
from python.helpers.d2insight_agent_sys import run_domain_detector  
  
class DashboardTool(Tool):  
      
    async def execute(self, csv_path="", chart_type="auto", **kwargs):  
        """  
        Execute dashboard generation for CSV data  
        """  
        try:  
            # Import the D2D modules (need to be added to the codebase)  
            from python.helpers.chart_utils import (  
                fix_legends, create_color_palette, enhance_plot,   
                fix_pie_chart, fix_multiple_series  
            )
            from python.helpers.d2insight_agent_sys import run_domain_detector  
              
            # Validate CSV path  
            if not csv_path:  
                return Response(message="Error: No CSV file path provided", break_loop=False)  
              
            full_path = get_abs_path(csv_path)  
            if not Path(full_path).exists():  
                return Response(message=f"Error: CSV file not found at {csv_path}", break_loop=False)  
              
            # Run domain detection and analysis  
            analysis_result = run_domain_detector(full_path)  
              
            # Generate insights summary  
            insights = analysis_result.get("analysis", {})  
            domain = analysis_result.get("domain_info", {}).get("domain", "Unknown")  
              
            # Create visualizations based on data  
            df = pd.read_csv(full_path)  
              
            # Auto-detect chart type if not specified  
            if chart_type == "auto":  
                numeric_cols = df.select_dtypes(include=['number']).columns  
                if len(numeric_cols) >= 2:  
                    chart_type = "scatter"  
                elif len(numeric_cols) == 1:  
                    chart_type = "histogram"  
                else:  
                    chart_type = "bar"  
              
            # Generate chart  
            output_path = get_abs_path("work_dir/dashboard_chart.png")  
              
            if chart_type == "bar" and len(df.columns) >= 2:  
                fig, ax = fix_multiple_series(  
                    df.head(10),   
                    kind='bar',  
                    title=f"Data Analysis - {domain}",  
                    figsize=(12, 8)  
                )  
            else:  
                fig, ax = plt.subplots(figsize=(12, 8))  
                if chart_type == "histogram" and len(df.select_dtypes(include=['number']).columns) > 0:  
                    numeric_col = df.select_dtypes(include=['number']).columns[0]  
                    ax.hist(df[numeric_col].dropna(), bins=20, alpha=0.7)  
                    enhance_plot(ax=ax, title=f"{numeric_col} Distribution - {domain}")  
                else:  
                    # Default to simple bar chart of first few rows  
                    df.head(10).plot(kind='bar', ax=ax)  
                    enhance_plot(ax=ax, title=f"Data Overview - {domain}")  
              
            plt.tight_layout()  
            plt.savefig(output_path, dpi=300, bbox_inches='tight')  
            plt.close()  
              
            # Prepare response  
            response_text = f"""Dashboard Generated Successfully!  
  
Domain: {domain}  
  
Key Insights:  
- Descriptive: {insights.get('descriptive', 'N/A')[:200]}...  
- Predictive: {insights.get('predictive', 'N/A')[:200]}...  
- Domain-specific: {insights.get('domain_related', 'N/A')[:200]}...  
  
Chart saved to: {output_path}  
Data shape: {df.shape[0]} rows, {df.shape[1]} columns  
"""  
              
            return Response(message=response_text, break_loop=False)  
              
        except Exception as e:  
            return Response(message=f"Dashboard generation failed: {str(e)}", break_loop=False)