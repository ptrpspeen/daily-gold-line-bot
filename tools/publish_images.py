from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import tempfile
from datetime import date
from pathlib import Path


IMAGE_BRANCH = "gold-price-images"
IMAGE_REF = f"refs/heads/{IMAGE_BRANCH}"


def _dated_image(name: str) -> bool:
    if not re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}\.png", name):
        return False
    try:
        date.fromisoformat(name[:-4])
        return True
    except ValueError:
        return False


def _git(repository: Path, *arguments: str, **options) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", *arguments], cwd=repository, capture_output=True, check=True,
        text=options.pop("text", True), **options,
    )


def publish_images(
    directory: Path, keep: int = 5, *, repository: Path | None = None,
) -> dict[str, str | int]:
    if keep < 1:
        raise ValueError("keep must be at least 1")
    repository = repository or Path.cwd()
    directory = directory.resolve()
    metadata_path = directory / "latest.json"
    if metadata_path.is_symlink():
        raise ValueError("latest.json must be a regular file")
    metadata = metadata_path.read_bytes()
    latest_date = json.loads(metadata)["date"]
    latest_name = f"{latest_date}.png"
    if not _dated_image(latest_name):
        raise ValueError("latest.json must contain a valid ISO date")
    local = {
        path.name: path for path in directory.iterdir()
        if _dated_image(path.name) and path.is_file() and not path.is_symlink()
    }
    if latest_name not in local:
        raise ValueError(f"missing local image for latest.json: {latest_name}")

    # Only exit 2 means the dedicated branch is absent. Authentication and
    # network failures must stop publication, rather than recreate the branch.
    try:
        _git(repository, "ls-remote", "--exit-code", "origin", IMAGE_REF)
    except subprocess.CalledProcessError as exc:
        if exc.returncode != 2:
            raise
        previous = ""
    else:
        _git(repository, "fetch", "--no-tags", "origin", IMAGE_REF)
        previous = _git(repository, "rev-parse", "FETCH_HEAD").stdout.strip()

    remote: set[str] = set()
    if previous:
        tree = _git(repository, "ls-tree", "-z", previous).stdout
        for entry in tree.split("\0"):
            if not entry:
                continue
            properties, name = entry.split("\t", 1)
            mode, kind, _ = properties.split()
            if kind == "blob" and mode in {"100644", "100755"} and _dated_image(name):
                remote.add(name)
    retained = sorted(remote | local.keys(), reverse=True)[:keep]
    if latest_name not in retained:
        raise ValueError("latest.json date is older than the retained image window")

    with tempfile.TemporaryDirectory(prefix="gold-price-publish-") as temporary:
        temporary_path = Path(temporary)
        snapshot = temporary_path / "snapshot"
        snapshot.mkdir()
        for name in retained:
            content = local[name].read_bytes() if name in local else _git(
                repository, "show", f"{previous}:{name}", text=False,
            ).stdout
            (snapshot / name).write_bytes(content)
        (snapshot / "latest.png").write_bytes((snapshot / latest_name).read_bytes())
        (snapshot / "latest.json").write_bytes(metadata)
        environment = os.environ.copy()
        environment.update({
            "GIT_INDEX_FILE": str(temporary_path / "index"),
            "GIT_AUTHOR_NAME": "github-actions[bot]",
            "GIT_AUTHOR_EMAIL": "41898282+github-actions[bot]@users.noreply.github.com",
            "GIT_COMMITTER_NAME": "github-actions[bot]",
            "GIT_COMMITTER_EMAIL": "41898282+github-actions[bot]@users.noreply.github.com",
        })
        _git(repository, "read-tree", "--empty", env=environment)
        _git(repository, "--work-tree", str(snapshot), "add", "--force", "--all", "--", ".", env=environment)
        tree = _git(repository, "write-tree", env=environment).stdout.strip()
        # No parent: replacing this dedicated branch keeps reachable history
        # bounded to one snapshot, including when old images are pruned.
        commit = _git(
            repository, "commit-tree", tree, "-m", f"Gold price images {latest_date}",
            env=environment,
        ).stdout.strip()
        _git(
            repository, "push", f"--force-with-lease={IMAGE_REF}:{previous}",
            "origin", f"{commit}:{IMAGE_REF}",
        )
    return {
        "branch": IMAGE_BRANCH, "commit": commit, "date": latest_date,
        "image": latest_name, "retained": len(retained),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Publish a bounded gold-price image snapshot.")
    parser.add_argument("--directory", type=Path, default=Path("generated"))
    parser.add_argument("--keep", type=int, default=5)
    parser.add_argument("--repo", help="owner/name, used to print the public raw image URL")
    args = parser.parse_args()
    if args.keep < 1:
        parser.error("--keep must be at least 1")
    result = publish_images(args.directory, args.keep)
    if args.repo:
        result["image_url"] = (
            f"https://raw.githubusercontent.com/{args.repo}/{IMAGE_BRANCH}/{result['image']}"
        )
    print(json.dumps(result))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
