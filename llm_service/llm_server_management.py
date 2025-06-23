import asyncio
import threading
import time

import psutil

from llm_service.llm_server_state import (
    mem_threshold, cpu_threshold, check_interval, model_idle_ttl,
    loaded_models, model_locks, model_last_used
)

from llm_service.model_registry import ModelRegistry, FLOW_JUDGE_PATH
from llm_service.enums.eagent import EAgent
from llm_service.enums.etier import ETier


class LlmServerManagement:
    def __init__(self):
        self._last_status_check = 0
        self.failed_unloads = {}
        self._start_watchdog()
        self.registry = ModelRegistry()
        self.protected_paths = {
            str(self.registry.get_model(EAgent.PM, ETier.STANDARD)).lower(),
            str(FLOW_JUDGE_PATH).lower()
        }
    def _start_watchdog(self):
        def monitor():
            while True:
                mem = psutil.virtual_memory().percent
                cpu = psutil.cpu_percent(interval=None)
                if mem > mem_threshold or cpu > cpu_threshold:
                    self.log(f"[LLM_MANAGE] Pressure detected (mem={mem:.1f}%, cpu={cpu:.1f}%). Enforcing priorities.")
                    asyncio.run(self._enforce_model_priorities())
                time.sleep(2)
        threading.Thread(target=monitor, daemon=True).start()

    async def start(self):
        while True:
            await self.tick()
            await asyncio.sleep(1)

    async def tick(self):
        now = time.time()
        if now - self._last_status_check < check_interval:
            return
        self._last_status_check = now
        await self._check_model_ttl()

    async def _check_model_ttl(self):
        try:
            now = time.time()
            for path, last_used in model_last_used.items():
                if self._is_protected_model(path):
                    continue
                last_used = model_last_used[path]
                if now - last_used > model_idle_ttl:
                    self.log(f"[LLM_MANAGE] TTL expired: {path} idle for {int(now - last_used)}s")
                    await self._unload_model(path)
        except Exception as e:
            self.log(f"[LLM_MANAGE] Failed TTL check: {e}")

    async def _enforce_model_priorities(self):
        try:
            for path in list(loaded_models.keys()):
                if self._is_protected_model(path):
                    continue
                await self._unload_model(path)
        except Exception as e:
            self.log(f"[LLM_MANAGE] Priority enforcement failed: {e}")

    async def _unload_model(self, model_path: str):
        cooldown = 30
        now = time.time()
        last_attempt = self.failed_unloads.get(model_path, 0)
        if now - last_attempt < cooldown:
            self.log(f"[LLM_MANAGE] Skipping unload (cooldown): {model_path}")
            return
        try:
            if model_path in loaded_models:
                del loaded_models[model_path]
                del model_locks[model_path]
                del model_last_used[model_path]
                self.log(f"[LLM_MANAGE] Unloaded: {model_path}")
                self.failed_unloads.pop(model_path, None)
            else:
                self.log(f"[LLM_MANAGE] Model not found: {model_path}")
        except Exception as e:
            self.log(f"[LLM_MANAGE] Exception unloading {model_path}: {e}")
            self.failed_unloads[model_path] = now

    def _is_protected_model(self, path: str) -> bool:
        if not path:
            return False
        return path.lower() in self.protected_paths
    def log(self,msg: str):
        print(f"[LLM] {msg}")