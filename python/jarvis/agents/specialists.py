"""Specialist agents — each one wraps a real capability.

The point of these classes is to keep the *intent -> action* mapping in one
place. The orchestrator scores them; the highest-scoring one is asked to
produce a structured action, which the executor then runs.
"""
from __future__ import annotations

import json
import re
from typing import Any

from .base import Agent, AgentContext, AgentResult

# A small map of "what the user said" -> {action} that the executor runs.
# Each entry has to be unambiguous so we don't accidentally open a game
# when the user asked to open a "code" file.
KNOWN_APP_TARGETS = {
    "discord": "discord", "vscode": "vscode", "vs_code": "vscode", "code": "vscode",
    "spotify": "spotify", "steam": "steam", "photoshop": "photoshop",
    "figma": "figma", "notion": "notion", "chrome": "chrome", "edge": "edge",
    "firefox": "firefox", "terminal": "terminal", "powershell": "powershell",
    "cmd": "cmd", "explorer": "explorer", "calculator": "calculator",
    "notepad": "notepad", "settings": "settings", "task_manager": "task_manager",
    "word": "winword", "excel": "excel", "outlook": "outlook",
    "teams": "teams", "zoom": "zoom", "slack": "slack",
    "telegram": "telegram", "whatsapp": "whatsapp",
    "obsidian": "obsidian", "notepad++": "notepad++", "npp": "notepad++",
    "pycharm": "pycharm", "intellij": "idea", "android studio": "studio",
    "git bash": "git bash", "cmder": "cmder",
}

URL_TARGETS = {
    "youtube": "https://www.youtube.com",
    "github": "https://github.com",
    "google": "https://www.google.com",
    "chatgpt": "https://chat.openai.com",
    "figma": "https://www.figma.com",
    "notion": "https://www.notion.so",
    "drive": "https://drive.google.com",
    "google_drive": "https://drive.google.com",
    "instagram": "https://www.instagram.com",
    "linkedin": "https://www.linkedin.com",
    "gmail": "https://mail.google.com",
    "twitter": "https://twitter.com", "x": "https://x.com",
    "facebook": "https://facebook.com",
    "reddit": "https://reddit.com",
    "stackoverflow": "https://stackoverflow.com",
    "medium": "https://medium.com",
    "trello": "https://trello.com", "gitlab": "https://gitlab.com",
    "netflix": "https://netflix.com", "prime": "https://primevideo.com",
    "twitch": "https://twitch.tv", "deepl": "https://deepl.com",
}

LOCALE_OPEN_VERBS = ("abrir", "abre", "abra", "abram", "open", "launch", "execute", "iniciar", "inicie", "rode", "roda", "rode o", "abre o", "abrir o", "abra o", "abra a")
LOCALE_CLOSE_VERBS = ("fechar", "fecha", "feche", "fechem", "close", "quit", "encerre", "encerra", "encerrem")
LOCALE_SEARCH_VERBS = ("pesquisar", "pesquise", "procure", "buscar", "busque", "search", "pesquisa")
LOCALE_PLAY_VERBS = ("toque", "toca", "tocar", "play", "reproduzir", "reproduza")
LOCALE_SHUTDOWN_VERBS = ("desligar", "desligue", "shutdown", "turn off", "desliga")
LOCALE_RESTART_VERBS = ("reiniciar", "reinicie", "restart", "reboot")
LOCALE_LOCK_VERBS = ("bloquear", "bloqueie", "lock", "trancar")
LOCATE_VOLUME = ("volume", "som", "audio", "áudio")

# Organize verbs
LOCALE_ORGANIZE_VERBS = (
    "organizar", "organize", "arrumar", "arrume", "categorizar",
    "categorize", "separar", "separe", "limpar", "limpe",
    "ordenar", "ordene",
)


def _contains_any(text: str, words: tuple[str, ...]) -> bool:
    for word in words:
        phrase = re.escape(word).replace(r"\ ", r"\s+")
        if re.search(rf"(?<!\w){phrase}(?!\w)", text, flags=re.IGNORECASE):
            return True
    return False


