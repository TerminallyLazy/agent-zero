import json  
import tempfile  
from pathlib import Path  
import models
from python.helpers.tool import Tool, Response  
from python.helpers.files import get_abs_path  
from python.helpers.chart_utils import (  
    fix_legends, create_color_palette, enhance_plot,   
    fix_pie_chart, fix_multiple_series  
)  
from python.helpers.d2insight_agent_sys import run_domain_detector  
  
class CompleteDashboardTool(Tool):  
      
    async def execute(self, csv_path="", chart_type="auto", model="gpt-4.1", **kwargs):  
        """  
        Complete dashboard generation: insights + Tree-of-Thought visualizations  
        """  
        try:  
            # Import both systems  
            from python.helpers.d2insight_agent_sys import run_domain_detector  
            from python.helpers.generate_and_run import generate_analysis  
              
            # Validate CSV path  
            if not csv_path:  
                return Response(message="Error: No CSV file path provided", break_loop=False)  
              
            full_path = get_abs_path(csv_path)  
            if not Path(full_path).exists():  
                return Response(message=f"Error: CSV file not found at {csv_path}", break_loop=False)  
              
            # Step 1: Generate domain insights using D2insight agent  
            analysis_result = run_domain_detector(full_path)  
              
            # Step 2: Save insights to JSON for the analysis generator  
            output_dir = get_abs_path("work_dir/complete_dashboard")  
            Path(output_dir).mkdir(parents=True, exist_ok=True)  
              
            insights_json_path = Path(output_dir) / "insights.json"  
            with open(insights_json_path, 'w') as f:  
                json.dump(analysis_result.get("analysis", {}), f, indent=2)  
              
            # Step 3: Generate Tree-of-Thought visualizations  
            thoughts = generate_analysis(  
                csv_path=full_path,  
                insight_json_path=insights_json_path,  
                model_config=model,  
                run_code=True,  
                save_dir=output_dir,  
                preserve_domain_insights=True  
            )  
              
            # Step 4: Compile results
            # Convert string model name to proper model config object
            from agent import ModelConfig
            
            if isinstance(model, str):
                model_config = ModelConfig(
                    provider=models.ModelProvider.OPENAI,
                    name=model
                )
            else:
                model_config = model
              
            domain = analysis_result.get("domain_info", {}).get("domain", "Unknown")  
            insights = analysis_result.get("analysis", {})  
              
            # Check for generated files  
            figures_dir = Path(output_dir) / "figures"  
            figure_files = list(figures_dir.glob("*.png")) if figures_dir.exists() else []  
              
            response_text = f"""Complete Dashboard Generated Successfully!  
  
Domain Detected: {domain}  
  
Business Insights:  
- Descriptive: {insights.get('descriptive', 'N/A')[:200]}...  
- Predictive: {insights.get('predictive', 'N/A')[:200]}...  
- Domain-specific: {insights.get('domain_related', 'N/A')[:200]}...  
  
Tree-of-Thought Analysis:  
{thoughts[:300]}...  
  
Generated Visualizations: {len(figure_files)} charts  
Output Directory: {output_dir}  
  
The complete dashboard combines:  
1. Automated domain detection and business insights  
2. Three-expert Tree-of-Thought visualization reasoning  
3. Professional chart generation with domain context  
"""  
              
            return Response(message=response_text, break_loop=False)  
              
        except Exception as e:  
            return Response(message=f"Complete dashboard generation failed: {str(e)}", break_loop=False)
