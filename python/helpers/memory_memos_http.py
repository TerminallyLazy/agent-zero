"""
MemoryOS HTTP API integration for Agent Zero memory system.

This module provides MemoryOS-compatible wrapper classes that maintain the same interface
as Agent Zero's existing FAISS-based memory system while leveraging MemoryOS's advanced
memory capabilities through HTTP API calls.
"""

import json
import os
import uuid
from enum import Enum
from typing import Any, Optional, Dict, List
import asyncio
from datetime import datetime
import httpx

from langchain_core.documents import Document

from agent import Agent
from python.helpers import files
from python.helpers.log import LogItem
from python.helpers.print_style import PrintStyle
from python.helpers.memory import Memory
from python.helpers import knowledge_import
from python.helpers.model_config import ModelConfig


class MemoryArea(Enum):
    """Memory areas for categorizing different types of content."""
    MAIN = "main"
    FRAGMENTS = "fragments"
    SOLUTIONS = "solutions"
    INSTRUMENTS = "instruments"


class MemOSClient:
    """HTTP client for communicating with MemoryOS API."""
    
    def __init__(self, host: str, memory_cube_id: str, user_id: str):
        self.host = host.rstrip('/')
        self.memory_cube_id = memory_cube_id
        self.user_id = user_id
        self.client = httpx.AsyncClient(timeout=30.0)

    async def add_memory(self, text: str, metadata: Dict[str, Any], user_id: str = None) -> str:
        """Add memory to MemoryOS via HTTP API."""
        try:
            target_user_id = user_id or self.user_id
            
            response = await self.client.post(
                f"{self.host}/memories",
                json={
                    "memory_content": text,
                    "user_id": target_user_id,
                    "mem_cube_id": self.memory_cube_id
                }
            )
            
            if response.status_code == 200:
                result = response.json()
                return str(uuid.uuid4())  # Return a unique ID for the memory
            else:
                raise Exception(f"Failed to add memory: {response.text}")
                
        except Exception as e:
            raise Exception(f"Error adding memory to MemoryOS: {e}")

    async def search_memories(self, query: str, limit: int = 5, user_id: str = None) -> List[Dict[str, Any]]:
        """Search memories in MemoryOS via HTTP API."""
        try:
            target_user_id = user_id or self.user_id
            
            response = await self.client.post(
                f"{self.host}/search",
                json={
                    "query": query,
                    "user_id": target_user_id,
                    "install_cube_ids": [self.memory_cube_id]
                }
            )
            
            if response.status_code == 200:
                result = response.json()
                memories = []
                
                # Extract text memories from response
                if result.get("data", {}).get("text_mem"):
                    for cube_data in result["data"]["text_mem"]:
                        for memory in cube_data.get("memories", []):
                            memories.append({
                                "id": str(uuid.uuid4()),
                                "text": memory.get("memory", ""),
                                "score": 1.0,  # MemoryOS doesn't return scores
                                "metadata": memory.get("metadata", {})
                            })
                
                return memories[:limit]
            else:
                raise Exception(f"Failed to search memories: {response.text}")
                
        except Exception as e:
            print(f"Error searching MemoryOS: {e}")
            return []

    async def register_cube(self):
        """Register the memory cube with MemoryOS."""
        try:
            response = await self.client.post(
                f"{self.host}/mem_cubes",
                json={
                    "mem_cube_name_or_path": self.memory_cube_id,
                    "mem_cube_id": self.memory_cube_id,
                    "user_id": self.user_id
                }
            )
            
            if response.status_code == 200:
                return True
            else:
                print(f"Warning: Failed to register cube: {response.text}")
                return False
                
        except Exception as e:
            print(f"Warning: Error registering cube: {e}")
            return False

    async def close(self):
        """Close the HTTP client."""
        await self.client.aclose()


