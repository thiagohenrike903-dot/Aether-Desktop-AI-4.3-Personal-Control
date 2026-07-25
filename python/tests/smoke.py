"""End-to-end smoke test for the orchestrator + executor.

Run with:
    cd python && python -m tests.smoke
"""
import asyncio
import json
import sys
from pathlib import Path

# Force UTF-8 stdout for Windows consoles.
try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    pass

# Make `python/` importable when run as a script.
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from jarvis.executor import run as run_action
from jarvis.orchestrator import dispatch


async def case(name: str, message: str, expected_type: str | None = None, *, skip: bool = False):
    print(f"  -> {name}")
    if skip:
        print(f"     (skipped)")
        return
    res = await dispatch(message)
    action = res.get("action")
    print(f"     winner: {res['winner']}")
    print(f"     action: {action}")
    if expected_type and (not action or action.get("type") != expected_type):
        print(f"     [WARN] expected {expected_type}")
    if action:
        result = await run_action(action)
        if isinstance(result, dict):
            keys = list(result.keys())[:4]
            preview = {k: result[k] for k in keys}
            print(f"     executed -> {preview}")


async def main():
    print("Aether — teste rápido de orquestração e execução")
    print("=" * 56)
    await case("open Discord",        "Aether, abra o Discord",                "open_app")
    await case("close Spotify",       "Aether, feche o Spotify",               "kill_app")
    await case("play playlist",       "Aether, toque minha playlist",          "open_app")
    await case("research query",      "Aether, pesquise inteligência artificial", None)
    await case("open downloads",      "Aether, abra minha pasta Downloads",    "open_path")
    await case("set volume",          "Aether, aumentar volume para 50",       "set_volume")
    await case("set brightness",      "Aether, brilho em 70",                  "set_brightness")
    await case("media next",          "Aether, próxima música",                "media_command")
    await case("open youtube (URL)",  "Aether, abra o YouTube",                "open_app", skip=True)
    await case("system shutdown",     "Aether, desligue o computador",         "system_action", skip=True)
    # New agents
    await case("organize downloads",  "Aether, organize minha pasta Downloads", "organize_files")
    await case("organize by type",    "Aether, organize Downloads por tipo",    "organize_files")
    await case("clean temp",          "Aether, limpe arquivos temporários",     "clean_temp_files")
    await case("list files",          "Aether, mostre os arquivos do Downloads","list_directory")
    # Vision agent
    await case("analyze screen",      "Aether, o que tem na minha tela",        "capture_and_analyze")
    print()
    print("All smoke tests complete.")


if __name__ == "__main__":
    asyncio.run(main())
