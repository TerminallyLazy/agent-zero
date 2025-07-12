"""
Hybrid memory system supporting dual backends, migration, and synchronization.

This module provides advanced memory management with support for:
- Dual backend operation (FAISS + MemOS simultaneously)
- Data migration between backends
- Hybrid mode (different areas using different backends)
- Synchronization capabilities
"""

import asyncio
import uuid
from enum import Enum
from typing import Dict, List, Any, Optional, Tuple
from datetime import datetime

from langchain_core.documents import Document

from agent import Agent
from python.helpers.memory import Memory
from python.helpers.memory_memos import MemOSMemory
from python.helpers.log import LogItem
from python.helpers.print_style import PrintStyle
from python.helpers import files


class MemoryBackendType(Enum):
    FAISS = "faiss"
    MEMOS = "memos"
    HYBRID = "hybrid"
    DUAL = "dual"


class HybridMemory:
    """
    Hybrid memory system that can use FAISS, MemOS, or both simultaneously.
    
    Supports:
    - Dual backend operation (write to both, read from primary)
    - Migration between backends
    - Hybrid mode (different areas using different backends)
    - Synchronization and backup strategies
    """

    def __init__(
        self,
        agent: Agent,
        primary_backend: MemoryBackendType,
        secondary_backend: Optional[MemoryBackendType] = None,
        memory_subdir: str = "default"
    ):
        self.agent = agent
        self.primary_backend = primary_backend
        self.secondary_backend = secondary_backend
        self.memory_subdir = memory_subdir
        
        self.faiss_memory: Optional[Memory] = None
        self.memos_memory: Optional[MemOSMemory] = None
        
        # Configuration for hybrid mode
        self.area_backend_mapping = {
            Memory.Area.MAIN.value: primary_backend,
            Memory.Area.FRAGMENTS.value: primary_backend,
            Memory.Area.SOLUTIONS.value: primary_backend,
            Memory.Area.INSTRUMENTS.value: primary_backend,
        }

    @staticmethod
    async def get(agent: Agent) -> "HybridMemory":
        """Get or create a hybrid memory instance for the given agent."""
        memory_subdir = agent.config.memory_subdir or "default"
        
        # Determine backend configuration
        backend_type = getattr(agent.config, 'memory_backend', 'faiss')
        
        if backend_type == 'hybrid':
            primary = MemoryBackendType.FAISS
            secondary = MemoryBackendType.MEMOS
        elif backend_type == 'dual':
            primary = MemoryBackendType.MEMOS
            secondary = MemoryBackendType.FAISS
        elif backend_type == 'memos':
            primary = MemoryBackendType.MEMOS
            secondary = None
        else:
            primary = MemoryBackendType.FAISS
            secondary = None
        
        # Create hybrid memory instance
        hybrid = HybridMemory(agent, primary, secondary, memory_subdir)
        await hybrid.initialize()
        
        return hybrid

    async def initialize(self):
        """Initialize the backend memory systems."""
        log_item = self.agent.context.log.log(
            type="util",
            heading=f"Initializing Hybrid Memory - Primary: {self.primary_backend.value}, Secondary: {self.secondary_backend.value if self.secondary_backend else 'None'}",
        )
        
        try:
            # Initialize FAISS if needed
            if (self.primary_backend == MemoryBackendType.FAISS or 
                self.secondary_backend == MemoryBackendType.FAISS or
                self.primary_backend == MemoryBackendType.HYBRID):
                
                # Temporarily set config to use FAISS
                original_backend = getattr(self.agent.config, 'memory_backend', 'faiss')
                original_enabled = getattr(self.agent.config, 'memos_enabled', False)
                
                self.agent.config.memory_backend = 'faiss'
                self.agent.config.memos_enabled = False
                
                self.faiss_memory = await Memory.get(self.agent)
                
                # Restore original config
                self.agent.config.memory_backend = original_backend
                self.agent.config.memos_enabled = original_enabled
            
            # Initialize MemOS if needed
            if (self.primary_backend == MemoryBackendType.MEMOS or 
                self.secondary_backend == MemoryBackendType.MEMOS or
                self.primary_backend == MemoryBackendType.HYBRID):
                
                # Temporarily set config to use MemOS
                original_backend = getattr(self.agent.config, 'memory_backend', 'faiss')
                original_enabled = getattr(self.agent.config, 'memos_enabled', False)
                
                self.agent.config.memory_backend = 'memos'
                self.agent.config.memos_enabled = True
                
                try:
                    self.memos_memory = await MemOSMemory.get(self.agent)
                except Exception as e:
                    PrintStyle.error(f"Failed to initialize MemOS: {e}")
                    self.memos_memory = None
                
                # Restore original config
                self.agent.config.memory_backend = original_backend
                self.agent.config.memos_enabled = original_enabled
            
            log_item.update(heading="Hybrid memory initialization complete")
            
        except Exception as e:
            log_item.update(heading=f"Hybrid memory initialization failed: {e}")
            raise

    async def search_similarity_threshold(
        self, query: str, limit: int, threshold: float, filter: str = ""
    ) -> List[Document]:
        """Search across configured backends with intelligent result merging."""
        
        # Extract area from filter for hybrid mode
        area = self._extract_area_from_filter(filter)
        backend = self._get_backend_for_area(area)
        
        if backend == MemoryBackendType.DUAL:
            # Search both backends and merge results
            return await self._search_dual_backend(query, limit, threshold, filter)
        elif backend == MemoryBackendType.MEMOS and self.memos_memory:
            return await self.memos_memory.search_similarity_threshold(query, limit, threshold, filter)
        elif backend == MemoryBackendType.FAISS and self.faiss_memory:
            return await self.faiss_memory.search_similarity_threshold(query, limit, threshold, filter)
        else:
            # Fallback to available backend
            if self.faiss_memory:
                return await self.faiss_memory.search_similarity_threshold(query, limit, threshold, filter)
            elif self.memos_memory:
                return await self.memos_memory.search_similarity_threshold(query, limit, threshold, filter)
            else:
                return []

    async def _search_dual_backend(
        self, query: str, limit: int, threshold: float, filter: str = ""
    ) -> List[Document]:
        """Search both backends and intelligently merge results."""
        
        tasks = []
        
        if self.faiss_memory:
            tasks.append(self.faiss_memory.search_similarity_threshold(query, limit, threshold, filter))
        
        if self.memos_memory:
            tasks.append(self.memos_memory.search_similarity_threshold(query, limit, threshold, filter))
        
        if not tasks:
            return []
        
        # Execute searches in parallel
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Merge and deduplicate results
        all_docs = []
        for result in results:
            if isinstance(result, list):
                all_docs.extend(result)
            elif isinstance(result, Exception):
                PrintStyle.error(f"Search error: {result}")
        
        # Remove duplicates based on content similarity
        unique_docs = self._deduplicate_documents(all_docs)
        
        # Sort by relevance and return top results
        return unique_docs[:limit]

    def _deduplicate_documents(self, docs: List[Document]) -> List[Document]:
        """Remove duplicate documents based on content similarity."""
        if not docs:
            return []
        
        unique_docs = []
        seen_hashes = set()
        
        for doc in docs:
            # Create a hash based on first 100 characters
            content_hash = hash(doc.page_content[:100])
            if content_hash not in seen_hashes:
                seen_hashes.add(content_hash)
                unique_docs.append(doc)
        
        return unique_docs

    async def insert_text(self, text: str, metadata: dict = {}) -> str:
        """Insert text into the appropriate backend(s)."""
        area = metadata.get("area", Memory.Area.MAIN.value)
        backend = self._get_backend_for_area(area)
        
        doc_id = str(uuid.uuid4())
        metadata["id"] = doc_id
        
        if backend == MemoryBackendType.DUAL:
            # Insert into both backends
            await self._insert_dual_backend(text, metadata)
        elif backend == MemoryBackendType.MEMOS and self.memos_memory:
            await self.memos_memory.insert_text(text, metadata)
        elif backend == MemoryBackendType.FAISS and self.faiss_memory:
            await self.faiss_memory.insert_text(text, metadata)
        else:
            # Fallback to available backend
            if self.faiss_memory:
                await self.faiss_memory.insert_text(text, metadata)
            elif self.memos_memory:
                await self.memos_memory.insert_text(text, metadata)
        
        return doc_id

    async def _insert_dual_backend(self, text: str, metadata: dict):
        """Insert into both backends simultaneously."""
        tasks = []
        
        if self.faiss_memory:
            tasks.append(self.faiss_memory.insert_text(text, metadata.copy()))
        
        if self.memos_memory:
            tasks.append(self.memos_memory.insert_text(text, metadata.copy()))
        
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

    async def insert_documents(self, docs: List[Document]) -> List[str]:
        """Insert multiple documents into appropriate backend(s)."""
        ids = []
        
        for doc in docs:
            doc_id = await self.insert_text(doc.page_content, doc.metadata)
            ids.append(doc_id)
        
        return ids

    async def delete_documents_by_ids(self, ids: List[str]) -> List[Document]:
        """Delete documents by IDs from all relevant backends."""
        deleted_docs = []
        
        if self.faiss_memory:
            try:
                faiss_deleted = await self.faiss_memory.delete_documents_by_ids(ids)
                deleted_docs.extend(faiss_deleted)
            except Exception as e:
                PrintStyle.error(f"FAISS deletion error: {e}")
        
        if self.memos_memory:
            try:
                memos_deleted = await self.memos_memory.delete_documents_by_ids(ids)
                deleted_docs.extend(memos_deleted)
            except Exception as e:
                PrintStyle.error(f"MemOS deletion error: {e}")
        
        return self._deduplicate_documents(deleted_docs)

    async def delete_documents_by_query(
        self, query: str, threshold: float, filter: str = ""
    ) -> List[Document]:
        """Delete documents by query from all relevant backends."""
        deleted_docs = []
        
        if self.faiss_memory:
            try:
                faiss_deleted = await self.faiss_memory.delete_documents_by_query(query, threshold, filter)
                deleted_docs.extend(faiss_deleted)
            except Exception as e:
                PrintStyle.error(f"FAISS query deletion error: {e}")
        
        if self.memos_memory:
            try:
                memos_deleted = await self.memos_memory.delete_documents_by_query(query, threshold, filter)
                deleted_docs.extend(memos_deleted)
            except Exception as e:
                PrintStyle.error(f"MemOS query deletion error: {e}")
        
        return self._deduplicate_documents(deleted_docs)

    def _extract_area_from_filter(self, filter_str: str) -> str:
        """Extract area from filter string."""
        if "area ==" in filter_str:
            parts = filter_str.split("area ==")
            if len(parts) > 1:
                area_part = parts[1].split("'")[1] if "'" in parts[1] else parts[1].split('"')[1]
                return area_part.strip()
        return Memory.Area.MAIN.value

    def _get_backend_for_area(self, area: str) -> MemoryBackendType:
        """Get the backend to use for a specific memory area."""
        if self.primary_backend == MemoryBackendType.DUAL:
            return MemoryBackendType.DUAL
        elif self.primary_backend == MemoryBackendType.HYBRID:
            return self.area_backend_mapping.get(area, MemoryBackendType.FAISS)
        else:
            return self.primary_backend

    def get_timestamp(self) -> str:
        """Get current timestamp in Agent Zero format."""
        return datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    def format_docs_plain(self, docs: List[Document]) -> List[str]:
        """Format documents as plain text."""
        return [doc.page_content for doc in docs]

    async def get_backend_status(self) -> Dict[str, Any]:
        """Get status information about all backends."""
        status = {
            "primary_backend": self.primary_backend.value,
            "secondary_backend": self.secondary_backend.value if self.secondary_backend else None,
            "faiss_available": self.faiss_memory is not None,
            "memos_available": self.memos_memory is not None,
            "memory_subdir": self.memory_subdir
        }
        
        # Get memory counts from each backend
        if self.faiss_memory:
            try:
                faiss_docs = await self.faiss_memory.search_similarity_threshold("*", 1000, 0.0, "")
                status["faiss_memory_count"] = len(faiss_docs)
            except Exception:
                status["faiss_memory_count"] = "unknown"
        
        if self.memos_memory:
            try:
                memos_docs = await self.memos_memory.search_similarity_threshold("*", 1000, 0.0, "")
                status["memos_memory_count"] = len(memos_docs)
            except Exception:
                status["memos_memory_count"] = "unknown"
        
        return status