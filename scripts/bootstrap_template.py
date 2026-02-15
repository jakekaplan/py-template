#!/usr/bin/env python3

import argparse
import importlib.util
import json
import re
import shutil
import subprocess
import sys
import tomllib
from dataclasses import dataclass, field
from pathlib import Path

TEMPLATE_DIST_NAME = "py-template"
TEMPLATE_IMPORT_NAME = "py_template"
ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = Path(__file__).resolve()
SCRIPT_DIR = SCRIPT_PATH.parent
BOOTSTRAP_HELPER_PATH = SCRIPT_DIR / "bootstrap_template_helpers.py"
helper_spec = importlib.util.spec_from_file_location(
    "bootstrap_template_helpers", BOOTSTRAP_HELPER_PATH
)
if helper_spec is None or helper_spec.loader is None:
    raise RuntimeError(f"Could not load helper module: {BOOTSTRAP_HELPER_PATH}")

helper_module = importlib.util.module_from_spec(helper_spec)
sys.modules[helper_spec.name] = helper_module
helper_spec.loader.exec_module(helper_module)

GitOrigin = helper_module.GitOrigin
ensure_section = helper_module.ensure_section
format_authors_line = helper_module.format_authors_line
set_key_in_section = helper_module.set_key_in_section
toml_quote = helper_module.toml_quote
_git_config_value = helper_module.git_config_value
_git_origin = helper_module.git_origin

BOOTSTRAP_TEST_PATH = ROOT / "tests" / "test_bootstrap_template.py"
STATE_PATH = ROOT / ".bootstrap-state.json"
STATE_BACKUP_DIR = ROOT / ".bootstrap-state-backups"
DEFAULT_PYTHON_RANGE = ">=3.11"
DIST_NAME_PATTERN = re.compile(r"^[A-Za-z0-9](?:[A-Za-z0-9._-]*[A-Za-z0-9])?$")
IMPORT_NAME_PATTERN = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


@dataclass
class BootstrapValues:
    dist_name: str
    import_name: str
    description: str
    author_name: str
    author_email: str
    repository_url: str
    issues_url: str
    python_range: str


@dataclass
class RollbackState:
    original_files: dict[Path, str] = field(default_factory=dict)
    renamed_dirs: list[tuple[Path, Path]] = field(default_factory=list)
    backup_files: dict[Path, Path] = field(default_factory=dict)


def git_origin() -> GitOrigin | None:
    return _git_origin(ROOT)


def git_config_value(key: str) -> str | None:
    return _git_config_value(ROOT, key)


def prompt(message: str, default: str = "") -> str:
    suffix = f" [{default}]" if default else ""
    value = input(f"{message}{suffix}: ").strip()
    return value or default


def run(cmd: list[str]) -> None:
    print(f"→ {' '.join(cmd)}")
    subprocess.run(cmd, cwd=ROOT, check=True)


def tracked_files() -> list[Path]:
    result = subprocess.run(
        ["git", "ls-files"],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=True,
    )
    return [ROOT / line for line in result.stdout.splitlines() if line.strip()]


def should_skip_placeholder_file(path: Path) -> bool:
    return (
        path.resolve() == SCRIPT_PATH
        or path.resolve() == BOOTSTRAP_HELPER_PATH
        or path.resolve() == BOOTSTRAP_TEST_PATH
        or path.name == "uv.lock"
        or path.is_symlink()
        or not path.exists()
        or not path.is_file()
    )


def checkpoint_payload(state: RollbackState) -> dict[str, list[dict[str, str]]]:
    files = [
        {
            "path": str(path.relative_to(ROOT)),
            "backup": str(backup_path.relative_to(ROOT)),
        }
        for path, backup_path in state.backup_files.items()
    ]
    renames = [
        {"old": str(old.relative_to(ROOT)), "new": str(new.relative_to(ROOT))}
        for old, new in state.renamed_dirs
    ]
    return {"files": files, "renames": renames}


def write_checkpoint(state: RollbackState) -> None:
    STATE_BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    STATE_PATH.write_text(json.dumps(checkpoint_payload(state), indent=2) + "\n", encoding="utf-8")


def cleanup_checkpoint() -> None:
    STATE_PATH.unlink(missing_ok=True)
    shutil.rmtree(STATE_BACKUP_DIR, ignore_errors=True)


def recover_from_checkpoint() -> None:
    if not STATE_PATH.exists():
        return

    data = json.loads(STATE_PATH.read_text(encoding="utf-8"))
    renames = data.get("renames", [])
    files = data.get("files", [])

    for rename in reversed(renames):
        old_dir = ROOT / rename["old"]
        new_dir = ROOT / rename["new"]
        if new_dir.exists() and not old_dir.exists():
            new_dir.rename(old_dir)

    restored = 0
    for file_entry in files:
        target_path = ROOT / file_entry["path"]
        backup_path = ROOT / file_entry["backup"]
        if not backup_path.exists():
            continue

        target_path.parent.mkdir(parents=True, exist_ok=True)
        target_path.write_text(backup_path.read_text(encoding="utf-8"), encoding="utf-8")
        restored += 1

    cleanup_checkpoint()
    print(f"Recovered from interrupted bootstrap: restored {restored} files")


