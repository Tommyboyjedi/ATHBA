"""Legacy local resource-director compatibility loop.

This module predates the ATHBA versus Rack AI execution boundary. It remains in
source as quarantined compatibility code and is not part of the modern active
ATHBA control plane.
"""

import asyncio
import os
import threading
import time

import psutil
import requests
from dotenv import load_dotenv

from core.dataclasses.shared_state import SharedState
from core.datastore.repos.project_repo import ProjectRepo
from llm_service.enums.eagent import EAgent
from llm_service.enums.etier import ETier
from llm_service.model_registry import ModelRegistry

load_dotenv()


def _is_protected_model(model_registry: ModelRegistry, model_path: str) -> bool:
    if not model_path:
        return False
    pm_model = str(model_registry.get_model(EAgent.PM, ETier.STANDARD)).lower()
    architect_model = str(model_registry.get_model(EAgent.Architect, ETier.MEGA)).lower()
    path = model_path.lower()
    return path == pm_model or path == architect_model


def _start_watchdog(shared_state: SharedState, on_pressure) -> None:
    def watchdog():
        while True:
            mem = psutil.virtual_memory().percent
            cpu = psutil.cpu_percent(interval=None)
            shared_state.last_mem_usage = mem
            shared_state.last_cpu_usage = cpu
            if mem > shared_state.mem_threshold or cpu > shared_state.cpu_threshold:
                shared_state.pause_all = True
                print(f"[WATCHDOG] Pressure detected (mem={mem}%, cpu={cpu}%). Poking RD...")
                asyncio.run(on_pressure("System pressure exceeded thresholds"))
            time.sleep(0.5)

    threading.Thread(target=watchdog, daemon=True).start()


class RdAgent:
    def __init__(self):
        self.model_registry = ModelRegistry()
        self.shared_state = SharedState()
        self.project_repo = ProjectRepo()
        self.llm_server_url = os.getenv("LLM_SERVER_URL", "http://127.0.0.1:8011")
        self.model_idle_ttl_seconds = int(os.getenv("LLM_MODEL_TTL", "120"))
        self.failed_unloads = {}
        _start_watchdog(self.shared_state, self.poke)

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
        usage_report = {project.id: 50 for project in projects}
        for project in projects:
            quota = self.shared_state.project_quota.get_quota(project.priority)
            usage = usage_report.get(project.id, 0)
            if usage > quota:
                await self.log(f"[RD] Project {project.name} exceeded quota ({usage}% > {quota}%). Consider pausing.")

    async def _check_llm_server(self):
        try:
            response = requests.get(f"{self.llm_server_url}/status", timeout=5)
            response.raise_for_status()
            data = response.json()
            models = data if isinstance(data, list) else data.get("loaded_models", [])
            now = time.time()
            for model in models:
                model_path = model.get("path")
                if _is_protected_model(self.model_registry, model_path):
                    await self.log(f"Preserving protected model: {model_path}")
                    continue
                last_used = model.get("last_used")
                if last_used is None:
                    await self.log(f"Model {model_path} has no last_used timestamp, skipping.")
                    continue
                if now - last_used > self.model_idle_ttl_seconds:
                    await self.log(f"Evaluating model for unload: {model_path} last used {int(now - last_used)}s ago")
                    await self._unload_model(model_path)
        except Exception as error:
            await self.log(f"Failed to query LLM server: {error}")

    async def _enforce_model_priorities(self):
        try:
            response = requests.get(f"{self.llm_server_url}/status", timeout=5)
            response.raise_for_status()
            data = response.json()
            models = data if isinstance(data, list) else data.get("loaded_models", [])
            for model in models:
                model_path = model.get("model", "").lower()
                if _is_protected_model(self.model_registry, model_path):
                    await self.log(f"Preserving protected model: {model_path}")
                    continue
                await self._unload_model(model.get("path"))
        except Exception as error:
            await self.log(f"[RD] Error enforcing model priorities: {error}")

    async def _unload_model(self, model_path):
        cooldown = 30
        last_attempt = self.failed_unloads.get(model_path, 0)
        if time.time() - last_attempt < cooldown:
            await self.log(f"Skipping unload for {model_path}, cooldown active.")
            return
        try:
            response = requests.post(
                f"{self.llm_server_url}/unload",
                json={"model_path": model_path},
                timeout=5,
            )
            if response.status_code == 200:
                await self.log(f"[RD] Unloaded model: {model_path}")
                self.failed_unloads.pop(model_path, None)
            else:
                await self.log(f"[RD] Failed to unload model: {model_path} - {response.status_code}")
                self.failed_unloads[model_path] = time.time()
        except Exception as error:
            await self.log(f"[RD] Exception during model unload: {error}")

    async def log(self, message: str):
        print(f"[RD] {message}")


if __name__ == "__main__":
    agent = RdAgent()
    asyncio.run(agent.start())
