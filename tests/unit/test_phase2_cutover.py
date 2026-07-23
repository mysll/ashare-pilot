from __future__ import annotations

import re
from pathlib import Path

from ashare_pilot import __version__


ROOT = Path(__file__).resolve().parents[2]
LEGACY_RUNTIME = re.compile(
    r"\.opencode/(?:lib|scripts|config|skills/[^/]+/(?:scripts|tests|aliases|cache|concepts|index|metadata|stocks|themes))"
)
BARE_CLI = re.compile(r"(?m)^\s*(?:[$>] ?)?ashare-pilot\b")


def test_phase2_removed_legacy_python_and_duplicate_data() -> None:
    assert not list((ROOT / ".opencode").rglob("*.py"))
    assert not (ROOT / ".opencode" / "config").exists()
    for name in ("aliases", "cache", "concepts", "index", "metadata", "stocks", "themes"):
        assert not (ROOT / ".opencode" / "skills" / "theme-library" / name).exists()


def test_runtime_instructions_use_only_the_public_cli() -> None:
    opencode_docs = [
        path
        for path in (ROOT / ".opencode").rglob("*.md")
        if "node_modules" not in path.parts
    ]
    paths = [
        ROOT / "AGENTS.md",
        ROOT / "CLAUDE.md",
        ROOT / "README.md",
        ROOT / "auto.bat",
        ROOT / "auto.sh",
        ROOT / "mise.toml",
        ROOT / "update_cookie.bat",
        ROOT / "update_theme.bat",
        ROOT / "update_theme_stock.bat",
        *opencode_docs,
    ]
    stale = {
        path.relative_to(ROOT).as_posix(): sorted(set(LEGACY_RUNTIME.findall(path.read_text(encoding="utf-8"))))
        for path in paths
        if LEGACY_RUNTIME.search(path.read_text(encoding="utf-8"))
    }
    assert stale == {}
    bare_invocations = {
        path.relative_to(ROOT).as_posix(): BARE_CLI.findall(path.read_text(encoding="utf-8"))
        for path in paths
        if BARE_CLI.search(path.read_text(encoding="utf-8"))
    }
    assert bare_invocations == {}
    mise_runtime = {
        path.relative_to(ROOT).as_posix()
        for path in paths
        if path != ROOT / "mise.toml" and "mise run pilot" in path.read_text(encoding="utf-8")
    }
    assert mise_runtime == set()


def test_release_version_and_authoritative_roots_are_consistent() -> None:
    pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    lock = (ROOT / "uv.lock").read_text(encoding="utf-8")

    assert __version__ == "1.0.0"
    assert 'version = "1.0.0"' in pyproject
    assert 'name = "ashare-pilot"\nversion = "1.0.0"' in lock
    for path in (ROOT / "config", ROOT / "data" / "theme-library", ROOT / "src" / "ashare_pilot"):
        assert path.is_dir()


def test_mise_uses_the_default_project_environment() -> None:
    mise = (ROOT / "mise.toml").read_text(encoding="utf-8")
    gitignore = (ROOT / ".gitignore").read_text(encoding="utf-8")
    pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    lock = (ROOT / "uv.lock").read_text(encoding="utf-8")

    assert 'UV_LINK_MODE = "copy"' in mise
    assert "python.uv_venv_auto" not in mise
    assert "UV_PROJECT_ENVIRONMENT" not in mise
    assert mise.count(r'set \"VIRTUAL_ENV=\"') == 2
    assert 'run = "env -u VIRTUAL_ENV uv sync"' in mise
    assert 'run = "env -u VIRTUAL_ENV uv run --frozen ashare-pilot"' in mise
    assert ".venv/" in gitignore
    assert ".venv-windows/" not in gitignore
    assert '"tzdata>=2025.2; sys_platform == \'win32\'"' in pyproject
    assert 'link-mode = "copy"' in pyproject
    assert 'name = "tzdata"' in lock


def test_windows_batch_entries_use_the_default_project_environment() -> None:
    for name in ("auto.bat", "update_cookie.bat", "update_theme.bat", "update_theme_stock.bat"):
        content = (ROOT / name).read_text(encoding="utf-8")
        assert 'set "VIRTUAL_ENV="' in content
        assert "UV_PROJECT_ENVIRONMENT" not in content
        assert "uv run --frozen ashare-pilot" in content
        assert "mise run pilot" not in content


def test_readme_documents_zero_history_memory_bootstrap() -> None:
    readme = (ROOT / "README.md").read_text(encoding="utf-8")

    assert "memory 可从零生长" in readme
    assert "automation memory init" in readme
    assert "初始化命令创建描述文件和空规则模板" in readme
    assert "不要复制示例规则" in readme
    assert "必须从可信状态恢复" not in readme