def backup_text_file(path: Path, state: RollbackState) -> None:
    if path in state.original_files:
        return
    if not path.exists() or not path.is_file():
        return

    original = path.read_text(encoding="utf-8")
    state.original_files[path] = original

    backup_path = STATE_BACKUP_DIR / f"{len(state.backup_files):04d}.txt"
    backup_path.parent.mkdir(parents=True, exist_ok=True)
    backup_path.write_text(original, encoding="utf-8")
    state.backup_files[path] = backup_path

    write_checkpoint(state)


def replace_placeholders(dist_name: str, import_name: str, state: RollbackState) -> None:
    changed_file_count = 0

    for path in tracked_files():
        if should_skip_placeholder_file(path):
            continue

        try:
            original = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue

        updated = original.replace(TEMPLATE_DIST_NAME, dist_name)
        updated = updated.replace(TEMPLATE_IMPORT_NAME, import_name)

        if updated == original:
            continue

        backup_text_file(path, state)
        path.write_text(updated, encoding="utf-8")
        changed_file_count += 1

    if changed_file_count:
        print(f"Updated placeholders in {changed_file_count} files")


def rename_package_dir(import_name: str, state: RollbackState) -> None:
    src_dir = ROOT / "src"
    old_dir = src_dir / TEMPLATE_IMPORT_NAME
    new_dir = src_dir / import_name

    if not old_dir.exists() or old_dir == new_dir:
        return
    if new_dir.exists():
        raise RuntimeError(f"Target package path already exists: {new_dir}")

    old_dir.rename(new_dir)
    state.renamed_dirs.append((old_dir, new_dir))
    write_checkpoint(state)
    print(f"Renamed package dir: {old_dir.relative_to(ROOT)} -> {new_dir.relative_to(ROOT)}")


def update_pyproject(values: BootstrapValues, state: RollbackState) -> None:
    pyproject_path = ROOT / "pyproject.toml"
    text = pyproject_path.read_text(encoding="utf-8")

    project_updates = {
        "name": values.dist_name,
        "description": values.description,
        "requires-python": values.python_range,
    }
    for key, value in project_updates.items():
        text = set_key_in_section(text, "project", key, f"{key} = {toml_quote(value)}")

    authors_line = format_authors_line(values.author_name, values.author_email)
    if authors_line:
        text = set_key_in_section(text, "project", "authors", authors_line)

    if values.repository_url or values.issues_url:
        text = ensure_section(text, "project.urls", before_section="dependency-groups")
        if values.repository_url:
            text = set_key_in_section(
                text,
                "project.urls",
                "Repository",
                f"Repository = {toml_quote(values.repository_url)}",
            )
        if values.issues_url:
            text = set_key_in_section(
                text,
                "project.urls",
                "Issues",
                f"Issues = {toml_quote(values.issues_url)}",
            )

    backup_text_file(pyproject_path, state)
    pyproject_path.write_text(text, encoding="utf-8")
    print("Updated pyproject.toml metadata")


def verify() -> None:
    commands = [
        ["uv", "sync", "--group", "dev"],
        ["uv", "lock"],
        ["uv", "run", "ruff", "format", "."],
        ["uv", "run", "prek", "run", "--all-files"],
        ["uv", "run", "pytest"],
    ]
    for command in commands:
        run(command)


def rollback_changes(state: RollbackState) -> None:
    if not state.original_files and not state.renamed_dirs:
        cleanup_checkpoint()
        return

    for old_dir, new_dir in reversed(state.renamed_dirs):
        if new_dir.exists() and not old_dir.exists():
            new_dir.rename(old_dir)

    restored = 0
    for path, original in state.original_files.items():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(original, encoding="utf-8")
        restored += 1

    cleanup_checkpoint()
    print(
        f"Rollback complete: restored {restored} files, reverted {len(state.renamed_dirs)} renames"
    )


def delete_bootstrap_artifacts() -> None:
    deleted_paths: list[str] = []
    for path in (SCRIPT_PATH, BOOTSTRAP_HELPER_PATH, BOOTSTRAP_TEST_PATH):
        if path.exists():
            deleted_paths.append(str(path.relative_to(ROOT)))
        path.unlink(missing_ok=True)

    if deleted_paths:
        print(f"Deleted bootstrap artifacts: {', '.join(deleted_paths)}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Bootstrap a repository created from py-template")
    parser.add_argument(
        "package_name",
        nargs="?",
        help="Distribution package name (e.g. my-package)",
    )
    parser.add_argument("--import-name", help="Import package name (e.g. my_package)")
    parser.add_argument("--description", help="Package description")
    parser.add_argument("--author-name", help="Author name")
    parser.add_argument("--author-email", help="Author email")
    parser.add_argument("--repository-url", help="Repository URL")
    parser.add_argument("--issues-url", help="Issues URL")
    parser.add_argument("--python-range", help="requires-python value")
    parser.add_argument(
        "--no-verify",
        action="store_true",
        help="Skip uv/prek/pytest verification",
    )
    parser.add_argument(
        "--keep-script",
        action="store_true",
        help="Keep bootstrap script/tests on success",
    )
    parser.add_argument(
        "--keep-changes-on-failure",
        action="store_true",
        help="Do not rollback edits if bootstrap fails",
    )
    return parser.parse_args()


