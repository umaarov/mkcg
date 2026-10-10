from __future__ import annotations

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT = Path(__file__).resolve().parents[1]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="CG_", env_file=".env", extra="ignore")

    data_dir: Path = ROOT / "var"
    tessdata_dir: Path = ROOT.parents[1] / "data" / "tessdata"
    secret_key: str = "dev-secret-change-me"

    # Router / PIIModule. Perimeter mode = no request may leave the host.
    perimeter_mode: bool = False
    anthropic_api_key: str = ""
    extraction_model: str = "claude-haiku-5-5"
    memo_model: str = "claude-sonnet-5-5"
    # Any hosted OpenAI-compatible API (DeepSeek, OpenRouter, ...). Treated as EXTERNAL: masked text only, blocked in perimeter mode.
    openai_base_url: str = ""  # e.g. https://api.deepseek.com/v1
    openai_api_key: str = ""
    openai_extraction_model: str = "deepseek-chat"
    openai_memo_model: str = "deepseek-chat"
    local_base_url: str = ""  # OpenAI-compatible endpoint (vLLM / Ollama) for the on-prem path
    local_model: str = "qwen2.5-7b-instruct"

    # Price table, USD per 1M tokens. Assumption: check the provider's price page before quoting. Models not listed are reported as unpriced (0);
    # set CG_PRICE_IN_PER_M / CG_PRICE_OUT_PER_M as JSON, e.g. '{"deepseek-chat": 0.0}', to meter another model.
    price_in_per_m: dict[str, float] = {"claude-haiku-5-5": 1.0, "claude-sonnet-5-5": 3.0}
    price_out_per_m: dict[str, float] = {"claude-haiku-5-5": 5.0, "claude-sonnet-5-5": 15.0}

    cors_origins: str = "*"
    max_cases_per_hour: int = 40
    public_demo: bool = True

    @property
    def db_url(self) -> str:
        return f"sqlite:///{self.data_dir / 'creditgateway.db'}"

    @property
    def uploads_dir(self) -> Path:
        return self.data_dir / "uploads"

    @property
    def models_dir(self) -> Path:
        # trained artifacts ship with the code (small, reproducible via `python -m app.modules.scoring.train`)
        return ROOT / "models"

    @property
    def keys_dir(self) -> Path:
        return self.data_dir / "keys"


settings = Settings()
for _d in (settings.data_dir, settings.uploads_dir, settings.models_dir, settings.keys_dir):
    _d.mkdir(parents=True, exist_ok=True)
