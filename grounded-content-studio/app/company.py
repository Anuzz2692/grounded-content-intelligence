"""Company profiles: what changes when the same studio writes for a different website.

A profile is a folder, `companies/<id>/`, holding `profile.json` and (for any company other than the
default) its own copy of the prompt files in `companies/<id>/prompts/`. Choose it with COMPANY=<id>.
The website address, names shown on the page, wording rules and prompts all come from the folder, so
switching company is: scaffold a folder, edit the prompts and profile, set COMPANY.

    python -m app.company new acme --name "Acme Corp" --url https://www.acme.example/
    python -m app.company check acme
"""
import argparse
import json
import re
import shutil
import sys
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
COMPANIES_DIR = ROOT / "companies"
DEFAULT_COMPANY = "example_company"
ID_PATTERN = re.compile(r"^[a-z0-9][a-z0-9_-]{1,40}$")
# Prompts may use these placeholders; they are filled from the company's profile when a prompt is read.
PLACEHOLDERS = ("company_name", "website_url", "audience", "subject")
PLACEHOLDER_RE = re.compile(r"\{\{\s*([a-z_]+)\s*\}\}")
MAX_PROMPT_CHARS = 14000


class ProfileError(RuntimeError):
    pass


@dataclass(frozen=True)
class Profile:
    id: str
    name: str
    website_url: str
    audience: str = "customers"
    subject: str = "the company"
    brand_check_label: str = "Brand and audience sensitivity"
    tagline: str = "Write content you can trust"
    placeholder: str = "Describe what you want written"
    examples: tuple[str, ...] = ()
    restricted_terms: tuple[tuple[str, str], ...] = ()
    risky_terms: tuple[tuple[str, str], ...] = ()

    def placeholders(self) -> dict[str, str]:
        return {"company_name": self.name, "website_url": self.website_url, "audience": self.audience, "subject": self.subject}

    @property
    def directory(self) -> Path:
        return COMPANIES_DIR / self.id

    @property
    def prompt_dir(self) -> Path:
        return self.directory / "prompts"

    def public(self) -> dict:
        """What the web page may show."""
        return {
            "id": self.id, "name": self.name, "audience": self.audience, "subject": self.subject,
            "brand_check_label": self.brand_check_label, "tagline": self.tagline, "placeholder": self.placeholder,
            "examples": list(self.examples),
        }


def _pairs(items: object, where: str) -> tuple[tuple[str, str], ...]:
    if not isinstance(items, list):
        raise ProfileError(f"{where} must be a list")
    out = []
    for item in items:
        label, pattern = (item.get("label"), item.get("pattern")) if isinstance(item, dict) else (item, None)
        if not isinstance(label, str) or not label.strip():
            raise ProfileError(f"{where}: every entry needs a label")
        # A plain label matches that wording, ignoring case, spacing and punctuation between words.
        if not (isinstance(pattern, str) and pattern.strip()):
            pattern = r"(?<!\w)" + r"[\s\-_]+".join(re.escape(w) for w in label.split()) + r"(?!\w)"
        try:
            re.compile(pattern)
        except re.error as exc:
            raise ProfileError(f"{where}: the pattern for '{label}' is not a valid regular expression ({exc})") from exc
        out.append((label.strip(), pattern))
    return tuple(out)


@lru_cache(maxsize=16)
def _load(path: Path, mtime: float) -> Profile:  # path and mtime are the key, so edits are picked up
    company = path.parent.name
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise ProfileError(f"{path} could not be read ({type(exc).__name__})") from exc
    if not isinstance(raw, dict) or not str(raw.get("name", "")).strip() or not str(raw.get("website_url", "")).startswith(("http://", "https://")):
        raise ProfileError(f"{path} needs a 'name' and a 'website_url' starting with http:// or https://")
    texts = ("name", "website_url", "audience", "subject", "brand_check_label", "tagline", "placeholder")
    values = {k: str(raw[k]) for k in texts if k in raw}
    values["examples"] = tuple(str(e) for e in raw.get("examples", []))
    values["restricted_terms"] = _pairs(raw.get("restricted_terms", []), "restricted_terms")
    values["risky_terms"] = _pairs(raw.get("risky_terms", []), "risky_terms")
    return Profile(id=company, **values)


def load_profile(company: str | None = None) -> Profile:
    if company is None:
        from app.config import get_settings
        company = get_settings().company
    if not ID_PATTERN.match(company):
        raise ProfileError(f"COMPANY '{company}' is not a valid folder name (lower-case letters, digits, _ and -)")
    path = COMPANIES_DIR / company / "profile.json"
    if not path.is_file():
        raise ProfileError(f"No profile for COMPANY '{company}'. Create it with: python -m app.company new {company} --name \"...\" --url https://...")
    return _load(path, path.stat().st_mtime)


