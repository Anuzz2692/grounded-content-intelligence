from functools import lru_cache
from typing import Literal

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # Which company the studio writes for: a folder under companies/ with its profile and prompts.
    company: str = "example_company"
    # Leave empty to use the company's website_url from its profile; set it to override.
    website_base_url: str = ""
    # auto: Claude first, Ollama if Claude fails. ollama / anthropic: use only that provider.
    llm_provider: Literal["auto", "anthropic", "ollama"] = "auto"
    anthropic_api_key: str | None = None
    anthropic_model: str = "claude-sonnet-4-5"
    ollama_base_url: str = "http://localhost:11434"
    ollama_model: str = "qwen2.5:7b"
    request_timeout_seconds: float = 12.0
    llm_timeout_seconds: float = 150.0
    # Local models may need to cold-load, so Ollama gets its own, longer timeout.
    ollama_timeout_seconds: float = 300.0
    # Ollama's default context window is small and silently truncates long prompts.
    ollama_num_ctx: int = 8192
    # Upper bound when the context window is enlarged to fit a long prompt (more RAM at higher values).
    ollama_max_ctx: int = 16384
    # Smaller research budget for local models, which have short contexts and slower input.
    ollama_max_research_chars: int = 12000
    cache_ttl_seconds: int = 300
    max_pages_to_fetch: int = 8
    max_chars_per_page: int = 9000
    max_research_chars: int = 26000
    max_output_tokens: int = 2200
    # Comma-separated API keys accepted in the X-API-Key header. Empty disables auth.
    api_keys: str = ""
    # Requests per client per minute on the generate endpoint. 0 disables the limit.
    rate_limit_per_minute: int = 10
    validator_max_tokens: int = 6000
    # When the format check finds misses (wrong counts, missing sections), ask the model once to fix them.
    format_repair: bool = True
    # Rewrite the draft so it reads naturally (one extra model call). Requests can still opt out.
    humanize_enabled: bool = True
    # If a rewrite still leaves 3 or more stock-phrase problems, run one more pass that targets them.
    humanize_second_pass: bool = True

    @property
    def api_key_list(self) -> list[str]:
        return [k.strip() for k in self.api_keys.split(",") if k.strip()]

    @model_validator(mode="after")
    def _fill_from_company_profile(self):
        if not self.website_base_url.strip():
            from app.company import load_profile
            self.website_base_url = load_profile(self.company).website_url
        return self

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()
