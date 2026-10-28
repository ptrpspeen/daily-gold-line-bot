import importlib.util
import json
import os
import subprocess
from pathlib import Path

import pytest


SPEC = importlib.util.spec_from_file_location(
    "publish_images", Path(__file__).parents[1] / "tools" / "publish_images.py"
)
publisher = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(publisher)


def git(repository: Path, *arguments: str, check: bool = True) -> subprocess.CompletedProcess:
    environment = os.environ.copy()
    environment.update({
        "GIT_AUTHOR_NAME": "Test", "GIT_AUTHOR_EMAIL": "test@example.com",
        "GIT_COMMITTER_NAME": "Test", "GIT_COMMITTER_EMAIL": "test@example.com",
    })
    return subprocess.run(
        ["git", *arguments], cwd=repository, env=environment,
        capture_output=True, text=True, check=check,
    )


@pytest.fixture
def repository(tmp_path: Path) -> tuple[Path, Path]:
    origin = tmp_path / "origin.git"
    work = tmp_path / "work"
    git(tmp_path, "init", "--bare", str(origin))
    git(tmp_path, "init", "--initial-branch=main", str(work))
    (work / "README.md").write_text("original\n")
    git(work, "add", "README.md")
    git(work, "commit", "-m", "Initial code")
    git(work, "remote", "add", "origin", str(origin))
    git(work, "push", "origin", "main")
    return work, origin


def inputs(directory: Path, days: list[int]) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    for day in days:
        (directory / f"2026-10-{day:02}.png").write_bytes(f"image-{day}".encode())
    (directory / "latest.json").write_text(json.dumps({"date": f"2026-10-{max(days):02}"}))


def snapshot_files(origin: Path) -> set[str]:
    return set(git(origin, "ls-tree", "--name-only", publisher.IMAGE_REF).stdout.splitlines())


def test_publishes_two_bounded_snapshots_without_touching_code_or_index(repository) -> None:
    work, origin = repository
    directory = work / "generated" / "run"
    inputs(directory, [20, 21, 22, 23, 24])
    (directory / "latest.png").write_bytes(b"stale alias")
    (directory / "2026-02-30.png").write_bytes(b"invalid calendar date")
    (directory / "notes.txt").write_text("local notes")
    nested = directory / "nested"
    nested.mkdir()
    (nested / "2026-10-28.png").write_bytes(b"nested image")
    external = work / "external.png"
    external.write_bytes(b"private image")
    (directory / "2026-10-25.png").symlink_to(external)
    (work / "README.md").write_text("staged user edit\n")
    git(work, "add", "README.md")
    (work / "README.md").write_text("unstaged user edit\n")
    code_head = git(work, "rev-parse", "HEAD").stdout
    staged = git(work, "diff", "--cached").stdout
    checkout = (work / "README.md").read_bytes()
    index_path = work / git(work, "rev-parse", "--git-path", "index").stdout.strip()
    index = index_path.read_bytes()

    first = publisher.publish_images(directory, repository=work)
    assert first["retained"] == 5
    assert snapshot_files(origin) == {
        *(f"2026-10-{day}.png" for day in [20, 21, 22, 23, 24]), "latest.png", "latest.json",
    }
    assert git(origin, "show", f"{publisher.IMAGE_REF}:latest.png").stdout == "image-24"
    assert git(origin, "rev-list", "--count", publisher.IMAGE_REF).stdout.strip() == "1"

    # A normal later run only has today's input; prior images come from origin.
    for path in directory.glob("2026-10-*.png"):
        path.unlink()
    inputs(directory, [25, 26])
    second = publisher.publish_images(directory, repository=work)
    assert second["commit"] != first["commit"]
    assert snapshot_files(origin) == {
        *(f"2026-10-{day}.png" for day in [22, 23, 24, 25, 26]), "latest.png", "latest.json",
    }
    assert git(origin, "show", f"{publisher.IMAGE_REF}:latest.png").stdout == "image-26"
    assert json.loads(git(origin, "show", f"{publisher.IMAGE_REF}:latest.json").stdout) == {"date": "2026-10-26"}
    assert git(origin, "rev-list", "--parents", publisher.IMAGE_REF).stdout.strip() == second["commit"]
    assert git(work, "rev-parse", "HEAD").stdout == code_head
    assert git(origin, "rev-parse", "refs/heads/main").stdout == code_head
    assert git(work, "diff", "--cached").stdout == staged
    assert index_path.read_bytes() == index
    assert (work / "README.md").read_bytes() == checkout
    assert (directory / "notes.txt").read_text() == "local notes"
    assert external.read_bytes() == b"private image"


def test_same_day_correction_replaces_image_without_keeping_history(repository) -> None:
    work, origin = repository
    directory = work / "generated"
    inputs(directory, [23, 24])
    publisher.publish_images(directory, repository=work)
    (directory / "2026-10-24.png").write_bytes(b"corrected up image")
    publisher.publish_images(directory, repository=work)
    assert git(origin, "show", f"{publisher.IMAGE_REF}:2026-10-24.png").stdout == "corrected up image"
    assert git(origin, "show", f"{publisher.IMAGE_REF}:latest.png").stdout == "corrected up image"
    assert git(origin, "rev-list", "--count", publisher.IMAGE_REF).stdout.strip() == "1"


def test_lease_rejects_concurrent_remote_snapshot(repository, monkeypatch) -> None:
    work, origin = repository
    directory = work / "generated"
    inputs(directory, [24])
    first = publisher.publish_images(directory, repository=work)
    inputs(directory, [25])
    original_git = publisher._git
    concurrent = ""

    def raced_git(repository, *arguments, **options):
        nonlocal concurrent
        if arguments[0] == "push":
            tree = git(origin, "rev-parse", f"{first['commit']}^{{tree}}").stdout.strip()
            concurrent = git(origin, "commit-tree", tree, "-m", "Concurrent publisher").stdout.strip()
            git(origin, "update-ref", publisher.IMAGE_REF, concurrent)
        return original_git(repository, *arguments, **options)

    monkeypatch.setattr(publisher, "_git", raced_git)
    with pytest.raises(subprocess.CalledProcessError) as error:
        publisher.publish_images(directory, repository=work)
    assert "stale info" in error.value.stderr
    assert git(origin, "rev-parse", publisher.IMAGE_REF).stdout.strip() == concurrent


def test_remote_failure_does_not_create_or_replace_branch(repository) -> None:
    work, origin = repository
    directory = work / "generated"
    inputs(directory, [24])
    git(work, "remote", "set-url", "origin", str(origin / "missing"))
    with pytest.raises(subprocess.CalledProcessError):
        publisher.publish_images(directory, repository=work)
    assert git(origin, "show-ref", "--verify", publisher.IMAGE_REF, check=False).returncode != 0


@pytest.mark.parametrize("keep", [0, -1])
def test_rejects_invalid_keep_before_any_git_calls(tmp_path, monkeypatch, keep) -> None:
    def unexpected_git(*args, **kwargs):
        pytest.fail("invalid retention must not invoke git")

    monkeypatch.setattr(publisher, "_git", unexpected_git)
    with pytest.raises(ValueError, match="at least 1"):
        publisher.publish_images(tmp_path, keep)


@pytest.mark.parametrize("value", ["2026-02-30", "../../private", None])
def test_rejects_unsafe_or_invalid_metadata_date(tmp_path, value) -> None:
    (tmp_path / "latest.json").write_text(json.dumps({"date": value}))
    with pytest.raises(ValueError, match="valid ISO date"):
        publisher.publish_images(tmp_path)
