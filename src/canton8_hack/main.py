from typing import List, Dict, Any
import os

# Ensure the moved `canton8_agent` package is importable when running from
# the workspace (it lives under `hackathon-toolkit/canton8_agent`). Try a
# normal import first, and if that fails, add the sibling `hackathon-toolkit`
# folder to `sys.path` and retry.
try:
    from canton8_agent.ai_provider import MockProvider, GeminiProvider
except Exception:
    import sys
    from pathlib import Path

    repo_root = Path(__file__).resolve().parents[2]
    candidate = repo_root / "hackathon-toolkit"
    if str(candidate) not in sys.path:
        sys.path.insert(0, str(candidate))
    from canton8_agent.ai_provider import MockProvider, GeminiProvider


def greet(name: str = "world") -> str:
    return f"Hello, {name}! Welcome to canton8_hack."


def demo_provider_selection():
    offers: List[Dict[str, Any]] = [
        {"id": "o1", "price": 120, "info": {"vendor": "A"}},
        {"id": "o2", "price": 80, "info": {"vendor": "B"}},
        {"id": "o3", "price": 95, "info": {"vendor": "C"}},
    ]
    mandate = {"perPurchaseLimit": 100}
    context = {"owner": "demo"}

    provider_name = os.getenv("AI_PROVIDER", "mock").lower()
    if provider_name == "gemini":
        provider = GeminiProvider()
    else:
        provider = MockProvider()

    decision = provider.decide_offer(offers, mandate, context)
    print("Provider:", provider.__class__.__name__)
    print("Decision:", decision)


if __name__ == "__main__":
    print(greet())
    demo_provider_selection()
