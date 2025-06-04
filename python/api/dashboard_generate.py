from python.helpers.api import ApiHandler  
from python.helpers.tool import Tool  
from python.tools.dashboard_tool import DashboardTool  
from python.helpers.files import get_abs_path
from python.helpers.chart_utils import (  
    fix_legends, create_color_palette, enhance_plot,   
    fix_pie_chart, fix_multiple_series  
)  
from python.helpers.d2insight_agent_sys import run_domain_detector  

from flask import Request, Response as FlaskResponse  
import json
from agent import Agent, AgentConfig, ModelConfig
import models

class DashboardGenerate(ApiHandler):  
      
    async def process(self, input: dict, request: Request) -> dict | FlaskResponse:  
        try:  
            csv_path = input.get("csv_path", "")  
            chart_type = input.get("chart_type", "auto")  
              
            if not csv_path:  
                return {"error": "No CSV path provided"}  
              
            # Create a mock agent context for the tool  
            # This would need to be adapted to work with Agent Zero's agent system
            config = AgentConfig(
                chat_model=ModelConfig(provider=models.ModelProvider.OPENAI, name="gpt-4.1"),
                utility_model=ModelConfig(provider=models.ModelProvider.OPENAI, name="gpt-4.1"),
                embeddings_model=ModelConfig(provider=models.ModelProvider.OPENAI, name="text-embedding-3-small"),
                browser_model=ModelConfig(provider=models.ModelProvider.OPENAI, name="gpt-4.1"),
                mcp_servers=""
            )
            agent = Agent(0, config)
            tool = DashboardTool(agent=agent, name="dashboard_tool", args=input, message="", method="async")
              
            result = await tool.execute(csv_path=csv_path, chart_type=chart_type)  
              
            return {  
                "success": True,  
                "message": result.message,  
                "chart_path": "work_dir/dashboard_chart.png"  
            }  
              
        except Exception as e:  
            return {"error": f"Dashboard generation failed: {str(e)}"}
