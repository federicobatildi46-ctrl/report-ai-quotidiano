"""Chiamate a Claude Code in modalità headless (`claude -p`), con l'abbonamento, non l'API.

Accorgimenti:
- nessun connettore MCP e nessuno strumento: Claude riceve tutto nel prompt e risponde in JSON
  validato con --json-schema (meno token, niente sorprese);
- su Windows si chiama direttamente claude.exe (il wrapper .cmd rovina le virgolette del JSON);
- si toglie CLAUDECODE dall'ambiente, così funziona anche lanciato da dentro Claude Code.
"""

import json
import os
import shutil
import subprocess
import time
from pathlib import Path


class ClaudeError(RuntimeError):
    pass


def claude_executable() -> str:
    found = shutil.which("claude")
    if not found:
        raise ClaudeError("Claude Code CLI non trovato: installa con `npm i -g @anthropic-ai/claude-code`")
    p = Path(found)
    if p.suffix.lower() in (".cmd", ".ps1", ""):
        native = p.parent / "node_modules" / "@anthropic-ai" / "claude-code" / "bin" / "claude.exe"
        if native.exists():
            return str(native)
    return found


def run_claude(prompt: str, schema: dict, *, system: str, model: str = "sonnet",
               timeout: int = 1200, tools: list[str] | None = None) -> tuple[dict, dict]:
    """Ritorna (output strutturato, statistiche d'uso).

    `tools`: strumenti di sola lettura da concedere (es. ["WebSearch", "WebFetch"] per le
    ricerche online); di default nessuno."""
    tools = tools or []
    cmd = [
        claude_executable(), "-p",
        "--model", model,
        "--output-format", "json",
        "--system-prompt", system,
        "--json-schema", json.dumps(schema, ensure_ascii=False),
        "--strict-mcp-config", "--mcp-config", '{"mcpServers":{}}',
        "--tools", ",".join(tools),
        "--no-session-persistence",
    ]
    if tools:
        cmd += ["--allowedTools", *tools]
    env = {k: v for k, v in os.environ.items() if k not in ("CLAUDECODE", "CLAUDE_CODE_ENTRYPOINT")}
    if env.get("CLAUDE_CODE_OAUTH_TOKEN"):
        # copiando il token da un terminale stretto può entrarci uno spazio/a capo: lo togliamo
        env["CLAUDE_CODE_OAUTH_TOKEN"] = "".join(env["CLAUDE_CODE_OAUTH_TOKEN"].split())
    t0 = time.perf_counter()
    proc = subprocess.run(cmd, input=prompt, capture_output=True, text=True, encoding="utf-8",
                          timeout=timeout, env=env)
    secs = round(time.perf_counter() - t0, 1)
    try:
        data = json.loads(proc.stdout)
    except json.JSONDecodeError:
        raise ClaudeError(f"risposta non JSON (exit {proc.returncode}): "
                          f"{(proc.stdout or proc.stderr)[:500]}") from None
    if data.get("is_error") or data.get("structured_output") is None:
        raise ClaudeError(f"errore Claude ({data.get('subtype')}): {str(data.get('result'))[:500]}")
    usage = data.get("usage", {})
    stats = {
        "secs": secs,
        "turns": data.get("num_turns"),
        # token nuovi (pesano sulla quota) vs riletti dalla cache (pesano molto meno)
        "input_tokens": usage.get("input_tokens", 0) + usage.get("cache_creation_input_tokens", 0),
        "cache_read_tokens": usage.get("cache_read_input_tokens", 0),
        "output_tokens": usage.get("output_tokens", 0),
        "equivalent_api_usd": data.get("total_cost_usd"),  # solo indicativo: col Pro non si paga
    }
    return data["structured_output"], stats
