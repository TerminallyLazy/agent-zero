"""
Memory backend status and management tool for hybrid and dual backend operations.
"""

from python.helpers.memory import Memory
from python.helpers.tool import Tool, Response


class MemoryBackendStatus(Tool):
    """Tool to check status and manage memory backends."""

    async def execute(self, action="status", **kwargs):
        
        try:
            if action == "status":
                result = await self._get_backend_status()
            elif action == "switch":
                result = await self._switch_backend(kwargs.get("backend", ""))
            elif action == "enable_dual":
                result = await self._enable_dual_backend()
            elif action == "disable_dual":
                result = await self._disable_dual_backend()
            elif action == "sync_status":
                result = await self._get_sync_status()
            else:
                result = f"Unknown action: {action}. Available: status, switch, enable_dual, disable_dual, sync_status"
        
        except Exception as e:
            result = f"Backend status error: {str(e)}"
        
        return Response(message=result, break_loop=False)

    async def _get_backend_status(self) -> str:
        """Get comprehensive status of all memory backends."""
        
        memory = await Memory.get(self.agent)
        
        # Get current configuration
        backend_type = getattr(self.agent.config, 'memory_backend', 'faiss')
        auto_sync = getattr(self.agent.config, 'memory_auto_sync', False)
        
        status_lines = [
            "**MemOS Backend Status**",
            "",
            f"🔧 **Configuration:**",
            f"• Backend Type: {backend_type}",
            f"• MemoryOS Active: {'✓' if backend_type == 'memos' else '✗'}",
            f"• Dual Backend: {'✓' if backend_type == 'dual' else '✗'}",
            f"• Hybrid Mode: {'✓' if backend_type == 'hybrid' else '✗'}",
            f"• Auto Sync: {'✓' if auto_sync else '✗'}",
            f"• Memory Subdir: {self.agent.config.memory_subdir or 'default'}",
            ""
        ]
        
        # Check if this is a hybrid memory instance
        if hasattr(memory, 'get_backend_status'):
            hybrid_status = await memory.get_backend_status()
            status_lines.extend([
                f"📊 **Backend Status:**",
                f"• Primary Backend: {hybrid_status.get('primary_backend', 'unknown')}",
                f"• Secondary Backend: {hybrid_status.get('secondary_backend', 'none')}",
                f"• FAISS Available: {'✓' if hybrid_status.get('faiss_available') else '✗'}",
                f"• MemOS Available: {'✓' if hybrid_status.get('memos_available') else '✗'}",
                ""
            ])
            
            # Memory counts
            faiss_count = hybrid_status.get('faiss_memory_count', 'unknown')
            memos_count = hybrid_status.get('memos_memory_count', 'unknown')
            
            status_lines.extend([
                f"📈 **Memory Counts:**",
                f"• FAISS Memories: {faiss_count}",
                f"• MemOS Memories: {memos_count}",
                ""
            ])
        else:
            # Single backend status
            backend_name = "MemOS" if hasattr(memory, 'client') else "FAISS"
            
            try:
                # Get memory count
                all_memories = await memory.search_similarity_threshold("*", 1000, 0.0, "")
                memory_count = len(all_memories)
                
                status_lines.extend([
                    f"📊 **{backend_name} Backend:**",
                    f"• Status: Active",
                    f"• Memory Count: {memory_count}",
                    ""
                ])
                
                # Area breakdown
                area_counts = {}
                for mem in all_memories:
                    area = mem.metadata.get("area", "unknown")
                    area_counts[area] = area_counts.get(area, 0) + 1
                
                if area_counts:
                    status_lines.append("📁 **Memory Areas:**")
                    for area, count in sorted(area_counts.items()):
                        status_lines.append(f"• {area}: {count}")
                    status_lines.append("")
                
            except Exception as e:
                status_lines.extend([
                    f"📊 **{backend_name} Backend:**",
                    f"• Status: Error - {str(e)}",
                    ""
                ])
        
        # Configuration recommendations
        status_lines.extend([
            "💡 **Recommendations:**"
        ])
        
        if backend_type == 'faiss':
            status_lines.append("• Consider switching to 'hybrid' or 'dual' backend to leverage MemOS")
        
        if backend_type in ['dual', 'hybrid'] and not auto_sync:
            status_lines.append("• Enable auto-sync for dual backend to keep memories synchronized")
        
        return "\n".join(status_lines)

    async def _switch_backend(self, target_backend: str) -> str:
        """Switch to a different backend configuration."""
        
        if not target_backend:
            return "Please specify target backend: faiss, memos, hybrid, or dual"
        
        valid_backends = ['faiss', 'memos', 'hybrid', 'dual']
        if target_backend not in valid_backends:
            return f"Invalid backend. Choose from: {', '.join(valid_backends)}"
        
        current_backend = getattr(self.agent.config, 'memory_backend', 'faiss')
        
        if current_backend == target_backend:
            return f"Already using {target_backend} backend"
        
        # Update configuration
        self.agent.config.memory_backend = target_backend
        
        return f"Switched from {current_backend} to {target_backend} backend. Restart may be required for full effect."

    async def _enable_dual_backend(self) -> str:
        """Enable dual backend operation."""
        
        self.agent.config.memory_backend = 'dual'
        
        return "Dual backend enabled. Both FAISS and MemOS will be used simultaneously."

    async def _disable_dual_backend(self) -> str:
        """Disable dual backend operation."""
        
        current_backend = getattr(self.agent.config, 'memory_backend', 'faiss')
        
        if current_backend != 'dual':
            return "Dual backend is not currently enabled"
        
        self.agent.config.memory_backend = 'faiss'
        
        return "Dual backend disabled. Switched back to FAISS backend."

    async def _get_sync_status(self) -> str:
        """Get synchronization status between backends."""
        
        backend_type = getattr(self.agent.config, 'memory_backend', 'faiss')
        
        if backend_type not in ['dual', 'hybrid']:
            return "Synchronization is only available for dual or hybrid backends"
        
        memory = await Memory.get(self.agent)
        
        if not hasattr(memory, 'get_backend_status'):
            return "Current memory instance does not support sync status"
        
        status = await memory.get_backend_status()
        
        faiss_count = status.get('faiss_memory_count', 0)
        memos_count = status.get('memos_memory_count', 0)
        
        sync_lines = [
            "**Backend Synchronization Status**",
            "",
            f"📊 **Memory Counts:**",
            f"• FAISS: {faiss_count}",
            f"• MemOS: {memos_count}",
            ""
        ]
        
        if faiss_count == memos_count:
            sync_lines.append("✅ **Status:** Backends appear synchronized")
        elif abs(faiss_count - memos_count) <= 5:
            sync_lines.append("⚠️ **Status:** Minor differences detected (within tolerance)")
        else:
            sync_lines.append("❌ **Status:** Significant differences detected")
            sync_lines.append("💡 **Suggestion:** Run memory_migrate with action='sync' to synchronize")
        
        auto_sync = getattr(self.agent.config, 'memory_auto_sync', False)
        sync_lines.extend([
            "",
            f"🔄 **Auto Sync:** {'Enabled' if auto_sync else 'Disabled'}"
        ])
        
        return "\n".join(sync_lines)