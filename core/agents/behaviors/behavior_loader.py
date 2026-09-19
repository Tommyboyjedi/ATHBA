import importlib
import pkgutil
from typing import List

from core.agents.interfaces import IAgent


class BehaviorLoader:
    def load_for_agent(self, agent: IAgent) -> List:
        return self._load(f"core.agents.behaviors.{agent.name.lower()}")

    def _load(self, module_path: str) -> List:
        basic_behavior = None
        behaviors = []
        pkg = importlib.import_module(module_path)
        for _, module_name, _ in pkgutil.iter_modules(pkg.__path__):
            full_module = f"{module_path}.{module_name}"
            mod = importlib.import_module(full_module)
            for attr_name in dir(mod):
                obj = getattr(mod, attr_name)
                if not isinstance(obj, type):
                    continue
                if not attr_name.endswith("Behavior") or not hasattr(obj, "run"):
                    continue
                instance = obj()
                if module_name == "basic_reply_behavior":
                    basic_behavior = instance
                else:
                    behaviors.append(instance)
        if basic_behavior is not None:
            behaviors.append(basic_behavior)
        return behaviors