def project_defaults() -> dict[str, str]:
    pyproject_data = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    project = pyproject_data.get("project", {})

    if not isinstance(project, dict):
        return {}

    defaults: dict[str, str] = {}
    for key in ("name", "description", "requires-python"):
        value = project.get(key)
        if isinstance(value, str):
            defaults[key] = value
    return defaults


def dist_to_import_name(dist_name: str) -> str:
    return re.sub(r"[-.]", "_", dist_name)


def validate_names(dist_name: str, import_name: str) -> None:
    if not DIST_NAME_PATTERN.fullmatch(dist_name):
        raise RuntimeError(
            "Invalid distribution name. Use letters/numbers and optional '-', '_', '.' separators."
        )

    if not IMPORT_NAME_PATTERN.fullmatch(import_name):
        raise RuntimeError(
            "Invalid import name. Use a valid Python identifier (letters/numbers/underscore, "
            "not starting with a number)."
        )


def collect_values(args: argparse.Namespace) -> BootstrapValues:
    defaults = project_defaults()
    origin = git_origin()

    inferred_name = origin.repo_name if origin else None
    inferred_repo_url = origin.repository_url if origin else None
    project_name = defaults.get("name", TEMPLATE_DIST_NAME)

    project_name_fallback = "" if project_name == TEMPLATE_DIST_NAME else project_name
    inferred_dist_name = args.package_name or inferred_name or project_name_fallback

    default_import = args.import_name or (
        dist_to_import_name(inferred_dist_name) if inferred_dist_name else ""
    )
    default_description = args.description or defaults.get("description", "")
    default_python = args.python_range or defaults.get("requires-python", DEFAULT_PYTHON_RANGE)
    default_repo = args.repository_url or inferred_repo_url or ""
    default_author_name = args.author_name or git_config_value("user.name") or ""
    default_author_email = args.author_email or git_config_value("user.email") or ""

    interactive = sys.stdin.isatty()

    if interactive:
        dist_name = args.package_name or prompt("Distribution name (e.g. my-package)")
        if not dist_name:
            dist_name = inferred_dist_name

        import_name = args.import_name or prompt("Import name (e.g. my_package)")
        if not import_name:
            import_name = dist_to_import_name(dist_name) if dist_name else default_import

        description = prompt("Description", default_description)
        author_name = prompt("Author name", default_author_name)
        author_email = prompt("Author email", default_author_email)
        repository_url = prompt("Repository URL", default_repo)

        issues_default = args.issues_url or (
            f"{repository_url.rstrip('/')}/issues" if repository_url else ""
        )
        issues_url = prompt("Issues URL", issues_default)
        python_range = prompt("Python range", default_python)
    else:
        dist_name = inferred_dist_name
        import_name = default_import
        description = default_description
        author_name = default_author_name
        author_email = default_author_email
        repository_url = default_repo
        issues_url = args.issues_url or (
            f"{repository_url.rstrip('/')}/issues" if repository_url else ""
        )
        python_range = default_python

    if not dist_name and not interactive:
        raise RuntimeError(
            "Could not infer distribution name. Pass package_name or set git origin remote."
        )

    return BootstrapValues(
        dist_name=dist_name,
        import_name=import_name,
        description=description,
        author_name=author_name,
        author_email=author_email,
        repository_url=repository_url,
        issues_url=issues_url,
        python_range=python_range,
    )


def main() -> int:
    recover_from_checkpoint()

    args = parse_args()
    values = collect_values(args)

    if not values.dist_name or not values.import_name:
        raise RuntimeError("Distribution and import names are required")

    validate_names(values.dist_name, values.import_name)

    rollback_state = RollbackState()
    try:
        replace_placeholders(
            dist_name=values.dist_name,
            import_name=values.import_name,
            state=rollback_state,
        )
        rename_package_dir(import_name=values.import_name, state=rollback_state)
        update_pyproject(values, state=rollback_state)

        if not args.no_verify:
            backup_text_file(ROOT / "uv.lock", rollback_state)
            verify()
    except BaseException:
        if not args.keep_changes_on_failure:
            rollback_changes(rollback_state)
        else:
            cleanup_checkpoint()
        raise

    cleanup_checkpoint()

    if not args.keep_script:
        delete_bootstrap_artifacts()

    print("Bootstrap complete")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"Bootstrap failed: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc
