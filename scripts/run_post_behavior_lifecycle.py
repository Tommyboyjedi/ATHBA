"""Continue a completed behavioral feature through the source-controlled PR30 lifecycle."""
from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path

from core.development.post_behavior_composition import PostBehaviorCompositionFactory, PostBehaviorCompositionRequest
from core.development.post_behavior_domain import PostBehaviorStatus
from core.development.post_behavior_store import PostBehaviorStateCodec
from core.execution.provider_reasoning_gateway import ProviderReasoningGateway
from core.llm.contracts.provider import ProviderRetryPolicy
from core.llm.providers.openai_provider import OpenAIProvider


async def execute(arguments) -> int:
    provider = OpenAIProvider(policy=ProviderRetryPolicy(
        timeout=arguments.reasoning_timeout, max_retries=0, backoff_factor=1.0))
    gateway = ProviderReasoningGateway(provider, arguments.reasoning_model)
    lifecycle = PostBehaviorCompositionFactory().build(PostBehaviorCompositionRequest(
        arguments.state_root, arguments.project_id, gateway))
    state = await lifecycle.run(arguments.project_id)
    print(json.dumps(PostBehaviorStateCodec.encode(state), sort_keys=True, indent=2))
    return 0 if state.status == PostBehaviorStatus.POST_BEHAVIOR_COMPLETE else 2


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--state-root", type=Path, required=True)
    parser.add_argument("--project-id", required=True)
    parser.add_argument("--reasoning-model", required=True,
                        help="Operator-configured local reasoning identity; never a workspace worker selector.")
    parser.add_argument("--reasoning-timeout", type=float, default=300.0)
    arguments = parser.parse_args()
    try:
        return asyncio.run(execute(arguments))
    except (ValueError, OSError, RuntimeError) as error:
        print(json.dumps({"status": "blocked", "error": str(error)}))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
