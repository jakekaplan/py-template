import argparse
import importlib.util
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest


def load_bootstrap_module():
    script_path = Path(__file__).resolve().parents[1] / "scripts" / "bootstrap_template.py"
    spec = importlib.util.spec_from_file_location("bootstrap_template", script_path)
    assert spec is not None
    assert spec.loader is not None

    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def make_args(**overrides):
    values = {
        "package_name": None,
        "import_name": None,
        "description": None,
        "author_name": None,
        "author_email": None,
        "repository_url": None,
        "issues_url": None,
        "python_range": None,
        "no_verify": False,
        "keep_script": False,
        "keep_changes_on_failure": False,
    }
    values.update(overrides)
    return argparse.Namespace(**values)


def test_collect_values_first_two_prompts_have_no_defaults(monkeypatch) -> None:
    bootstrap = load_bootstrap_module()

    monkeypatch.setattr(
        bootstrap,
        "project_defaults",
        lambda: {"name": "py-template", "description": "A package", "requires-python": ">=3.11"},
    )
    monkeypatch.setattr(
        bootstrap,
        "git_origin",
        lambda: bootstrap.GitOrigin(
            raw_url="git@github.com:acme/cool-tool.git",
            repository_url="https://github.com/acme/cool-tool",
            repo_name="cool-tool",
        ),
    )
    monkeypatch.setattr(bootstrap, "git_config_value", lambda key: None)
    monkeypatch.setattr(bootstrap.sys, "stdin", SimpleNamespace(isatty=lambda: True))

    prompts: list[str] = []
    answers = iter(["", "", "", "", "", "", "", ""])

    def fake_input(prompt_text: str) -> str:
        prompts.append(prompt_text)
        return next(answers)

    monkeypatch.setattr("builtins.input", fake_input)

    values = bootstrap.collect_values(make_args())

    assert prompts[0] == "Distribution name (e.g. my-package): "
    assert prompts[1] == "Import name (e.g. my_package): "
    assert "[" not in prompts[0]
    assert "[" not in prompts[1]
    assert values.dist_name == "cool-tool"
    assert values.import_name == "cool_tool"


def test_collect_values_issues_default_tracks_repo_prompt(monkeypatch) -> None:
    bootstrap = load_bootstrap_module()

    monkeypatch.setattr(
        bootstrap,
        "project_defaults",
        lambda: {"name": "py-template", "description": "A package", "requires-python": ">=3.11"},
    )
    monkeypatch.setattr(
        bootstrap,
        "git_origin",
        lambda: bootstrap.GitOrigin(
            raw_url="git@github.com:acme/original.git",
            repository_url="https://github.com/acme/original",
            repo_name="original",
        ),
    )
    monkeypatch.setattr(bootstrap, "git_config_value", lambda key: None)
    monkeypatch.setattr(bootstrap.sys, "stdin", SimpleNamespace(isatty=lambda: True))

    answers = iter(["", "", "", "", "", "https://github.com/acme/renamed", "", ""])
    monkeypatch.setattr("builtins.input", lambda prompt_text: next(answers))

    values = bootstrap.collect_values(make_args())

    assert values.repository_url == "https://github.com/acme/renamed"
    assert values.issues_url == "https://github.com/acme/renamed/issues"


def test_collect_values_noninteractive_infers_from_git(monkeypatch) -> None:
    bootstrap = load_bootstrap_module()

    monkeypatch.setattr(
        bootstrap,
        "project_defaults",
        lambda: {"name": "py-template", "description": "A package", "requires-python": ">=3.11"},
    )
    monkeypatch.setattr(
        bootstrap,
        "git_origin",
        lambda: bootstrap.GitOrigin(
            raw_url="git@github.com:acme/cool-tool.git",
            repository_url="https://github.com/acme/cool-tool",
            repo_name="cool-tool",
        ),
    )
    monkeypatch.setattr(
        bootstrap,
        "git_config_value",
        lambda key: {"user.name": "Jake", "user.email": "jake@example.com"}.get(key),
    )
    monkeypatch.setattr(bootstrap.sys, "stdin", SimpleNamespace(isatty=lambda: False))

    values = bootstrap.collect_values(make_args())

    assert values.dist_name == "cool-tool"
    assert values.import_name == "cool_tool"
    assert values.repository_url == "https://github.com/acme/cool-tool"
    assert values.issues_url == "https://github.com/acme/cool-tool/issues"
    assert values.author_name == "Jake"
    assert values.author_email == "jake@example.com"


