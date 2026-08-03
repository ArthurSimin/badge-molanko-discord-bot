import os
import sys
import shutil
import importlib
import gc
from typing import Optional, Dict, Any

class TerminalCommandHandler:
    """处理所有终端命令（通过 stdin 输入）"""

    def __init__(self, bot):
        self.bot = bot

    # ---------- 辅助方法 ----------

    def _get_cog_files(self) -> Dict[str, Dict[str, Any]]:
        """
        返回所有 cog 文件的信息：
        {
            'cog_name': {
                'file': '完整路径',
                'disabled': bool
            }
        }
        - .py 文件：disabled=False
        - .py.disabled 文件：disabled=True
        """
        result = {}
        cogs_dir = self.bot.cogs_dir
        if not os.path.exists(cogs_dir):
            return result

        for filename in os.listdir(cogs_dir):
            if filename.startswith("_"):
                continue
            if filename.endswith(".py"):
                name = filename[:-3]
                result[name] = {
                    "file": os.path.join(cogs_dir, filename),
                    "disabled": False
                }
            elif filename.endswith(".py.disabled"):
                name = filename[:-12]  # 去掉 '.py.disabled'
                result[name] = {
                    "file": os.path.join(cogs_dir, filename),
                    "disabled": True
                }
        return result

    def _is_loaded(self, cog_name: str) -> bool:
        """检查 cog (cogs.<cog_name>) 是否已加载"""
        return f"cogs.{cog_name}" in self.bot.extensions

    def _clear_cog_cache(self, cog_name: str):
        """彻底清除单个 cog 的缓存和 __pycache__"""
        module_prefix = f"cogs.{cog_name}"
        # 1. 从 sys.modules 删除
        to_remove = [mod for mod in list(sys.modules.keys()) if mod == module_prefix or mod.startswith(module_prefix + ".")]
        for mod in to_remove:
            del sys.modules[mod]
            print(f"Removed {mod} from sys.modules")

        # 2. 垃圾回收
        gc.collect()
        print("Ran garbage collection")

        # 3. 删除 __pycache__
        cog_info = self._get_cog_files().get(cog_name)
        if cog_info and os.path.exists(cog_info["file"]):
            pycache_dir = os.path.join(os.path.dirname(cog_info["file"]), "__pycache__")
            if os.path.exists(pycache_dir):
                try:
                    shutil.rmtree(pycache_dir)
                    print(f"Deleted {pycache_dir}")
                except Exception as e:
                    print(f"Failed to delete {pycache_dir}: {e}")

        # 4. 刷新 importlib 缓存
        importlib.invalidate_caches()
        print("Invalidated importlib caches")

    def _clear_utils_cache(self):
        """清除所有 utils 模块的缓存和 __pycache__"""
        utils_dir = self.bot.utils_dir
        if not os.path.exists(utils_dir):
            print("utils directory not found, skipping")
            return

        # 1. 从 sys.modules 删除
        to_remove = [mod for mod in list(sys.modules.keys()) if mod.startswith("utils.")]
        for mod in to_remove:
            del sys.modules[mod]
            print(f"Removed {mod} from sys.modules")

        # 2. 删除所有 __pycache__ 目录
        for root, dirs, files in os.walk(utils_dir):
            if "__pycache__" in dirs:
                pycache_path = os.path.join(root, "__pycache__")
                try:
                    shutil.rmtree(pycache_path)
                    print(f"Deleted {pycache_path}")
                except Exception as e:
                    print(f"Failed to delete {pycache_path}: {e}")

        importlib.invalidate_caches()
        print("Invalidated importlib caches for utils")

    # ---------- 命令分发 ----------

    async def dispatch(self, cmd: str, arg: Optional[str] = None):
        """根据命令名调用对应的处理方法"""
        if cmd == "list":
            await self.cmd_list()
        elif cmd == "reload":
            await self.cmd_reload(arg)
        elif cmd == "stop":
            await self.cmd_stop(arg)
        elif cmd == "load":
            await self.cmd_load(arg)
        elif cmd == "disable":
            await self.cmd_disable(arg)
        elif cmd == "enable":
            await self.cmd_enable(arg)
        elif cmd == "sync":
            await self.cmd_sync()
        elif cmd == "help":
            await self.cmd_help()
        else:
            print(f"Unknown command: {cmd}. Type 'help' for available commands.")

    # ---------- 具体命令实现 ----------

    async def cmd_list(self):
        cog_info = self._get_cog_files()
        if not cog_info:
            print("No cog files found.")
            return

        print("Cog status:")
        for name, info in sorted(cog_info.items()):
            loaded = self._is_loaded(name)
            disabled = info["disabled"]
            status = []
            status.append("loaded" if loaded else "unloaded")
            status.append("disabled" if disabled else "enabled")
            print(f"  {name}: {', '.join(status)}")

    async def cmd_reload(self, arg: Optional[str] = None):
        """
        重载：
        - 无参数或 'utils' → 重载所有 cog + utils
        - 指定 cog 名 → 仅重载该 cog（不重载 utils）
        """
        if arg == "utils":
            arg = None

        if arg is None:
            # 全量重载
            print("Reloading all cogs and utils...")
            cog_info = self._get_cog_files()
            enabled_cogs = [name for name, info in cog_info.items() if not info["disabled"]]

            # 卸载所有已加载的
            for name in enabled_cogs:
                ext = f"cogs.{name}"
                if self._is_loaded(name):
                    try:
                        await self.bot.unload_extension(ext)
                        print(f"Unloaded {ext}")
                    except Exception as e:
                        print(f"Failed unloading {ext}: {e}")

            # 清除所有 cog 缓存
            for name in enabled_cogs:
                self._clear_cog_cache(name)

            # 清除 utils 缓存
            self._clear_utils_cache()

            # 重新加载所有 cog
            for name in enabled_cogs:
                ext = f"cogs.{name}"
                try:
                    await self.bot.load_extension(ext)
                    print(f"Loaded {ext}")
                except Exception as e:
                    print(f"Failed loading {ext}: {e}")

            # 同步斜线命令
            try:
                synced = await self.bot.tree.sync()
                print(f"Re-synced {len(synced)} slash command(s)")
            except Exception as e:
                print(f"Slash sync after reload failed: {e}")

        else:
            # 单个 cog 重载
            cog_info = self._get_cog_files()
            if arg not in cog_info:
                print(f"Cog '{arg}' not found.")
                return
            if cog_info[arg]["disabled"]:
                print(f"Cog '{arg}' is disabled. Enable it first.")
                return

            ext = f"cogs.{arg}"
            if self._is_loaded(arg):
                try:
                    await self.bot.unload_extension(ext)
                    print(f"Unloaded {ext}")
                except Exception as e:
                    print(f"Failed unloading {ext}: {e}")

            self._clear_cog_cache(arg)

            try:
                await self.bot.load_extension(ext)
                print(f"Loaded {ext}")
            except Exception as e:
                print(f"Failed loading {ext}: {e}")

            try:
                synced = await self.bot.tree.sync()
                print(f"Re-synced {len(synced)} slash command(s)")
            except Exception as e:
                print(f"Slash sync after reload failed: {e}")

    async def cmd_stop(self, arg: Optional[str] = None):
        """无参数 → 停止整个 bot；有参数 → 卸载指定 cog"""
        if arg is None:
            print("Shutting down bot...")
            self.bot._shutdown = True
            if self.bot._terminal_task and not self.bot._terminal_task.done():
                self.bot._terminal_task.cancel()
                try:
                    await self.bot._terminal_task
                except asyncio.CancelledError:
                    pass
            await self.bot.close()
        else:
            cog_info = self._get_cog_files()
            if arg not in cog_info:
                print(f"Cog '{arg}' not found.")
                return
            if not self._is_loaded(arg):
                print(f"Cog '{arg}' is not loaded.")
                return
            ext = f"cogs.{arg}"
            try:
                await self.bot.unload_extension(ext)
                print(f"Unloaded {ext}")
            except Exception as e:
                print(f"Failed unloading {ext}: {e}")

    async def cmd_load(self, arg: Optional[str] = None):
        if arg is None:
            print("Usage: load <module>")
            return

        cog_info = self._get_cog_files()
        if arg not in cog_info:
            print(f"Cog '{arg}' not found.")
            return
        if cog_info[arg]["disabled"]:
            print(f"Cog '{arg}' is disabled. Use 'enable {arg}' first.")
            return
        if self._is_loaded(arg):
            print(f"Cog '{arg}' is already loaded.")
            return

        ext = f"cogs.{arg}"
        try:
            await self.bot.load_extension(ext)
            print(f"Loaded {ext}")
            synced = await self.bot.tree.sync()
            print(f"Synced {len(synced)} slash command(s)")
        except Exception as e:
            print(f"Failed loading {ext}: {e}")

    async def cmd_disable(self, arg: Optional[str] = None):
        if arg is None:
            print("Usage: disable <module>")
            return

        cog_info = self._get_cog_files()
        if arg not in cog_info:
            print(f"Cog '{arg}' not found.")
            return
        if cog_info[arg]["disabled"]:
            print(f"Cog '{arg}' is already disabled.")
            return

        # 先卸载（如果已加载）
        if self._is_loaded(arg):
            ext = f"cogs.{arg}"
            try:
                await self.bot.unload_extension(ext)
                print(f"Unloaded {ext}")
            except Exception as e:
                print(f"Failed unloading {ext}: {e}")
                return

        # 重命名文件
        old_path = cog_info[arg]["file"]
        new_path = old_path + ".disabled"
        try:
            os.rename(old_path, new_path)
            print(f"Disabled '{arg}' (renamed to {os.path.basename(new_path)})")
        except Exception as e:
            print(f"Failed to disable {arg}: {e}")

    async def cmd_enable(self, arg: Optional[str] = None):
        if arg is None:
            print("Usage: enable <module>")
            return

        cog_info = self._get_cog_files()
        if arg not in cog_info:
            print(f"Cog '{arg}' not found.")
            return
        if not cog_info[arg]["disabled"]:
            print(f"Cog '{arg}' is already enabled.")
            return

        old_path = cog_info[arg]["file"]
        if not old_path.endswith(".py.disabled"):
            print(f"Internal error: {old_path} does not end with .py.disabled")
            return
        new_path = old_path[:-12] + ".py"
        try:
            os.rename(old_path, new_path)
            print(f"Enabled '{arg}' (renamed to {os.path.basename(new_path)})")
        except Exception as e:
            print(f"Failed to enable {arg}: {e}")

    async def cmd_sync(self):
        try:
            synced = await self.bot.tree.sync()
            print(f"Synced {len(synced)} slash command(s)")
        except Exception as e:
            print(f"Slash sync failed: {e}")

    async def cmd_help(self):
        help_text = """
Available terminal commands:
  list                        - Show all cogs with status (loaded/unloaded, enabled/disabled)
  reload                      - Deep reload all cogs and utils (clears cache, __pycache__, GC)
  reload utils                - Same as reload (all cogs + utils)
  reload <module>             - Deep reload a specific cog only (utils NOT reloaded)
  stop                        - Gracefully shutdown the bot
  stop <module>               - Unload a specific cog
  load <module>               - Load a specific cog (must be enabled)
  disable <module>            - Unload and rename file to .py.disabled
  enable <module>             - Rename .py.disabled back to .py (does NOT load)
  sync                        - Manually sync slash commands
  help                        - Show this help
"""
        print(help_text)