def _extract_app_name(text: str) -> str | None:
    tokens = re.findall(r"[a-zA-Z_]+", text.lower())
    for t in tokens:
        if t in KNOWN_APP_TARGETS:
            return KNOWN_APP_TARGETS[t]
    return None


def _extract_app_name_v2(text: str) -> str | None:
    """Extended app extraction with multi-word support."""
    low = text.lower()
    # Try multi-word first
    for key in sorted(KNOWN_APP_TARGETS.keys(), key=len, reverse=True):
        if key in low:
            return KNOWN_APP_TARGETS[key]
    return _extract_app_name(text)


def _extract_url_target(text: str) -> str | None:
    low = text.lower()
    for key, url in URL_TARGETS.items():
        if key in low:
            return url
    return None


def _extract_path(text: str) -> str | None:
    paths = _extract_paths(text)
    return paths[0] if paths else None


def _extract_paths(text: str) -> list[str]:
    """Extract explicit local paths, including quoted paths with spaces."""
    candidates: list[str] = []
    for quoted in re.findall(r"""["']([^"'[\r\n]+)["']""", text):
        value = quoted.strip()
        if re.match(r"^(?:[a-zA-Z]:[\\/]|/|~/)", value):
            candidates.append(value)
    candidates.extend(
        re.findall(r"(?:[a-zA-Z]:[\\\\/][^\s,;]+|~/[^\s,;]+|/[^\s,;]+)", text)
    )
    return list(dict.fromkeys(candidates))


def _extract_number(text: str) -> int | None:
    m = re.search(r"(\d{1,3})\s*%?", text)
    return int(m.group(1)) if m else None


def _extract_search_query(text: str) -> str | None:
    low = text.lower()
    m = re.search(
        r"(?:pesquis[ae]|buscar|busque|search|pesquisa|procure|procurar)\s+(.+?)$",
        low,
    )
    return m.group(1).strip() if m else None


def _system_intent(text: str) -> str | None:
    low = text.lower()
    if _contains_any(low, LOCALE_SHUTDOWN_VERBS):
        return "shutdown"
    if _contains_any(low, LOCALE_RESTART_VERBS):
        return "restart"
    if _contains_any(low, LOCALE_LOCK_VERBS):
        return "lock"
    if "suspend" in low or "dormir" in low or "hibernar" in low:
        return "suspend"
    if "logout" in low or "sair" in low or "log off" in low:
        return "log_out"
    return None


# --------------------------------------------------------------------------- #
# Specialists
# --------------------------------------------------------------------------- #

