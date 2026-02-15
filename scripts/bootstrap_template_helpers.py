import re
import subprocess
from dataclasses import dataclass
from pathlib import Path


@dataclass
class GitOrigin:
    raw_url: str
    repository_url: str | None
    repo_name: str | None


def git_origin(root: Path) -> GitOrigin | None:
    result = subprocess.run(
        ["git", "remote", "get-url", "origin"],
        cwd=root,
        text=True,
        capture_output=True,
    )
    if result.returncode != 0:
        return None

    raw_url = result.stdout.strip()
    if not raw_url:
        return None

    repository_url = normalize_github_url(raw_url)
    repo_name = repo_name_from_url(raw_url) or repo_name_from_url(repository_url)
    return GitOrigin(raw_url=raw_url, repository_url=repository_url, repo_name=repo_name)


def normalize_github_url(remote_url: str) -> str | None:
    url = remote_url.strip().rstrip("/")

    match = re.match(r"git@github\.com:(.+?)(?:\.git)?$", url)
    if match:
        return f"https://github.com/{match.group(1)}"

    match = re.match(r"(https://github\.com/.+?)(?:\.git)?$", url)
    if match:
        return match.group(1)

    return None


def repo_name_from_url(url: str | None) -> str | None:
    if not url:
        return None

    normalized = url.rstrip("/")
    match = re.search(r"([^/:]+?)(?:\.git)?$", normalized)
    if not match:
        return None

    repo_name = match.group(1)
    return repo_name or None


def git_config_value(root: Path, key: str) -> str | None:
    result = subprocess.run(
        ["git", "config", "--get", key],
        cwd=root,
        text=True,
        capture_output=True,
    )
    if result.returncode != 0:
        return None

    value = result.stdout.strip()
    return value or None


def toml_quote(value: str) -> str:
    escaped = value.replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'


def section_span(text: str, section: str) -> tuple[int, int] | None:
    pattern = re.compile(rf"(?ms)^\[{re.escape(section)}\]\n(.*?)(?=^\[|\Z)")
    match = pattern.search(text)
    if not match:
        return None
    return match.start(1), match.end(1)


def set_key_in_section(text: str, section: str, key: str, line: str) -> str:
    span = section_span(text, section)
    if span is None:
        raise RuntimeError(f"Missing section [{section}] in pyproject.toml")

    start, end = span
    body = text[start:end]
    key_pattern = re.compile(rf"(?m)^{re.escape(key)}\s*=.*$")

    if key_pattern.search(body):
        body = key_pattern.sub(line, body, count=1)
    else:
        if body and not body.endswith("\n"):
            body += "\n"
        body += f"{line}\n"

    return text[:start] + body + text[end:]


def ensure_section(text: str, section: str, before_section: str | None = None) -> str:
    if section_span(text, section) is not None:
        return text

    new_section = f"\n[{section}]\n"
    if before_section:
        anchor = re.search(rf"(?m)^\[{re.escape(before_section)}\]\n", text)
        if anchor:
            head = text[: anchor.start()].rstrip() + "\n"
            tail = text[anchor.start() :]
            return head + new_section + "\n" + tail

    return text.rstrip() + new_section + "\n"


def format_authors_line(author_name: str, author_email: str) -> str | None:
    if not author_name and not author_email:
        return None

    parts: list[str] = []
    if author_name:
        parts.append(f"name = {toml_quote(author_name)}")
    if author_email:
        parts.append(f"email = {toml_quote(author_email)}")

    return f"authors = [{{ {', '.join(parts)} }}]"
