"""Quick test that all provider factory configs work."""
import importlib.util
import os
import subprocess
import sys
import json
import unittest


_HTTPX_AVAILABLE = (
    importlib.util.find_spec("httpx") is not None
    and not getattr(sys.modules.get("httpx"), "__aether_test_stub__", False)
)


PROVIDER_CASES = [
    ("gemini", {"LLM_PROVIDER": "gemini", "GEMINI_API_KEY": "test-key"}),
    ("qwen (ollama)", {"LLM_PROVIDER": "qwen", "LLM_MODEL": "qwen2.5-vl"}),
    ("qwen_api", {"LLM_PROVIDER": "qwen_api", "LLM_API_KEY": "sk-test"}),
    ("openai", {"LLM_PROVIDER": "openai", "LLM_API_KEY": "sk-test"}),
    ("ollama", {"LLM_PROVIDER": "ollama"}),
    ("glm", {"LLM_PROVIDER": "glm", "LLM_API_KEY": "test-key"}),
]


def check_provider(name: str, env: dict[str, str]) -> tuple[bool, str]:
    env_json = json.dumps(env)
    code = f"""
import os, json
env = json.loads({env_json!r})
for k, v in env.items():
    os.environ[k] = v
from jarvis.llm_providers import get_provider
import jarvis.llm_providers
jarvis.llm_providers._PROVIDER = None
p = get_provider()
if p is None:
    print("FAIL: provider is None")
else:
    print(f"OK: {{type(p).__name__}} model={{p.model}}")
"""
    r = subprocess.run(
        [sys.executable, "-c", code],
        capture_output=True, text=True,
        cwd=os.path.join(os.path.dirname(__file__), ".."),
    )
    out = (r.stdout or "").strip().split("\n")[-1]
    return "OK" in out, out


@unittest.skipUnless(_HTTPX_AVAILABLE, "httpx not installed")
class ProviderFactoryTests(unittest.TestCase):
    def test_provider_factories(self) -> None:
        for name, env in PROVIDER_CASES:
            with self.subTest(provider=name):
                ok, output = check_provider(name, env)
                self.assertTrue(ok, output or "provider subprocess failed")


def main():
    all_ok = True
    for name, env in PROVIDER_CASES:
        ok, out = check_provider(name, env)
        status = "PASS" if ok else "FAIL"
        print(f"  [{status}] {name}: {out}")
        if not ok:
            all_ok = False
    print()
    print("ALL OK" if all_ok else "SOME FAILED")
    return 0 if all_ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