async def automation_handler(ctx: AgentContext) -> AgentResult:
    """Open / close apps, files, URLs, manage the OS."""
    msg = ctx.user_message
    low = msg.lower()
    action: dict[str, Any] | None = None
    reply = "Executando ação de automação."

    sys_intent = _system_intent(msg)
    if sys_intent:
        action = {"type": "system_action", "target": sys_intent}
        reply = f"Executando comando: {sys_intent}."
    elif _contains_any(low, LOCALE_OPEN_VERBS):
        target = _extract_url_target(msg) or _extract_app_name_v2(msg)
        path = _extract_path(msg)
        if target in URL_TARGETS.values():
            action = {"type": "open_url", "target": target}
            reply = f"Abrindo {target}."
        elif target:
            action = {"type": "open_app", "target": target}
            reply = f"Abrindo {target}."
        elif path:
            action = {"type": "open_path", "target": path}
            reply = f"Abrindo {path}."
        else:
            if "downloads" in low or "download" in low:
                action = {"type": "open_path", "target": "shell:Downloads"}
            elif "desktop" in low or "área de trabalho" in low:
                action = {"type": "open_path", "target": "shell:Desktop"}
            elif "documentos" in low or "documents" in low or "documento" in low:
                action = {"type": "open_path", "target": "shell:Documents"}
            elif "imagens" in low or "pictures" in low or "fotos" in low:
                action = {"type": "open_path", "target": "shell:Pictures"}
            elif "música" in low or "music" in low or "musica" in low:
                action = {"type": "open_path", "target": "shell:Music"}
            elif "vídeos" in low or "videos" in low or "videos" in low:
                action = {"type": "open_path", "target": "shell:Videos"}
    elif _contains_any(low, LOCALE_CLOSE_VERBS):
        target = _extract_app_name_v2(msg)
        if target:
            action = {"type": "kill_app", "target": target}
            reply = f"Fechando {target}."
    elif _contains_any(low, LOCATE_VOLUME) or "som" in low:
        num = _extract_number(msg)
        if num is not None:
            action = {"type": "set_volume", "target": num}
        elif "aumentar" in low or "aumenta" in low or "increase" in low or "mais alto" in low:
            action = {"type": "set_volume_delta", "target": 10}
        elif "abaixar" in low or "diminuir" in low or "decrease" in low or "mais baixo" in low:
            action = {"type": "set_volume_delta", "target": -10}
        elif "mudo" in low or "mutado" in low or "mute" in low:
            action = {"type": "set_volume", "target": 0}
        elif "máximo" in low or "maximo" in low or "max" in low or "full" in low:
            action = {"type": "set_volume", "target": 100}
    elif _contains_any(low, LOCALE_PLAY_VERBS):
        action = {"type": "open_app", "target": "spotify"}
        reply = "Abrindo Spotify."
    elif "brilho" in low or "brightness" in low:
        num = _extract_number(msg)
        if num is not None:
            action = {"type": "set_brightness", "target": num}
    elif "próxima" in low or "proxima" in low or "next" in low or "pular" in low:
        action = {"type": "media_command", "target": "next"}
    elif "anterior" in low or "previous" in low or "prev" in low or "voltar" in low:
        action = {"type": "media_command", "target": "prev"}
    elif "pausar" in low or "pause" in low or "pausa" in low:
        action = {"type": "media_command", "target": "play_pause"}
    elif _contains_any(low, LOCALE_SEARCH_VERBS):
        query = _extract_search_query(msg)
        if query:
            action = {"type": "search_web", "target": query}
            reply = f"Pesquisando por \"{query}\"."

    return AgentResult(
        agent_id="automation",
        agent_name="Automation",
        reply=reply,
        action=action,
        confidence=0.85 if action else 0.3,
    )


