"""Runtime configuration, read once from environment variables."""
from __future__ import annotations

import os
from pathlib import Path


def _load_dotenv(path: Path) -> None:
    """Minimal .env loader so the app has zero extra dependencies."""
    if not path.exists():
        return
    for raw in path.read_text(encoding="utf-8-sig").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


BACKEND_DIR = Path(__file__).resolve().parent.parent
PROJECT_DIR = BACKEND_DIR.parent
_load_dotenv(PROJECT_DIR / ".env")


def _float(name: str, default: float) -> float:
    try:
        return float(os.environ.get(name, default))
    except ValueError:
        return default


DATA_DIR = Path(os.environ.get("VO_DATA_DIR", BACKEND_DIR / "data"))
DB_PATH = Path(os.environ.get("VO_DB_PATH", DATA_DIR / "vendor_onboarding.db"))
UPLOAD_DIR = Path(os.environ.get("VO_UPLOAD_DIR", DATA_DIR / "uploads"))
SAMPLE_DIR = BACKEND_DIR / "sample_data"
SEED_DIR = Path(__file__).resolve().parent / "seed"
FRONTEND_DIST = PROJECT_DIR / "frontend" / "dist"

PUBLIC_BASE_URL = os.environ.get("VO_PUBLIC_BASE_URL", "http://localhost:8000").rstrip("/")

# Seconds to pause between pipeline stages so the live view is watchable.
STAGE_DELAY_SECONDS = _float("VO_STAGE_DELAY_SECONDS", 0.6)

MAX_UPLOAD_BYTES = int(_float("VO_MAX_UPLOAD_MB", 5) * 1024 * 1024)

# Decision thresholds.
REVIEW_RISK_THRESHOLD = int(_float("VO_REVIEW_RISK_THRESHOLD", 30))
BANK_LETTER_MAX_AGE_DAYS = int(_float("VO_BANK_LETTER_MAX_AGE_DAYS", 90))
SANCTIONS_REVIEW_SCORE = int(_float("VO_SANCTIONS_REVIEW_SCORE", 85))
SANCTIONS_BLOCK_SCORE = int(_float("VO_SANCTIONS_BLOCK_SCORE", 95))

# Optional LLM layer. Never used for the approve/reject decision itself.
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "").strip()
OPENAI_MODEL = os.environ.get("OPENAI_MODEL", "gpt-4o-mini")
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "").strip()
ANTHROPIC_MODEL = os.environ.get("ANTHROPIC_MODEL", "claude-3-5-haiku-latest")
LLM_PROVIDER = os.environ.get("VO_LLM_PROVIDER", "auto").lower()  # auto | openai | anthropic | none
LLM_TIMEOUT_SECONDS = _float("VO_LLM_TIMEOUT_SECONDS", 20)

PROCUREMENT_EMAIL = os.environ.get("VO_PROCUREMENT_EMAIL", "procurement@acme-buyer.example")
REVIEW_TEAM_EMAIL = os.environ.get("VO_REVIEW_TEAM_EMAIL", "vendor-risk@acme-buyer.example")
BUYER_COMPANY = os.environ.get("VO_BUYER_COMPANY", "Acme Buyer Pvt Ltd")


def ensure_dirs() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
