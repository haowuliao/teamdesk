"""环境配置：LLM 接入点。无 key 时进入离线模式（is_llm_offline=True）。"""
import os

DEFAULT_BASE_URL = "https://api.deepseek.com/v1"
DEFAULT_MODEL = "deepseek-chat"


def _env(name: str, default: str = "") -> str:
    return os.environ.get(name, default).strip()


class Config:
    LLM_BASE_URL: str = _env("LLM_BASE_URL", DEFAULT_BASE_URL)
    LLM_API_KEY: str = _env("LLM_API_KEY")
    LLM_MODEL: str = _env("LLM_MODEL", DEFAULT_MODEL)
    DATA_DIR: str = _env("TEAMDESK_DATA_DIR", os.path.join(os.path.dirname(os.path.dirname(__file__)), "data"))
    DATABASE_URL: str = _env("TEAMDESK_DB_URL", f"sqlite+aiosqlite:///{os.path.join(DATA_DIR, 'teamdesk.db')}")

    @property
    def is_llm_offline(self) -> bool:
        return not self.LLM_API_KEY


config = Config()