async def files_handler(ctx: AgentContext) -> AgentResult:
    """Organize files, manage downloads, clean temp files."""
    msg = ctx.user_message
    low = msg.lower()
    action: dict[str, Any] | None = None
    reply = "Processando arquivos."
    paths = _extract_paths(msg)

    if "pdf" in low and paths and _contains_any(
        low,
        ("ler", "leia", "extrair", "extraia", "resumir", "resuma", "analisar", "analise"),
    ):
        action = {"type": "pdf_extract_text", "target": paths[0]}
        reply = f"Extraindo o texto do PDF {paths[0]}."

    elif "backup" in low or "cópia de segurança" in low:
        from ..workspace import get_root
        root = get_root()
        if _contains_any(low, ("listar", "liste", "mostrar", "mostre", "ver backups")):
            action = {"type": "backup_list"}
            reply = "Consultando os backups disponíveis."
        elif _contains_any(low, ("criar", "crie", "fazer", "faça", "gerar", "gere")):
            target = paths[0] if paths else (str(root) if root else None)
            if target:
                action = {"type": "backup_create", "target": target}
                reply = f"Criando um backup seguro de {target}."
            else:
                reply = "Selecione um workspace ou informe a pasta que deve receber o backup."
        else:
            reply = "Posso criar ou listar backups. Informe a pasta ou selecione um workspace."

    # Organize Downloads
    elif _contains_any(low, LOCALE_ORGANIZE_VERBS):
        # Determine which folder
        folder = None
        if "download" in low:
            folder = "~/Downloads"
        elif "desktop" in low or "área de trabalho" in low:
            folder = "~/Desktop"
        elif "documento" in low:
            folder = "~/Documents"
        else:
            folder = "~/Downloads"  # default to Downloads

        by_type = "tipo" in low or "type" in low or "categoria" in low or "categor" in low
        by_date = "data" in low or "date" in low
        dry_run = "simular" in low or "dry" in low or "preview" in low or "prévia" in low

        if "limpar" in low or "clean" in low or "temp" in low:
            action = {
                "type": "clean_temp_files",
                "target": folder,
                "days_old": 30,
                "dry_run": dry_run,
            }
            reply = f"{'Simulando limpeza' if dry_run else 'Limpando'} de arquivos temporários em {folder}."
        else:
            action = {
                "type": "organize_files",
                "target": folder,
                "by_type": not by_date,  # default to type
                "by_date": by_date,
                "dry_run": dry_run,
            }
            reply = f"{'Simulando organização' if dry_run else 'Organizando'} arquivos em {folder}{' por tipo' if not by_date else ' por data'}."

    # Copy / move / delete files
    elif _contains_any(low, ("copiar", "copie", "copia", "copy")):
        if len(paths) >= 2:
            action = {
                "type": "file_operation",
                "operation": "copy",
                "source": paths[0],
                "destination": paths[1],
            }
            reply = f"Preparando a cópia de {paths[0]} para {paths[1]}."
        else:
            reply = "Informe os caminhos de origem e destino para copiar o arquivo."
    elif _contains_any(low, ("mover", "mova", "move")):
        if len(paths) >= 2:
            action = {
                "type": "file_operation",
                "operation": "move",
                "source": paths[0],
                "destination": paths[1],
            }
            reply = f"Preparando a movimentação de {paths[0]} para {paths[1]}."
        else:
            reply = "Informe os caminhos de origem e destino para mover o arquivo."
    elif _contains_any(
        low,
        ("deletar", "delete", "excluir", "exclua", "apagar", "apague", "remover", "remova"),
    ):
        src = _extract_path(msg)
        if src:
            action = {
                "type": "file_operation",
                "operation": "delete",
                "source": src,
                "confirm_required": True,
            }
            reply = f"Preparando exclusão de {src}. Preciso de confirmação."

    # List files in a folder
    elif _contains_any(low, ("listar", "liste", "mostre", "mostrar")):
        folder = paths[0] if paths else None
        if "download" in low:
            folder = "~/Downloads"
        elif "desktop" in low:
            folder = "~/Desktop"
        elif "documento" in low:
            folder = "~/Documents"
        if folder:
            action = {"type": "list_directory", "target": folder}
            reply = f"Listando arquivos em {folder}."

    return AgentResult(
        agent_id="files",
        agent_name="Files",
        reply=reply,
        action=action,
        confidence=0.85 if action else 0.3,
    )


async def research_handler(ctx: AgentContext) -> AgentResult:
    from ..web_search import search_and_summarize
    try:
        results = await search_and_summarize(
            ctx.user_message,
            conversation_id=str(
                ctx.metadata.get("conversation_id") or ""
            ).strip() or None,
        )
        if results.get("results"):
            snippets = "\n".join(
                f"- {r['title']}: {r['snippet'][:200]}"
                for r in results["results"][:5]
            )
            reply = f"Resultados da pesquisa:\n{snippets}"
        else:
            reply = "Não encontrei resultados para sua pesquisa."
        return AgentResult(
            agent_id="research",
            agent_name="Research",
            reply=reply,
            confidence=0.85 if results.get("results") else 0.4,
        )
    except Exception as exc:
        return AgentResult(
            agent_id="research",
            agent_name="Research",
            reply=f"Não foi possível pesquisar: {exc}",
            confidence=0.3,
        )


