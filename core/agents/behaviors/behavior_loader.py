# core/agents/behaviours/behavior_loader.py

import importlib
import pkgutil
from typing import List
from core.agents.interfaces import AgentBehavior, IAgent


class BehaviorLoader:

    def load_for_agent(self, agent: IAgent) -> List:
        return self._load(f"core.agents.behaviors.{agent.name.lower()}")
    def _load(self, module_path: str) -> List:
        behaviors = []
        pkg = importlib.import_module(module_path)

        for _, module_name, _ in pkgutil.iter_modules(pkg.__path__):
            full_module = f"{module_path}.{module_name}"
            mod = importlib.import_module(full_module)

            for attr_name in dir(mod):
                obj = getattr(mod, attr_name)
                if isinstance(obj, type) and issubclass(obj, AgentBehavior) and obj is not AgentBehavior:
                    if module_name == "basic_reply_behavior":
                        basic_mod = obj()
                        continue
                    behaviors.append(obj())
        try:
            if basic_mod:
                behaviors.append(basic_mod)
        except NameError:
            pass
        return behaviors