def test_collect_values_noninteractive_requires_name(monkeypatch) -> None:
    bootstrap = load_bootstrap_module()

    monkeypatch.setattr(
        bootstrap,
        "project_defaults",
        lambda: {"name": "py-template", "description": "A package", "requires-python": ">=3.11"},
    )
    monkeypatch.setattr(bootstrap, "git_origin", lambda: None)
    monkeypatch.setattr(bootstrap, "git_config_value", lambda key: None)
    monkeypatch.setattr(bootstrap.sys, "stdin", SimpleNamespace(isatty=lambda: False))

    with pytest.raises(RuntimeError, match="Could not infer distribution name"):
        bootstrap.collect_values(make_args())


def test_validate_names() -> None:
    bootstrap = load_bootstrap_module()

    bootstrap.validate_names("good-name", "good_name")

    with pytest.raises(RuntimeError, match="Invalid distribution name"):
        bootstrap.validate_names("bad name", "good_name")

    with pytest.raises(RuntimeError, match="Invalid import name"):
        bootstrap.validate_names("good-name", "bad-name")


def test_main_rolls_back_on_failure(monkeypatch) -> None:
    bootstrap = load_bootstrap_module()

    args = make_args(keep_script=True, keep_changes_on_failure=False)
    values = bootstrap.BootstrapValues(
        dist_name="cool-tool",
        import_name="cool_tool",
        description="desc",
        author_name="",
        author_email="",
        repository_url="",
        issues_url="",
        python_range=">=3.11",
    )

    monkeypatch.setattr(bootstrap, "parse_args", lambda: args)
    monkeypatch.setattr(bootstrap, "collect_values", lambda incoming: values)
    monkeypatch.setattr(
        bootstrap,
        "replace_placeholders",
        lambda dist_name, import_name, state: None,
    )
    monkeypatch.setattr(bootstrap, "rename_package_dir", lambda import_name, state: None)
    monkeypatch.setattr(bootstrap, "update_pyproject", lambda incoming_values, state: None)
    monkeypatch.setattr(bootstrap, "verify", lambda: (_ for _ in ()).throw(RuntimeError("boom")))

    backed_up_paths: list[Path] = []

    def fake_backup(path: Path, state) -> None:
        backed_up_paths.append(path)

    monkeypatch.setattr(bootstrap, "backup_text_file", fake_backup)

    rollback_called = {"value": False}

    def fake_rollback(state):
        rollback_called["value"] = True

    monkeypatch.setattr(bootstrap, "rollback_changes", fake_rollback)

    with pytest.raises(RuntimeError, match="boom"):
        bootstrap.main()

    assert rollback_called["value"]
    assert bootstrap.ROOT / "uv.lock" in backed_up_paths


def test_main_rolls_back_on_keyboard_interrupt(monkeypatch) -> None:
    bootstrap = load_bootstrap_module()

    args = make_args(keep_script=True, keep_changes_on_failure=False)
    values = bootstrap.BootstrapValues(
        dist_name="cool-tool",
        import_name="cool_tool",
        description="desc",
        author_name="",
        author_email="",
        repository_url="",
        issues_url="",
        python_range=">=3.11",
    )

    monkeypatch.setattr(bootstrap, "parse_args", lambda: args)
    monkeypatch.setattr(bootstrap, "collect_values", lambda incoming: values)
    monkeypatch.setattr(
        bootstrap,
        "replace_placeholders",
        lambda dist_name, import_name, state: None,
    )
    monkeypatch.setattr(bootstrap, "rename_package_dir", lambda import_name, state: None)
    monkeypatch.setattr(bootstrap, "update_pyproject", lambda incoming_values, state: None)
    monkeypatch.setattr(bootstrap, "verify", lambda: (_ for _ in ()).throw(KeyboardInterrupt()))

    rollback_called = {"value": False}

    def fake_rollback(state):
        rollback_called["value"] = True

    monkeypatch.setattr(bootstrap, "rollback_changes", fake_rollback)

    with pytest.raises(KeyboardInterrupt):
        bootstrap.main()

    assert rollback_called["value"]