async def programming_handler(ctx: AgentContext) -> AgentResult:
    from ..workspace import get_root
    root = get_root()
    if root:
        low = ctx.user_message.lower()
        action: dict[str, Any] | None = None
        reply = (
            f"O workspace {root.name} está pronto. Posso analisar, planejar e "
            "propor alterações sem abrir outro aplicativo."
        )
        if "git status" in low or "status do git" in low:
            action = {"type": "git_status", "target": str(root)}
            reply = f"Consultando o status Git de {root.name}."
        elif "git log" in low or "histórico do git" in low or "historico do git" in low:
            action = {"type": "git_log", "target": str(root)}
            reply = f"Consultando o histórico Git de {root.name}."
        elif "git diff" in low or "diferenças do git" in low or "diferencas do git" in low:
            action = {"type": "git_diff", "target": str(root)}
            reply = f"Consultando as alterações Git de {root.name}."
        elif "branch" in low and _contains_any(
            low,
            ("listar", "liste", "mostrar", "mostre"),
        ):
            action = {"type": "git_branch", "target": str(root)}
            reply = f"Listando as branches de {root.name}."
        return AgentResult(
            agent_id="programming",
            agent_name="Programming",
            reply=reply,
            confidence=0.8 if action else 0.65,
            action=action,
        )
    return AgentResult(
        agent_id="programming",
        agent_name="Programming",
        reply="Selecione um workspace no Studio primeiro.",
        confidence=0.4,
    )


async def designer_handler(ctx: AgentContext) -> AgentResult:
    return AgentResult(
        agent_id="designer",
        agent_name="Designer",
        reply=(
            "Posso ajudar a definir hierarquia, layout, cores, componentes e "
            "fluxos de interface. Diga qual tela ou experiência deseja criar."
        ),
        confidence=0.5,
    )


async def marketing_handler(ctx: AgentContext) -> AgentResult:
    return AgentResult(
        agent_id="marketing",
        agent_name="Marketing",
        reply="Ativando heurísticas de marketing.",
        confidence=0.45,
    )


async def seo_handler(ctx: AgentContext) -> AgentResult:
    return AgentResult(
        agent_id="seo",
        agent_name="SEO",
        reply="Rodando análise de SEO.",
        confidence=0.45,
    )


async def content_handler(ctx: AgentContext) -> AgentResult:
    return AgentResult(
        agent_id="content",
        agent_name="Content",
        reply="Preparando rascunho de conteúdo.",
        confidence=0.45,
    )


async def commercial_handler(ctx: AgentContext) -> AgentResult:
    return AgentResult(
        agent_id="commercial",
        agent_name="Commercial",
        reply="Pipeline comercial engajado.",
        confidence=0.4,
    )


async def financial_handler(ctx: AgentContext) -> AgentResult:
    return AgentResult(
        agent_id="financial",
        agent_name="Financial",
        reply="Modelo financeiro ativado.",
        confidence=0.4,
    )


async def agenda_handler(ctx: AgentContext) -> AgentResult:
    msg_low = ctx.user_message.lower()
    if "que dia" in msg_low or "que horas" in msg_low or "data" in msg_low:
        from datetime import datetime
        now = datetime.now()
        return AgentResult(
            agent_id="agenda",
            agent_name="Agenda",
            reply=f"Hoje é {now.strftime('%A, %d de %B de %Y')}. São {now.strftime('%H:%M')}.",
            confidence=0.9,
        )
    if (
        "clima" in msg_low
        or "previsão do tempo" in msg_low
        or "previsao do tempo" in msg_low
        or "tempo em " in msg_low
    ):
        city_match = re.search(
            r"(?:clima|previs[aã]o do tempo|tempo)\s+(?:em|de|para)\s+(.+?)[?.!]*$",
            ctx.user_message,
            re.IGNORECASE,
        )
        city = city_match.group(1).strip()[:120] if city_match else ""
        forecast = "previs" in msg_low or "próxim" in msg_low or "proxim" in msg_low
        return AgentResult(
            agent_id="agenda",
            agent_name="Agenda",
            reply=(
                f"Consultando {'a previsão' if forecast else 'o clima atual'}"
                f"{f' de {city}' if city else ''}."
            ),
            action={
                "type": "weather_forecast" if forecast else "weather",
                "city": city,
            },
            confidence=0.88,
        )
    if _contains_any(
        msg_low,
        ("agenda", "calendário", "calendario", "compromissos", "eventos"),
    ) and _contains_any(
        msg_low,
        ("listar", "liste", "mostrar", "mostre", "ver", "quais"),
    ):
        return AgentResult(
            agent_id="agenda",
            agent_name="Agenda",
            reply="Consultando os próximos eventos do calendário.",
            action={"type": "calendar_list", "max": 10},
            confidence=0.85,
        )
    return AgentResult(
        agent_id="agenda",
        agent_name="Agenda",
        reply="Posso consultar seus próximos eventos quando o Google Calendar estiver conectado.",
        confidence=0.4,
    )


async def navigation_handler(ctx: AgentContext) -> AgentResult:
    """The 'navigation' agent routes to web URLs / internal browser tabs."""
    url = _extract_url_target(ctx.user_message)
    if url:
        return AgentResult(
            agent_id="navigation",
            agent_name="Navigation",
            reply=f"Roteando navegação para {url}.",
            action={"type": "open_url", "target": url},
            confidence=0.8,
        )
    return AgentResult(
        agent_id="navigation",
        agent_name="Navigation",
        reply="Aguardando destino de navegação.",
        confidence=0.2,
    )


async def system_handler(ctx: AgentContext) -> AgentResult:
    """Pass-through for system-level commands."""
    low = ctx.user_message.lower()
    if _contains_any(
        low,
        (
            "uso do sistema",
            "uso do meu sistema",
            "cpu",
            "memória ram",
            "processos em execução",
            "estado do sistema",
            "diagnóstico do sistema",
            "fora do normal",
        ),
    ):
        return AgentResult(
            agent_id="system",
            agent_name="System",
            reply="Consultando CPU, memória e processos do computador.",
            action={"type": "system_snapshot"},
            confidence=0.9,
        )
    intent = _system_intent(ctx.user_message)
    if intent:
        return AgentResult(
            agent_id="system",
            agent_name="System",
            reply=f"Autorizando comando: {intent}.",
            action={"type": "system_action", "target": intent},
            confidence=0.9,
        )
    return AgentResult(
        agent_id="system",
        agent_name="System",
        reply="Aguardando comando de sistema.",
        confidence=0.2,
    )


async def security_handler(ctx: AgentContext) -> AgentResult:
    low = ctx.user_message.lower()
    path = _extract_path(ctx.user_message)
    action: dict[str, Any] | None = None
    reply = "Posso revisar riscos, criptografar arquivos e explicar as proteções do Aether."
    if path and _contains_any(low, ("criptografar", "criptografe", "encrypt")):
        action = {"type": "crypto_encrypt", "target": path}
        reply = f"Preparando a criptografia de {path}. A operação exigirá confirmação."
    elif path and _contains_any(low, ("descriptografar", "descriptografe", "decrypt")):
        action = {"type": "crypto_decrypt", "target": path}
        reply = f"Preparando a descriptografia de {path}. A operação exigirá confirmação."
    return AgentResult(
        agent_id="security",
        agent_name="Security",
        reply=reply,
        action=action,
        confidence=0.85 if action else 0.4,
    )


async def communication_handler(ctx: AgentContext) -> AgentResult:
    low = ctx.user_message.lower()
    if _contains_any(
        low,
        ("listar", "liste", "mostrar", "mostre", "caixa de entrada", "inbox"),
    ):
        return AgentResult(
            agent_id="communication",
            agent_name="Communication",
            reply="Consultando as mensagens recentes da sua conta conectada.",
            action={"type": "email_list", "max": 10},
            confidence=0.84,
        )
    search_match = re.search(
        r"(?:buscar|busque|pesquisar|pesquise|procurar|procure).+?(?:sobre|por|de)\s+(.+)$",
        ctx.user_message,
        re.IGNORECASE,
    )
    if search_match:
        return AgentResult(
            agent_id="communication",
            agent_name="Communication",
            reply="Pesquisando mensagens na conta conectada.",
            action={
                "type": "email_search",
                "query": search_match.group(1).strip()[:500],
                "max": 10,
            },
            confidence=0.82,
        )
    return AgentResult(
        agent_id="communication",
        agent_name="Communication",
        reply=(
            "Posso listar ou pesquisar e-mails. O envio exige destinatário, "
            "assunto, conteúdo e confirmação explícita."
        ),
        confidence=0.4,
    )


