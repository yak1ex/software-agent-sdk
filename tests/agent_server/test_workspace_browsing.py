import subprocess
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

from openhands.agent_server.file_router import file_router
from openhands.agent_server.git_router import git_router


def test_workspace_browsing(tmp_path: Path):
    app = FastAPI()
    app.include_router(file_router, prefix="/api")
    app.include_router(git_router, prefix="/api")
    client = TestClient(app)
    for name in ("repo-a", "group/repo-b"):
        repo = tmp_path / name
        repo.mkdir(parents=True)
        subprocess.run(["git", "init", str(repo)], check=True, capture_output=True)
        (repo / "hello world.txt").write_text(name)
    ignored = tmp_path / "node_modules" / "hidden"
    ignored.mkdir(parents=True)
    (ignored / "file.txt").write_text("ignored")

    response = client.get("/api/git/repositories", params={"path": str(tmp_path)})
    assert response.status_code == 200
    assert [repo["path"] for repo in response.json()["repositories"]] == [
        "group/repo-b",
        "repo-a",
    ]
    response = client.get("/api/file/list", params={"path": str(tmp_path), "limit": 1})
    assert response.status_code == 200
    assert response.json() == {
        "files": ["group/repo-b/hello world.txt"],
        "truncated": True,
    }
    response = client.get("/api/file/list", params={"path": str(tmp_path)})
    assert response.json() == {
        "files": ["group/repo-b/hello world.txt", "repo-a/hello world.txt"],
        "truncated": False,
    }


def test_discovery_accepts_worktrees(tmp_path: Path):
    repo = tmp_path / "repo"
    subprocess.run(["git", "init", str(repo)], check=True, capture_output=True)
    subprocess.run(
        [
            "git",
            "-C",
            str(repo),
            "-c",
            "user.name=Test",
            "-c",
            "user.email=test@example.com",
            "commit",
            "--allow-empty",
            "-m",
            "initial",
        ],
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "-C", str(repo), "worktree", "add", "--detach", str(tmp_path / "tree")],
        check=True,
        capture_output=True,
    )
    app = FastAPI()
    app.include_router(git_router, prefix="/api")
    response = TestClient(app).get(
        "/api/git/repositories", params={"path": str(tmp_path)}
    )
    assert [repo["path"] for repo in response.json()["repositories"]] == [
        "repo",
        "tree",
    ]


def test_repository_scoped_changes_and_commit_diff(tmp_path: Path):
    app = FastAPI()
    app.include_router(git_router, prefix="/api")
    client = TestClient(app)
    repo = tmp_path / "repo"
    nested = repo / "nested"
    for directory in (repo, nested):
        subprocess.run(["git", "init", str(directory)], check=True, capture_output=True)
        (directory / "file.txt").write_text(directory.name)
        subprocess.run(["git", "-C", str(directory), "add", "file.txt"], check=True)
        subprocess.run(
            [
                "git",
                "-C",
                str(directory),
                "-c",
                "user.name=Test",
                "-c",
                "user.email=test@example.com",
                "commit",
                "-m",
                directory.name,
            ],
            check=True,
            capture_output=True,
        )
        (directory / "file.txt").write_text("modified")
    response = client.get(
        "/api/git/changes",
        params={"path": str(repo), "include_nested": False, "ref": "HEAD"},
    )
    assert response.json() == [{"path": "file.txt", "status": "UPDATED"}]
    # The ordinary aggregate API must also work when the workspace is not Git.
    response = client.get(
        "/api/git/changes", params={"path": str(tmp_path), "ref": "HEAD"}
    )
    assert any(
        Path(change["path"]) == Path("repo/file.txt") for change in response.json()
    )
    commits = client.get("/api/git/commits", params={"path": str(nested)}).json()
    sha = commits["commits"][0]["sha"]
    assert commits["commits"][0]["subject"] == "nested"
    response = client.get(
        "/api/git/diff",
        params={
            "path": str(nested / "file.txt"),
            "repository": str(nested),
            "commit": sha,
        },
    )
    assert response.status_code == 200
    assert response.json()["modified"] == "nested"
    response = client.get(
        "/api/git/diff",
        params={
            "path": str(repo / "file.txt"),
            "repository": str(nested),
            "commit": sha,
        },
    )
    assert response.status_code == 400
