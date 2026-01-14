from python.helpers import persist_chat, tokens, files
from python.helpers.extension import Extension
from agent import LoopData
import asyncio
import os


class RenameChat(Extension):

    async def execute(self, loop_data: LoopData = LoopData(), **kwargs):
        asyncio.create_task(self.change_name())

    async def change_name(self):
        try:
            # prepare history
            history_text = self.agent.history.output_text()
            ctx_length = min(
                int(self.agent.config.utility_model.ctx_length * 0.7), 5000
            )
            history_text = tokens.trim_to_tokens(history_text, ctx_length, "start")
            # prepare system and user prompt
            system = self.agent.read_prompt("fw.rename_chat.sys.md")
            current_name = self.agent.context.name
            message = self.agent.read_prompt(
                "fw.rename_chat.msg.md", current_name=current_name, history=history_text
            )
            # call utility model
            new_name = await self.agent.call_utility_model(
                system=system, message=message, background=True
            )
            # update name
            if new_name:
                # trim name to max length if needed
                if len(new_name) > 40:
                    new_name = new_name[:40] + "..."
                # apply to context and save
                self.agent.context.name = new_name
                persist_chat.save_tmp_chat(self.agent.context)

                # Rename folder to match new title (if using new slug-based format)
                try:
                    with persist_chat._migration_lock:  # FIX: Add locking
                        old_folder = persist_chat.get_chat_folder_path(self.agent.context.id)
                        new_folder_name = persist_chat._get_folder_name_for_context(self.agent.context)
                        new_folder = files.get_abs_path(persist_chat.CHATS_FOLDER, new_folder_name)

                        # FIX: Check destination doesn't exist (prevent data loss)
                        if old_folder != new_folder and os.path.exists(old_folder) and not os.path.exists(new_folder):
                            os.rename(old_folder, new_folder)
                            persist_chat._update_folder_cache(self.agent.context.id, new_folder_name)
                except Exception as e:
                    print(f"Warning: Failed to rename chat folder: {e}")  # FIX: Add logging
        except Exception as e:
            pass  # non-critical
