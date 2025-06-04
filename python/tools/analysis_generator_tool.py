import json  
import subprocess  
import tempfile  
from pathlib import Path  
from python.helpers.tool import Tool, Response  
from python.helpers.files import get_abs_path
from python.helpers.generate_and_run import generate_analysis
  
class AnalysisGeneratorTool(Tool):  
      
    async def execute(self, csv_path="", insight_json_path="", model="gpt-4.1", **kwargs):  
        """  
        Generate Tree-of-Thought analysis and visualizations from CSV data and insights  
        """  
        try:  
            # Import the analysis generator  
            from python.helpers.generate_and_run import generate_analysis  
              
            # Validate inputs  
            if not csv_path:  
                return Response(message="Error: No CSV file path provided", break_loop=False)  
            if not insight_json_path:  
                return Response(message="Error: No insight JSON path provided", break_loop=False)  
              
            full_csv_path = get_abs_path(csv_path)  
            full_insight_path = get_abs_path(insight_json_path)  
              
            if not Path(full_csv_path).exists():  
                return Response(message=f"Error: CSV file not found at {csv_path}", break_loop=False)  
            if not Path(full_insight_path).exists():  
                return Response(message=f"Error: Insight JSON not found at {insight_json_path}", break_loop=False)  
              
            # Set up output directory  
            output_dir = get_abs_path("work_dir/analysis_output")  
            Path(output_dir).mkdir(parents=True, exist_ok=True)  
              
            # Generate analysis with Tree-of-Thought approach  
            thoughts = generate_analysis(  
                csv_path=full_csv_path,  
                insight_json_path=full_insight_path,  
                model_config=model,  
                run_code=True,  
                save_dir=output_dir,  
                preserve_domain_insights=True  
            )  
              
            # Check for generated files  
            thoughts_file = Path(output_dir) / "analysis_thoughts.md"  
            code_file = Path(output_dir) / "analysis.py"  
            figures_dir = Path(output_dir) / "figures"  
              
            generated_files = []  
            if thoughts_file.exists():  
                generated_files.append(str(thoughts_file))  
            if code_file.exists():  
                generated_files.append(str(code_file))  
            if figures_dir.exists():  
                figure_files = list(figures_dir.glob("*.png"))  
                generated_files.extend([str(f) for f in figure_files])  
              
            response_text = f"""Tree-of-Thought Analysis Generated Successfully!  
  
Generated Files:  
{chr(10).join(f"- {f}" for f in generated_files)}  
  
Analysis Thoughts Preview:  
{thoughts[:500]}...  
  
The analysis used a three-expert Tree-of-Thought approach to:  
1. Extract key domain findings from your insights  
2. Identify relevant data columns  
3. Evaluate data selection through expert consensus  
4. Generate visualizations with domain context  
  
Check the work_dir/analysis_output/ folder for all generated files and visualizations.  
"""  
              
            return Response(message=response_text, break_loop=False)  
              
        except Exception as e:  
            return Response(message=f"Analysis generation failed: {str(e)}", break_loop=False)