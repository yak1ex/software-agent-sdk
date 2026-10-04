"""Bounded discovery of repository roots inside a workspace."""

import os
from pathlib import Path

from pydantic import BaseModel

from openhands.sdk.git.exceptions import GitRepositoryError
from openhands.sdk.git.utils import validate_git_repository


WORKSPACE_EXCLUDED_DIRS = frozenset(
    {
        ".git",
        "node_modules",
        ".venv",
        "venv",
        "__pycache__",
        "dist",
        "build",
        ".next",
        ".cache",
        ".pytest_cache",
        ".mypy_cache",
        ".turbo",
        ".parcel-cache",
        "target",
    }
)


class WorkspaceRepository(BaseModel):
    path: str


class WorkspaceRepositories(BaseModel):
    repositories: list[WorkspaceRepository]
    truncated: bool = False


def discover_repositories(
    workspace: Path, max_depth: int = 6, limit: int = 200
) -> WorkspaceRepositories:
    root = workspace.resolve()
    if not root.is_dir():
        raise GitRepositoryError(f"Not a directory: {root}")
    repositories: list[WorkspaceRepository] = []
    truncated = False
    visited = 0

    def on_error(error: OSError) -> None:
        raise GitRepositoryError(f"Cannot read directory: {error.filename}") from error

    for directory, dirs, _ in os.walk(root, followlinks=False, onerror=on_error):
        current = Path(directory)
        visited += 1
        if visited > 20000:
            truncated = True
            break
        dirs[:] = sorted(
            name
            for name in dirs
            if name not in WORKSPACE_EXCLUDED_DIRS
            and not (current / name).is_symlink()
            and not (current / name).is_junction()
        )
        relative = current.relative_to(root)
        if (current / ".git").exists():
            try:
                validate_git_repository(current)
            except GitRepositoryError:
                pass
            else:
                if len(repositories) == limit:
                    truncated = True
                    break
                repositories.append(WorkspaceRepository(path=relative.as_posix()))
        if len(relative.parts) >= max_depth:
            truncated = truncated or bool(dirs)
            dirs[:] = []
    return WorkspaceRepositories(
        repositories=sorted(repositories, key=lambda repo: repo.path),
        truncated=truncated,
    )
