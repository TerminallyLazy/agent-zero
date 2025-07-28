from python.helpers.api import ApiHandler, Request, Response
from datetime import datetime, timezone
from typing import Dict, List, Any
import aiohttp


class AgentsList(ApiHandler):
    
    @classmethod
    def requires_auth(cls) -> bool:
        return False
    
    async def process(self, input: dict, request: Request) -> dict | Response:
        """Return list of available agents including main agent and network agents."""
        try:
            agents = []
            
            # Main agent entry
            main_agent = {
                "id": "main",
                "type": "main",
                "name": "Agent Zero",
                "role": "main",
                "status": "active",
                "endpoint": "local",
                "capabilities": ["reasoning", "tools", "memory", "planning"],
                "last_contact": datetime.now(timezone.utc).isoformat(),
                "created_at": datetime.now(timezone.utc).isoformat(),
                "task_count": 0,
                "url": None
            }
            agents.append(main_agent)
            
            # Check for network agents on known ports
            network_ports = [8001, 8002, 8003]
            for port in network_ports:
                try:
                    endpoint = f"http://localhost:{port}"
                    async with aiohttp.ClientSession() as session:
                        async with session.get(f"{endpoint}/acp_ping", timeout=aiohttp.ClientTimeout(total=1)) as response:
                            if response.status == 200:
                                agent_data = {
                                    "id": f"network-{port}",
                                    "type": "peer",
                                    "name": f"Agent {port}",
                                    "role": f"network-agent-{port}",
                                    "status": "online",
                                    "endpoint": endpoint,
                                    "capabilities": ["reasoning", "tools", "memory", "planning"],
                                    "protocol": "ACP",
                                    "last_contact": datetime.now(timezone.utc).isoformat(),
                                    "created_at": datetime.now(timezone.utc).isoformat(),
                                    "task_count": 0,
                                    "url": endpoint
                                }
                                agents.append(agent_data)
                except:
                    # Network agent not available
                    pass
            
            statistics = {
                "total_agents": len(agents),
                "status_counts": {"active": len(agents)},
                "total_tasks": 0,
                "pending_tasks": 0,
                "online_agents": len(agents)
            }
            
            return {
                "success": True,
                "agents": agents,
                "active_agent": "main",
                "statistics": statistics
            }
            
        except Exception as e:
            return {
                "success": False,
                "error": str(e),
                "agents": [],
                "active_agent": "main",
                "statistics": {
                    "total_agents": 1,
                    "status_counts": {"active": 1},
                    "total_tasks": 0,
                    "pending_tasks": 0,
                    "online_agents": 1
                }
            }