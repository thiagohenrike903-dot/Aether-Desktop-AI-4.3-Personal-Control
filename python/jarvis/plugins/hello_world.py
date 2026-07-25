PLUGIN_NAME = "Hello World"
PLUGIN_VERSION = "1.0.0"
PLUGIN_DESCRIPTION = "Um plugin de exemplo que demonstra o sistema de plugins do Aether."
PLUGIN_AUTHOR = "Aether"


async def handler(action: str, params: dict) -> dict:
    if action == "hello":
        name = params.get("name", "Mundo")
        return {"ok": True, "message": f"Olá, {name}!", "plugin": PLUGIN_NAME}
    elif action == "echo":
        return {"ok": True, "echo": params.get("text", ""), "plugin": PLUGIN_NAME}
    elif action == "info":
        return {
            "ok": True,
            "name": PLUGIN_NAME,
            "version": PLUGIN_VERSION,
            "description": PLUGIN_DESCRIPTION,
            "author": PLUGIN_AUTHOR,
        }
    return {"ok": False, "error": f"Ação desconhecida: {action}"}