async def database_handler(ctx: AgentContext) -> AgentResult:
    return AgentResult(
        agent_id="database",
        agent_name="Database",
        reply="Consultando banco de dados.",
        confidence=0.35,
    )


async def memory_handler(ctx: AgentContext) -> AgentResult:
    return AgentResult(
        agent_id="memory",
        agent_name="Memory",
        reply="Atualizando memória de longo prazo.",
        confidence=0.35,
    )


async def vision_handler(ctx: AgentContext) -> AgentResult:
    """Analyze images / screen / camera using VLM."""
    msg = ctx.user_message.lower()
    action: dict[str, Any] | None = None
    reply = "Análise visual ativada."

    if _contains_any(msg, ("tela", "screen", "print", "captura", "capturar")):
        action = {"type": "capture_and_analyze", "prompt": ctx.user_message}
        reply = "Capturando e analisando a tela."
    elif _contains_any(msg, ("câmera", "camera", "cam", "webcam")):
        action = {"type": "capture_and_analyze", "source": "camera", "prompt": ctx.user_message}
        reply = "Ativando câmera para análise."
    elif _contains_any(msg, ("imagem", "image", "foto", "arquivo")):
        reply = "Anexe a imagem à conversa para que eu possa analisá-la."

    return AgentResult(
        agent_id="vision",
        agent_name="Vision",
        reply=reply,
        action=action,
        confidence=0.75 if action else 0.3,
    )