class MemOSMemory(Memory):
    """
    MemoryOS integration maintaining Agent Zero Memory interface compatibility.
    """
    
    index: dict[str, "MemOSMemory"] = {}
    
    @staticmethod
    async def get(agent: Agent) -> "MemOSMemory":
        """Get or create MemOS memory instance for the given agent."""
        memory_subdir = agent.config.memory_subdir or "default"
        
        if memory_subdir not in MemOSMemory.index:
            log_item = agent.context.log.log(
                f"Initializing MemOS memory for: {memory_subdir}",
                "memory", PrintStyle.BOLD
            )
            
            client = MemOSMemory.initialize(
                log_item,
                agent.config.models.get_model_config("llm"),
                memory_subdir,
                agent.config
            )
            
            MemOSMemory.index[memory_subdir] = MemOSMemory(
                agent, client, memory_subdir
            )
            
            log_item.update(heading="MemOS memory initialized")
        
        return MemOSMemory.index[memory_subdir]

    @staticmethod
    async def get_new(agent: Agent) -> "MemOSMemory":
        """Reload the MemOS memory instance for the given agent."""
        memory_subdir = agent.config.memory_subdir or "default"
        if MemOSMemory.index.get(memory_subdir):
            del MemOSMemory.index[memory_subdir]
        return await MemOSMemory.get(agent)

    @staticmethod
    def initialize(
        log_item: LogItem | None,
        model_config: ModelConfig,
        memory_subdir: str,
        agent_config: "AgentConfig"
    ) -> "MemOSClient":
        """Initialize MemoryOS HTTP client."""
        
        if log_item:
            log_item.update(heading="Connecting to MemoryOS...")
        
        # Extract MemoryOS configuration from agent config
        host = agent_config.memos_host or "http://localhost:8080"
        user_id = agent_config.memos_user_id or "agent_zero"
        
        # Create memory cube ID with user isolation
        memory_cube_id = f"agent_zero_{memory_subdir}"
        
        try:
            client = MemOSClient(host, memory_cube_id, user_id)
        except Exception as e:
            if log_item:
                log_item.update(heading=f"Failed to connect to MemoryOS: {e}")
            raise ValueError(f"Failed to initialize MemoryOS client: {e}")
        
        if log_item:
            log_item.update(heading=f"MemoryOS connected - User: {user_id}, Host: {host}")
        
        return client

    def __init__(
        self,
        agent: Agent,
        client: "MemOSClient",
        memory_subdir: str,
    ):
        self.agent = agent
        self.client = client
        self.memory_subdir = memory_subdir

    async def preload_knowledge(
        self, log_item: LogItem | None, kn_dirs: list[str], memory_subdir: str
    ):
        """Preload knowledge files into MemoryOS memory cubes."""
        if log_item:
            log_item.update(heading="Preloading knowledge into MemoryOS...")

        # Register cube first
        await self.client.register_cube()

        # Create directory for tracking knowledge imports
        db_dir = self._abs_db_dir(memory_subdir)
        index_path = files.get_abs_path(db_dir, "knowledge_import.json")

        # Ensure directory exists
        if not os.path.exists(db_dir):
            os.makedirs(db_dir)

        # Load existing import index
        index: dict[str, knowledge_import.KnowledgeImport] = {}
        if os.path.exists(index_path):
            with open(index_path, "r") as f:
                index = json.load(f)

        # Process knowledge directories
        files_processed = 0
        for kn_dir in kn_dirs:
            if log_item:
                log_item.stream(progress=f"\nProcessing knowledge directory: {kn_dir}")
            
            processed = await self._import_knowledge_dir(kn_dir, index, log_item)
            files_processed += processed

        # Save updated index
        with open(index_path, "w") as f:
            json.dump(index, f, indent=2)

        if log_item:
            log_item.update(heading=f"Knowledge preloading complete - {files_processed} files processed")

    async def _import_knowledge_dir(
        self, kn_dir: str, index: dict, log_item: LogItem | None
    ) -> int:
        """Import knowledge from a directory."""
        files_processed = 0
        
        for root, dirs, files_list in os.walk(kn_dir):
            for file_name in files_list:
                if file_name.endswith(('.txt', '.md', '.json')):
                    file_path = os.path.join(root, file_name)
                    
                    # Check if file needs to be imported
                    file_stats = os.stat(file_path)
                    file_key = file_path
                    
                    if (file_key not in index or 
                        index[file_key].get('modified_time', 0) < file_stats.st_mtime):
                        
                        try:
                            with open(file_path, 'r', encoding='utf-8') as f:
                                content = f.read()
                            
                            # Add to MemoryOS
                            await self.client.add_memory(
                                content,
                                {
                                    "source": "knowledge_import",
                                    "file_path": file_path,
                                    "area": MemoryArea.MAIN.value
                                }
                            )
                            
                            # Update index
                            index[file_key] = {
                                'file_path': file_path,
                                'modified_time': file_stats.st_mtime,
                                'imported_at': datetime.now().isoformat()
                            }
                            
                            files_processed += 1
                            
                            if log_item:
                                log_item.stream(progress=f"Imported: {file_name}")
                                
                        except Exception as e:
                            if log_item:
                                log_item.stream(progress=f"Error importing {file_name}: {e}")
        
        return files_processed

    def _abs_db_dir(self, memory_subdir: str) -> str:
        """Get absolute path to memory database directory."""
        return files.get_abs_path("memory", "memos", memory_subdir)

    async def search(
        self, query: str, memory_subdir: str = "", count: int = 5
    ) -> list[Document]:
        """Search memories using MemoryOS HTTP API."""
        try:
            memories = await self.client.search_memories(query, limit=count)
            
            documents = []
            for memory in memories:
                doc = Document(
                    page_content=memory["text"],
                    metadata={
                        **memory.get("metadata", {}),
                        "id": memory["id"],
                        "score": memory.get("score", 1.0),
                        "source": "memos"
                    }
                )
                documents.append(doc)
            
            return documents
            
        except Exception as e:
            print(f"Error searching MemoryOS: {e}")
            return []

    async def search_similarity_threshold(
        self, query: str, memory_subdir: str = "", threshold: float = 0.1, count: int = 5
    ) -> list[Document]:
        """Search memories with similarity threshold."""
        # MemoryOS doesn't provide similarity scores, so we'll use regular search
        return await self.search(query, memory_subdir, count)

    async def store(
        self,
        documents: list[Document],
        memory_subdir: str = "",
        memory_area: MemoryArea = MemoryArea.MAIN
    ):
        """Store documents in MemoryOS."""
        try:
            for doc in documents:
                metadata = {
                    **doc.metadata,
                    "area": memory_area.value,
                    "stored_at": datetime.now().isoformat()
                }
                
                await self.client.add_memory(
                    doc.page_content,
                    metadata
                )
                
        except Exception as e:
            print(f"Error storing documents in MemoryOS: {e}")

    async def close(self):
        """Close MemoryOS client connection."""
        if hasattr(self.client, 'close'):
            await self.client.close()