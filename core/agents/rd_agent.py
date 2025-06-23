# rd_agent.py
import os

import requests
from dotenv import load_dotenv
load_dotenv()


import asyncio
import threading
import time
import psutil

from core.dataclasses.shared_state import SharedState
from core.datastore.repos.project_repo import ProjectRepo
from llm_service.model_registry import ModelRegistry
from llm_service.enums.eagent import EAgent
from llm_service.enums.etier import ETier


class RdAgent:
    def __init__(self):
        self.model_registry = ModelRegistry()
        self.shared_state = SharedState()
        self.project_repo = ProjectRepo()
        self.llm_server_url = os.getenv("LLM_SERVER_URL", "http://127.0.0.1:8011")
        self.model_idle_ttl_seconds = int(os.getenv("LLM_MODEL_TTL", "120"))
        self._start_watchdog()
        self.failed_unloads = {}

    def _start_watchdog(self):
        def watchdog():
            while True:
                mem = psutil.virtual_memory().percent
                cpu = psutil.cpu_percent(interval=None)
                self.shared_state.last_mem_usage = mem
                self.shared_state.last_cpu_usage = cpu

                if mem > self.shared_state.mem_threshold or cpu > self.shared_state.cpu_threshold:
                    self.shared_state.pause_all = True
                    print(f"[WATCHDOG] Pressure detected (mem={mem}%, cpu={cpu}%). Poking RD...")
                    asyncio.run(self.poke("System pressure exceeded thresholds"))
                time.sleep(0.5)

        thread = threading.Thread(target=watchdog, daemon=True)
        thread.start()

    async def start(self):
        while True:
            await self.tick()
            await asyncio.sleep(1.0)

    async def tick(self):
        await self._check_system_pressure()
        await self._check_llm_server()
        await self._check_quota()

    async def poke(self, reason: str):
        await self.log(f"Poked due to: {reason}")
        await self.tick()

    async def _check_system_pressure(self):
        if self.shared_state.pause_all:
            await self.log("System pressure active: unloading non-essential models.")
            await self._enforce_model_priorities()

    async def _check_quota(self):
        projects = await self.project_repo.list_all()
        usage_report = await self._estimate_usage(projects)

        for project in projects:
            quota = self.shared_state.project_quota.get_quota(project.priority)
            usage = usage_report.get(project.id, 0)

            if usage > quota:
                await self.log(f"[RD] Project {project.name} exceeded quota ({usage}% > {quota}%). Consider pausing.")

    async def _estimate_usage(self, projects):
        return {project.id: 50 for project in projects}  # Dummy usage data

    async def _check_llm_server(self):
        try:
            response = requests.get(f"{self.llm_server_url}/status", timeout=5)
            response.raise_for_status()
            data = response.json()
            models = data if isinstance(data, list) else data.get("loaded_models", [])
            now = time.time()

            for model in models:
                model_path = model.get("path")
                if self._is_protected_model(model_path):
                    await self.log(f"Preserving protected model: {model_path}")
                    continue
                    continue
                last_used = model.get("last_used")
                if last_used is None:
                    await self.log(f"Model {model_path} has no last_used timestamp, skipping.")
                    continue
                if now - last_used > self.model_idle_ttl_seconds:
                    await self.log(f"Evaluating model for unload: {model_path} last used {int(now - last_used)}s ago")
                    await self._unload_model(model_path)


        except Exception as e:
            await self.log(f"Failed to query LLM server: {e}")

    async def _enforce_model_priorities(self):
        try:
            response = requests.get(f"{self.llm_server_url}/status", timeout=5)
            response.raise_for_status()
            data = response.json()
            models = data if isinstance(data, list) else data.get("loaded_models", [])

            for model in models:
                model_path = model.get("model", "").lower()
                if self._is_protected_model(model_path):
                    await self.log(f"Preserving protected model: {model_path}")
                    continue
                await self._unload_model(model.get("path"))

        except Exception as e:
            await self.log(f"[RD] Error enforcing model priorities: {e}")

    async def _unload_model(self, model_path):
        # In _unload_model
        cooldown = 30  # seconds
        last_attempt = self.failed_unloads.get(model_path, 0)
        if time.time() - last_attempt < cooldown:
            await self.log(f"Skipping unload for {model_path}, cooldown active.")
            return

        # Proceed to unload
        try:
            res = requests.post(f"{self.llm_server_url}/unload", json={"model_path": model_path}, timeout=5)
            if res.status_code == 200:
                await self.log(f"[RD] Unloaded model: {model_path}")
                self.failed_unloads.pop(model_path, None)
            else:
                await self.log(f"[RD] Failed to unload model: {model_path} — {res.status_code}")
                self.failed_unloads[model_path] = time.time()
        except Exception as e:
            await self.log(f"[RD] Exception during model unload: {e}")

    async def log(self, message: str):
        print(f"[RD] {message}")

    def _is_protected_model(self, model_path: str) -> bool:
        """Check if the given path matches any protected model paths."""

        if not model_path:
            return False

        pm_model = str(self.model_registry.get_model(EAgent.PM, ETier.STANDARD)).lower()
        architect_model = str(self.model_registry.get_model(EAgent.Architect, ETier.MEGA)).lower()

        path = model_path.lower()
        return path == pm_model or path == architect_model


if __name__ == "__main__":
    agent = RdAgent()
    asyncio.run(agent.start())