def build_specialist_agents() -> list[Agent]:
    return [
        Agent("automation", "Automation", "Computer & app control",
              keywords=["abrir", "abre", "abra", "abrir o", "abrir a", "open", "launch", "kill",
                        "fechar", "fecha", "feche", "close", "quit", "encerra",
                        "desligar", "desligue", "reiniciar", "reinicie", "bloquear", "bloqueie",
                        "volume", "brilho", "brightness", "play", "pausar", "pause",
                        "spotify", "discord", "vscode", "vs_code", "chrome", "edge", "firefox",
                        "photoshop", "figma", "notion", "terminal", "powershell", "cmd",
                        "calculadora", "explorer", "settings", "task_manager"],
              domains=["automation", "os", "system", "control"],
              handler=automation_handler),
        Agent("files", "Files", "File organization & management",
              keywords=["organizar", "organize", "arrumar", "arrume", "categorizar",
                        "separar", "separe", "limpar", "limpe", "download",
                        "downloads", "arquivo", "arquivos", "file", "files",
                        "copiar", "copie", "copy", "mover", "mova", "move",
                        "deletar", "delete", "excluir", "exclua", "apagar",
                        "apague", "remover", "remova", "temp", "temporário",
                        "listar", "liste", "mostrar", "mostre", "pdf", "backup",
                        "cópia de segurança"],
              domains=["files", "organization", "storage"],
              handler=files_handler),
        Agent("research", "Research", "Information retrieval",
              keywords=["pesquisar", "pesquise", "procure", "buscar", "busque",
                        "search", "research", "investigar", "investigue", "what is", "o que é",
                        "quem é", "como funciona"],
              domains=["research", "web"],
              handler=research_handler),
        Agent("programming", "Programming", "Code generation & analysis",
              keywords=["code", "código", "programar", "programa", "function", "função",
                        "class", "classe", "compile", "compilar", "debug", "depurar",
                        "criar", "create", "crie um projeto", "git status",
                        "git log", "git diff", "branch"],
              domains=["programming", "code"],
              handler=programming_handler),
        Agent("designer", "Designer", "UI/UX & graphic design",
              keywords=["design", "desenhar", "desenhe", "ui", "ux", "layout",
                        "mockup", "logotipo", "logo", "cor", "color"],
              domains=["design", "ui"],
              handler=designer_handler),
        Agent("marketing", "Marketing", "Marketing strategy",
              keywords=["marketing", "campaign", "campanha", "marca", "branding", "persona"],
              domains=["marketing"],
              handler=marketing_handler),
        Agent("seo", "SEO", "Search engine optimisation",
              keywords=["seo", "keyword", "palavra-chave", "ranking", "backlink", "serp"],
              domains=["seo"],
              handler=seo_handler),
        Agent("content", "Content", "Content creation",
              keywords=["conteúdo", "content", "artigo", "blog", "post", "escrever", "escreva"],
              domains=["content"],
              handler=content_handler),
        Agent("commercial", "Commercial", "Sales & commercial ops",
              keywords=["vender", "venda", "cliente", "crm", "comercial", "sales"],
              domains=["commercial", "sales"],
              handler=commercial_handler),
        Agent("financial", "Financial", "Finance & markets",
              keywords=["financeiro", "finance", "stock", "ação", "ações", "investir",
                        "invest", "money", "dinheiro", "budget", "orçamento"],
              domains=["finance"],
              handler=financial_handler),
        Agent("agenda", "Agenda", "Calendar & scheduling",
              keywords=["agenda", "calendário", "calendar", "lembrete", "reminder",
                        "reunião", "meeting", "schedule", "clima",
                        "previsão do tempo", "previsao do tempo", "tempo em"],
              domains=["agenda", "calendar"],
              handler=agenda_handler),
        Agent("communication", "Communication", "Connected email",
              keywords=["email", "e-mail", "inbox", "caixa de entrada",
                        "mensagens recebidas"],
              domains=["email", "communication"],
              handler=communication_handler),
        Agent("navigation", "Navigation", "Web & URL routing",
              keywords=["navegar", "navegue", "abrir youtube", "abrir github", "abrir google",
                        "abrir chatgpt", "abrir figma", "abrir notion", "abrir drive",
                        "abrir instagram", "abrir linkedin", "abrir twitter"],
              domains=["navigation", "web", "url"],
              handler=navigation_handler),
        Agent("system", "System", "Power & system control",
              keywords=["desligar", "desligue", "reiniciar", "reinicie", "bloquear",
                        "bloqueie", "shutdown", "restart", "lock", "suspend",
                        "hibernar", "dormir", "sair", "logout", "uso do sistema",
                        "uso do meu sistema", "cpu", "memória ram",
                        "processos em execução", "estado do sistema",
                        "diagnóstico do sistema", "fora do normal"],
              domains=["system", "power"],
              handler=system_handler),
        Agent("security", "Security", "Security & threat analysis",
              keywords=["segurança", "security", "ameaça", "threat", "firewall",
                        "scan", "verificar", "verifique", "antivírus",
                        "criptografar", "criptografe", "descriptografar",
                        "descriptografe", "encrypt", "decrypt"],
              domains=["security"],
              handler=security_handler),
        Agent("database", "Database", "Persistent data access",
              keywords=["banco", "database", "db", "sql", "tabela", "query"],
              domains=["database"],
              handler=database_handler),
        Agent("memory", "Memory", "Long-term memory manager",
              keywords=["lembrar", "lembre", "remember", "memorize", "memória", "memory",
                        "esqueça", "forget"],
              domains=["memory"],
              handler=memory_handler),
        Agent("vision", "Vision", "Image & screen analysis",
              keywords=["ver", "veja", "olhe", "olhar", "tela", "screen",
                        "câmera", "camera", "webcam", "imagem", "image",
                        "foto", "print", "captura", "analisar imagem",
                        "mostrar tela", "o que tem na tela"],
              domains=["vision", "image", "camera"],
              handler=vision_handler),
    ]
