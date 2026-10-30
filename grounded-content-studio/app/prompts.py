from pathlib import Path

PROMPT_DIR = Path(__file__).resolve().parent.parent / "prompts"


def _company_dir() -> tuple[Path, bool]:
    """(the active company's prompt folder, whether it is the default company)."""
    from app.company import DEFAULT_COMPANY, load_profile
    profile = load_profile()
    return profile.prompt_dir, profile.id == DEFAULT_COMPANY


def fill_placeholders(text: str) -> str:
    """Replace {{company_name}}, {{website_url}}, {{audience}} and {{subject}} with the active company's values."""
    from app.company import PLACEHOLDER_RE, load_profile
    values = load_profile().placeholders()
    return PLACEHOLDER_RE.sub(lambda m: values.get(m.group(1), m.group(0)), text)


def read_prompt(filename: str) -> str:
    own, is_default = _company_dir()
    path = own / filename
    if not path.is_file():
        if not is_default:
            # No silent fallback: the shared prompts are written for another business.
            raise RuntimeError(f"Required prompt file is missing for this company: {path}. Create the folder with `python -m app.company new`.")
        path = PROMPT_DIR / filename

    if not path.is_file():
        raise RuntimeError(f"Required prompt file is missing: {filename}")

    prompt = path.read_text(encoding="utf-8").strip()
    prompt = fill_placeholders(prompt)

    if not prompt:
        raise RuntimeError(f"Required prompt file is empty: {filename}")

    return prompt


BRAND_GUIDELINES_FILE = "brand_guidelines.md"


def load_brand_guidelines(directory: Path | None = None) -> str:
    """Approved brand guidelines for the active company, or "" if there are none.

    The company's own prompts/brand_guidelines.md is used; the shared prompts/ folder only for the default company.
    """
    if directory is not None:
        folders = [directory]
    else:
        own, is_default = _company_dir()
        folders = [own] + ([PROMPT_DIR] if is_default else [])
    for folder in folders:
        path = folder / BRAND_GUIDELINES_FILE
        if path.is_file():
            text = path.read_text(encoding="utf-8").strip()
            if text:
                return text
    return ""
