"""Report AI quotidiano: raccolta, filtro, fact check e generatori di contenuti."""

from pathlib import Path

import truststore

# Usa l'archivio certificati di Windows (necessario se l'antivirus ispeziona l'HTTPS).
truststore.inject_into_ssl()

ROOT = Path(__file__).resolve().parents[2]
CONFIG_DIR = ROOT / "config"
PROMPTS_DIR = ROOT / "prompts"
DATA_DIR = ROOT / "data"
REPORTS_DIR = ROOT / "reports"
OUTPUTS_DIR = ROOT / "outputs"
