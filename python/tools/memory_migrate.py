"""
Memory migration tool for moving data between FAISS and MemOS backends.
"""

import asyncio
from typing import Dict, List, Any
from python.helpers.memory import Memory
from python.helpers.memory_memos import MemOSMemory
from python.helpers.tool import Tool, Response


class MemoryMigrate(Tool):
    """Tool to migrate memories between FAISS and MemOS backends."""

    async def execute(self, action="", source_backend="", target_backend="", 
                     area_filter="", dry_run=False, batch_size=10, **kwargs):
        
        if not action:
            return Response(
                message="Please specify an action: 'migrate', 'sync', 'compare', or 'backup'",
                break_loop=False
            )
        
        try:
            if action == "migrate":
                result = await self._migrate_memories(source_backend, target_backend, area_filter, dry_run, batch_size)
            elif action == "sync":
                result = await self._sync_backends(source_backend, target_backend, area_filter, dry_run)
            elif action == "compare":
                result = await self._compare_backends(source_backend, target_backend, area_filter)
            elif action == "backup":
                result = await self._backup_memories(source_backend, area_filter)
            else:
                result = f"Unknown action: {action}"
        
        except Exception as e:
            result = f"Migration error: {str(e)}"
        
        return Response(message=result, break_loop=False)

    async def _migrate_memories(self, source: str, target: str, area_filter: str, 
                               dry_run: bool, batch_size: int) -> str:
        """Migrate memories from source backend to target backend."""
        
        if not source or not target:
            return "Please specify both source_backend and target_backend (faiss or memos)"
        
        if source == target:
            return "Source and target backends cannot be the same"
        
        # Get source memory instance
        source_memory = await self._get_backend_instance(source)
        if not source_memory:
            return f"Failed to initialize {source} backend"
        
        # Get target memory instance
        target_memory = await self._get_backend_instance(target)
        if not target_memory:
            return f"Failed to initialize {target} backend"
        
        # Build filter
        filter_str = f"area == '{area_filter}'" if area_filter else ""
        
        # Get memories from source
        source_docs = await source_memory.search_similarity_threshold(
            query="*", limit=10000, threshold=0.0, filter=filter_str
        )
        
        if not source_docs:
            return f"No memories found in {source} backend"
        
        if dry_run:
            return f"DRY RUN: Would migrate {len(source_docs)} memories from {source} to {target}"
        
        # Migrate in batches
        migrated_count = 0
        failed_count = 0
        
        for i in range(0, len(source_docs), batch_size):
            batch = source_docs[i:i + batch_size]
            
            try:
                # Insert batch into target
                await target_memory.insert_documents(batch)
                migrated_count += len(batch)
                
                # Optional: Remove from source after successful migration
                # source_ids = [doc.metadata.get("id") for doc in batch if doc.metadata.get("id")]
                # if source_ids:
                #     await source_memory.delete_documents_by_ids(source_ids)
                
            except Exception as e:
                # Log error but continue with next batch
                pass
                failed_count += len(batch)
        
        return f"Migration complete: {migrated_count} memories migrated, {failed_count} failed"

    async def _sync_backends(self, source: str, target: str, area_filter: str, dry_run: bool) -> str:
        """Synchronize memories between backends (bidirectional)."""
        
        if not source or not target:
            return "Please specify both source_backend and target_backend"
        
        source_memory = await self._get_backend_instance(source)
        target_memory = await self._get_backend_instance(target)
        
        if not source_memory or not target_memory:
            return "Failed to initialize one or both backends"
        
        filter_str = f"area == '{area_filter}'" if area_filter else ""
        
        # Get memories from both backends
        source_docs = await source_memory.search_similarity_threshold(
            query="*", limit=10000, threshold=0.0, filter=filter_str
        )
        target_docs = await target_memory.search_similarity_threshold(
            query="*", limit=10000, threshold=0.0, filter=filter_str
        )
        
        # Find differences
        source_content = {doc.page_content[:100]: doc for doc in source_docs}
        target_content = {doc.page_content[:100]: doc for doc in target_docs}
        
        source_only = [doc for key, doc in source_content.items() if key not in target_content]
        target_only = [doc for key, doc in target_content.items() if key not in source_content]
        
        if dry_run:
            return f"DRY RUN: Would sync {len(source_only)} memories from {source} to {target}, {len(target_only)} from {target} to {source}"
        
        # Sync missing memories
        synced_count = 0
        
        if source_only:
            await target_memory.insert_documents(source_only)
            synced_count += len(source_only)
        
        if target_only:
            await source_memory.insert_documents(target_only)
            synced_count += len(target_only)
        
        return f"Synchronization complete: {synced_count} memories synchronized"

    async def _compare_backends(self, source: str, target: str, area_filter: str) -> str:
        """Compare memories between backends."""
        
        if not source or not target:
            return "Please specify both source_backend and target_backend"
        
        source_memory = await self._get_backend_instance(source)
        target_memory = await self._get_backend_instance(target)
        
        if not source_memory or not target_memory:
            return "Failed to initialize one or both backends"
        
        filter_str = f"area == '{area_filter}'" if area_filter else ""
        
        # Get memories from both backends
        source_docs = await source_memory.search_similarity_threshold(
            query="*", limit=10000, threshold=0.0, filter=filter_str
        )
        target_docs = await target_memory.search_similarity_threshold(
            query="*", limit=10000, threshold=0.0, filter=filter_str
        )
        
        # Analyze differences
        source_content = {doc.page_content[:100]: doc for doc in source_docs}
        target_content = {doc.page_content[:100]: doc for doc in target_docs}
        
        common_count = len(set(source_content.keys()) & set(target_content.keys()))
        source_only_count = len(set(source_content.keys()) - set(target_content.keys()))
        target_only_count = len(set(target_content.keys()) - set(source_content.keys()))
        
        # Area breakdown
        source_areas = {}
        target_areas = {}
        
        for doc in source_docs:
            area = doc.metadata.get("area", "unknown")
            source_areas[area] = source_areas.get(area, 0) + 1
        
        for doc in target_docs:
            area = doc.metadata.get("area", "unknown")
            target_areas[area] = target_areas.get(area, 0) + 1
        
        comparison = [
            f"**Backend Comparison Report**",
            f"",
            f"📊 **Memory Counts:**",
            f"• {source}: {len(source_docs)} memories",
            f"• {target}: {len(target_docs)} memories",
            f"• Common: {common_count} memories",
            f"• Only in {source}: {source_only_count} memories",
            f"• Only in {target}: {target_only_count} memories",
            f"",
            f"📁 **{source.title()} Areas:**"
        ]
        
        for area, count in sorted(source_areas.items()):
            comparison.append(f"• {area}: {count}")
        
        comparison.append(f"\n📁 **{target.title()} Areas:**")
        for area, count in sorted(target_areas.items()):
            comparison.append(f"• {area}: {count}")
        
        return "\n".join(comparison)

    async def _backup_memories(self, backend: str, area_filter: str) -> str:
        """Create a backup of memories from specified backend."""
        
        if not backend:
            return "Please specify backend (faiss or memos)"
        
        memory = await self._get_backend_instance(backend)
        if not memory:
            return f"Failed to initialize {backend} backend"
        
        filter_str = f"area == '{area_filter}'" if area_filter else ""
        
        # Get all memories
        docs = await memory.search_similarity_threshold(
            query="*", limit=10000, threshold=0.0, filter=filter_str
        )
        
        if not docs:
            return f"No memories found in {backend} backend"
        
        # Create backup data
        backup_data = {
            "backend": backend,
            "area_filter": area_filter or "all",
            "timestamp": memory.get_timestamp(),
            "memory_count": len(docs),
            "memories": []
        }
        
        for doc in docs:
            backup_data["memories"].append({
                "content": doc.page_content,
                "metadata": doc.metadata
            })
        
        # Save backup file
        import json
        backup_filename = f"memory_backup_{backend}_{area_filter or 'all'}_{backup_data['timestamp'].replace(':', '-').replace(' ', '_')}.json"
        backup_path = f"memory/{self.agent.config.memory_subdir or 'default'}/{backup_filename}"
        
        from python.helpers import files
        files.write_file(files.get_abs_path(backup_path), json.dumps(backup_data, indent=2))
        
        return f"Backup created: {backup_filename} ({len(docs)} memories)"

    async def _get_backend_instance(self, backend: str):
        """Get a memory backend instance."""
        
        if backend.lower() == "faiss":
            # Temporarily configure for FAISS
            original_backend = getattr(self.agent.config, 'memory_backend', 'faiss')
            original_enabled = getattr(self.agent.config, 'memos_enabled', False)
            
            self.agent.config.memory_backend = 'faiss'
            self.agent.config.memos_enabled = False
            
            try:
                memory = await Memory.get(self.agent)
                return memory
            finally:
                self.agent.config.memory_backend = original_backend
                self.agent.config.memos_enabled = original_enabled
        
        elif backend.lower() == "memos":
            # Temporarily configure for MemOS
            original_backend = getattr(self.agent.config, 'memory_backend', 'faiss')
            original_enabled = getattr(self.agent.config, 'memos_enabled', False)
            
            self.agent.config.memory_backend = 'memos'
            self.agent.config.memos_enabled = True
            
            try:
                memory = await MemOSMemory.get(self.agent)
                return memory
            except Exception as e:
                # MemOS initialization failed, return None
                pass
                return None
            finally:
                self.agent.config.memory_backend = original_backend
                self.agent.config.memos_enabled = original_enabled
        
        else:
            return None