def test_main_skip_rollback_when_requested(monkeypatch) -> None:
    bootstrap = load_bootstrap_module()

    args = make_args(keep_script=True, keep_changes_on_failure=True)
    values = bootstrap.BootstrapValues(
        dist_name="cool-tool",
        import_name="cool_tool",
        description="desc",
        author_name="",
        author_email="",
        repository_url="",
        issues_url="",
        python_range=">=3.11",
    )

    monkeypatch.setattr(bootstrap, "parse_args", lambda: args)
    monkeypatch.setattr(bootstrap, "collect_values", lambda incoming: values)
    monkeypatch.setattr(
        bootstrap,
        "replace_placeholders",
        lambda dist_name, import_name, state: None,
    )
    monkeypatch.setattr(bootstrap, "rename_package_dir", lambda import_name, state: None)
    monkeypatch.setattr(bootstrap, "update_pyproject", lambda incoming_values, state: None)
    monkeypatch.setattr(bootstrap, "verify", lambda: (_ for _ in ()).throw(RuntimeError("boom")))

    rollback_called = {"value": False}

    def fake_rollback(state):
        rollback_called["value"] = True

    monkeypatch.setattr(bootstrap, "rollback_changes", fake_rollback)

    with pytest.raises(RuntimeError, match="boom"):
        bootstrap.main()

    assert not rollback_called["value"]


def test_delete_bootstrap_artifacts(monkeypatch, tmp_path: Path) -> None:
    bootstrap = load_bootstrap_module()

    script_path = tmp_path / "scripts" / "bootstrap_template.py"
    script_path.parent.mkdir(parents=True)
    script_path.write_text("script", encoding="utf-8")

    test_path = tmp_path / "tests" / "test_bootstrap_template.py"
    test_path.parent.mkdir(parents=True)
    test_path.write_text("tests", encoding="utf-8")

    monkeypatch.setattr(bootstrap, "ROOT", tmp_path)
    monkeypatch.setattr(bootstrap, "SCRIPT_PATH", script_path)
    monkeypatch.setattr(bootstrap, "BOOTSTRAP_TEST_PATH", test_path)

    bootstrap.delete_bootstrap_artifacts()

    assert not script_path.exists()
    assert not test_path.exists()


def test_main_deletes_bootstrap_artifacts_on_success(monkeypatch) -> None:
    bootstrap = load_bootstrap_module()

    args = make_args(keep_script=False, no_verify=True)
    values = bootstrap.BootstrapValues(
        dist_name="cool-tool",
        import_name="cool_tool",
        description="desc",
        author_name="",
        author_email="",
        repository_url="",
        issues_url="",
        python_range=">=3.11",
    )

    monkeypatch.setattr(bootstrap, "parse_args", lambda: args)
    monkeypatch.setattr(bootstrap, "collect_values", lambda incoming: values)
    monkeypatch.setattr(
        bootstrap,
        "replace_placeholders",
        lambda dist_name, import_name, state: None,
    )
    monkeypatch.setattr(bootstrap, "rename_package_dir", lambda import_name, state: None)
    monkeypatch.setattr(bootstrap, "update_pyproject", lambda incoming_values, state: None)

    deleted = {"value": False}

    def fake_delete():
        deleted["value"] = True

    monkeypatch.setattr(bootstrap, "delete_bootstrap_artifacts", fake_delete)

    assert bootstrap.main() == 0
    assert deleted["value"]