# --- command line ---------------------------------------------------------------------------------

def scaffold(company: str, name: str, url: str) -> Path:
    from app.prompts import PROMPT_DIR
    if not ID_PATTERN.match(company):
        raise ProfileError("The company id must be lower-case letters, digits, _ or - (2 to 41 characters).")
    if not url.startswith(("http://", "https://")):
        raise ProfileError("The website address must start with http:// or https://")
    target = COMPANIES_DIR / company
    if target.exists():
        raise ProfileError(f"{target} already exists; nothing was changed.")
    (target / "prompts").mkdir(parents=True)
    for source in sorted(PROMPT_DIR.glob("*.txt")):
        shutil.copy(source, target / "prompts" / source.name)
    profile = {
        "name": name, "website_url": url, "audience": "customers", "subject": "the company",
        "brand_check_label": "Brand and audience sensitivity",
        "tagline": "Write content you can trust", "placeholder": "Describe what you want written", "examples": [],
        "restricted_terms": [], "risky_terms": [],
    }
    (target / "profile.json").write_text(json.dumps(profile, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return target


def check(company: str) -> tuple[list[str], list[str]]:
    """(problems, warnings). Problems stop the company working; warnings are things still to edit."""
    from app import llm, structured
    from app.prompts import PROMPT_DIR
    try:
        profile = load_profile(company)
    except ProfileError as exc:
        return [str(exc)], []
    problems: list[str] = []
    warnings: list[str] = []
    if company == DEFAULT_COMPANY:
        return problems, warnings
    for source in sorted(PROMPT_DIR.glob("*.txt")):
        mine = profile.prompt_dir / source.name
        if not mine.is_file():
            problems.append(f"{source.name} is missing from {profile.prompt_dir}")
            continue
        text = mine.read_text(encoding="utf-8")
        if text.count("Version:") != 1:
            problems.append(f"{mine.name} must contain exactly one 'Version:' line")
        unknown = sorted({m for m in PLACEHOLDER_RE.findall(text) if m not in PLACEHOLDERS})
        if unknown:
            problems.append(f"{mine.name} uses unknown placeholders: {', '.join('{{' + u + '}}' for u in unknown)}")
    core = profile.prompt_dir / "content_generation.txt"
    if core.is_file():
        core_text = core.read_text(encoding="utf-8")
        for content_type, length in (("video_script", "standard"), ("social_post", "standard"), ("faq", "standard"), ("article", "detailed"), (structured.BRIEF_VIDEO, "standard")):
            module = profile.prompt_dir / llm.MODULE_FILES[llm.content_group(content_type)]
            if not module.is_file():
                continue
            module_text = module.read_text(encoding="utf-8")
            if len(core_text) + len(module_text) > MAX_PROMPT_CHARS:
                warnings.append(f"content_generation.txt plus {module.name} is over {MAX_PROMPT_CHARS} characters; a small local model may lose the end")
            absent = [f for f in structured.typed_schema(content_type, length)["properties"] if f not in module_text and f not in core_text]
            if absent:
                problems.append(f"{module.name} does not explain these output fields: {', '.join(absent)}")
    if not (profile.prompt_dir / "brand_guidelines.md").is_file():
        warnings.append("No prompts/brand_guidelines.md: brand validation will always ask for review until you add the company's real guidelines")
    if not profile.examples:
        warnings.append("profile.json has no example topics for the page")
    return problems, warnings


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m app.company")
    sub = parser.add_subparsers(dest="command", required=True)
    new = sub.add_parser("new", help="create companies/<id>/ with a copy of the prompts to edit")
    new.add_argument("id")
    new.add_argument("--name", required=True)
    new.add_argument("--url", required=True)
    chk = sub.add_parser("check", help="verify a company folder is complete")
    chk.add_argument("id")
    args = parser.parse_args(argv)
    try:
        if args.command == "new":
            target = scaffold(args.id, args.name, args.url)
            print(f"Created {target}\nNext: edit the files in {target / 'prompts'} and {target / 'profile.json'}, "
                  f"run `python -m app.company check {args.id}`, then set COMPANY={args.id} in .env.")
            return 0
        problems, warnings = check(args.id)
    except ProfileError as exc:
        print(f"ERROR: {exc}")
        return 1
    for line in problems:
        print(f"PROBLEM: {line}")
    for line in warnings:
        print(f"TO EDIT: {line}")
    print("OK" if not problems else f"{len(problems)} problem(s)")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
