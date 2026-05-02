from __future__ import annotations

import asyncio
import hashlib
import os
import re
from dataclasses import dataclass, field
from datetime import UTC
from functools import lru_cache
from pathlib import Path
from typing import Any

_GIT_ROOT_NOT_FOUND = object()

_GIT_ROOT_CACHE_SIZE = 50


@lru_cache(maxsize=_GIT_ROOT_CACHE_SIZE)
def _find_git_root_impl(start_path: str) -> str | object:
    current = Path(start_path).resolve()
    root = Path(current.anchor) if current.anchor else current

    while True:
        git_path = current / ".git"
        try:
            if git_path.is_dir() or git_path.is_file():
                return str(current)
        except OSError:
            pass

        parent = current.parent
        if parent == current:
            break
        current = parent

    try:
        git_path = root / ".git"
        if git_path.is_dir() or git_path.is_file():
            return str(root)
    except OSError:
        pass

    return _GIT_ROOT_NOT_FOUND


def find_git_root(start_path: str | None = None) -> str | None:
    if start_path is None:
        start_path = os.getcwd()
    result = _find_git_root_impl(start_path)
    if result is _GIT_ROOT_NOT_FOUND:
        return None
    return str(result)


def clear_git_root_cache() -> None:
    _find_git_root_impl.cache_clear()


async def _run_git(
    args: list[str], cwd: str | None = None, check: bool = False
) -> tuple[int, str, str]:
    try:
        proc = await asyncio.create_subprocess_exec(
            "git",
            *args,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=cwd,
        )
        stdout, stderr = await proc.communicate()
        code = proc.returncode or 0

        stdout_str = stdout.decode("utf-8", errors="replace") if stdout else ""
        stderr_str = stderr.decode("utf-8", errors="replace") if stderr else ""

        if check and code != 0:
            raise RuntimeError(f"git {' '.join(args)} failed with code {code}: {stderr_str}")

        return code, stdout_str, stderr_str
    except FileNotFoundError:
        return 1, "", "git not found"


async def _run_git_lines(args: list[str], cwd: str | None = None) -> list[str]:
    code, stdout, _stderr = await _run_git(args, cwd=cwd)
    if code != 0:
        return []
    return [line for line in stdout.strip().split("\n") if line]


async def _run_git_first_line(args: list[str], cwd: str | None = None) -> str | None:
    lines = await _run_git_lines(args, cwd=cwd)
    return lines[0] if lines else None


async def get_is_git(cwd: str | None = None) -> bool:
    if cwd is None:
        cwd = os.getcwd()
    return find_git_root(cwd) is not None


async def get_git_root(cwd: str | None = None) -> str | None:
    if cwd is None:
        cwd = os.getcwd()
    return find_git_root(cwd)


async def get_head(cwd: str | None = None) -> str:
    git_root = await get_git_root(cwd)
    if git_root is None:
        return ""
    head_path = Path(git_root) / ".git" / "HEAD"
    try:
        content = head_path.read_text(encoding="utf-8").strip()
        if content.startswith("ref:"):
            ref = content[4:].strip()
            ref_path = Path(git_root) / ".git" / ref
            if ref_path.exists():
                return ref_path.read_text(encoding="utf-8").strip()
            packed_refs = Path(git_root) / ".git" / "packed-refs"
            if packed_refs.exists():
                for line in packed_refs.read_text(encoding="utf-8").split("\n"):
                    line = line.strip()
                    if line and not line.startswith("#") and not line.startswith("^"):
                        parts = line.split(" ", 1)
                        if len(parts) == 2 and parts[1] == ref:
                            return parts[0]
        return content
    except OSError:
        pass
    code, stdout, _stderr = await _run_git(["rev-parse", "HEAD"], cwd=git_root)
    if code == 0:
        return stdout.strip()
    return ""


async def get_branch(cwd: str | None = None) -> str:
    git_root = await get_git_root(cwd)
    if git_root is None:
        return ""
    head_path = Path(git_root) / ".git" / "HEAD"
    try:
        content = head_path.read_text(encoding="utf-8").strip()
        if content.startswith("ref: refs/heads/"):
            return content[16:]
    except OSError:
        pass
    code, stdout, _stderr = await _run_git(["rev-parse", "--abbrev-ref", "HEAD"], cwd=git_root)
    if code == 0:
        result = stdout.strip()
        if result and result != "HEAD":
            return result
    return ""


async def get_default_branch(cwd: str | None = None) -> str:
    git_root = await get_git_root(cwd)
    if git_root is None:
        return ""
    code, stdout, _stderr = await _run_git(["remote", "show", "origin", "--", "HEAD"], cwd=git_root)
    if code == 0:
        match = re.search(r"HEAD branch:\s+(\S+)", stdout)
        if match:
            return match.group(1)
    for candidate in ["origin/main", "origin/master", "origin/staging"]:
        code, _stdout, _stderr = await _run_git(["rev-parse", "--verify", candidate], cwd=git_root)
        if code == 0:
            return candidate.split("/", 1)[1]
    return "main"


async def get_remote_url(remote_name: str = "origin", cwd: str | None = None) -> str | None:
    git_root = await get_git_root(cwd)
    if git_root is None:
        return None
    config_path = Path(git_root) / ".git" / "config"
    try:
        content = config_path.read_text(encoding="utf-8")
        in_remote_section = False
        in_correct_remote = False
        for line in content.split("\n"):
            line = line.strip()
            if line.startswith("[remote "):
                in_remote_section = True
                in_correct_remote = f'"{remote_name}"' in line
            elif line.startswith("["):
                in_remote_section = False
                in_correct_remote = False
            elif in_correct_remote and line.startswith("url "):
                return line.split("=", 1)[1].strip()
    except OSError:
        pass
    code, stdout, _stderr = await _run_git(["remote", "get-url", remote_name], cwd=git_root)
    if code == 0:
        return stdout.strip()
    return None


def normalize_git_remote_url(url: str) -> str | None:
    trimmed = url.strip()
    if not trimmed:
        return None

    ssh_match = re.match(r"^git@([^:]+):(.+?)(?:\.git)?$", trimmed)
    if ssh_match:
        return f"{ssh_match.group(1)}/{ssh_match.group(2)}".lower()

    url_match = re.match(r"^(?:https?|ssh):\/\/(?:[^@]+@)?([^/]+)\/(.+?)(?:\.git)?$", trimmed)
    if url_match:
        host = url_match.group(1)
        path = url_match.group(2)

        if _is_localhost(host) and path.startswith("git/"):
            proxy_path = path[4:]
            segments = proxy_path.split("/")
            if len(segments) >= 3 and "." in segments[0]:
                return proxy_path.lower()
            return f"github.com/{proxy_path}".lower()

        return f"{host}/{path}".lower()

    return None


def _is_localhost(host: str) -> bool:
    host_without_port = host.split(":")[0]
    return host_without_port == "localhost" or bool(
        re.match(r"^127\.\d{1,3}\.\d{1,3}\.\d{1,3}$", host_without_port)
    )


async def get_repo_remote_hash(cwd: str | None = None) -> str | None:
    remote_url = await get_remote_url(cwd=cwd)
    if not remote_url:
        return None
    normalized = normalize_git_remote_url(remote_url)
    if not normalized:
        return None
    return hashlib.sha256(normalized.encode()).hexdigest()[:16]


async def get_is_head_on_remote(cwd: str | None = None) -> bool:
    git_root = await get_git_root(cwd)
    if git_root is None:
        return False
    code, _stdout, _stderr = await _run_git(["rev-parse", "@{u}"], cwd=git_root)
    return code == 0


async def has_unpushed_commits(cwd: str | None = None) -> bool:
    git_root = await get_git_root(cwd)
    if git_root is None:
        return False
    code, stdout, _stderr = await _run_git(["rev-list", "--count", "@{u}..HEAD"], cwd=git_root)
    if code == 0:
        try:
            return int(stdout.strip()) > 0
        except ValueError:
            pass
    return False


async def get_is_clean(ignore_untracked: bool = False, cwd: str | None = None) -> bool:
    git_root = await get_git_root(cwd)
    if git_root is None:
        return True
    args = ["--no-optional-locks", "status", "--porcelain"]
    if ignore_untracked:
        args.append("-uno")
    code, stdout, _stderr = await _run_git(args, cwd=git_root)
    return stdout.strip() == ""


async def get_changed_files(cwd: str | None = None) -> list[str]:
    git_root = await get_git_root(cwd)
    if git_root is None:
        return []
    code, stdout, _stderr = await _run_git(
        ["--no-optional-locks", "status", "--porcelain"], cwd=git_root
    )
    if code != 0:
        return []
    result: list[str] = []
    for line in stdout.strip().split("\n"):
        if not line.strip():
            continue
        parts = line.strip().split(" ", 1)
        if len(parts) > 1 and parts[1].strip():
            result.append(parts[1].strip())
    return result


@dataclass
class GitFileStatus:
    tracked: list[str] = field(default_factory=list)
    untracked: list[str] = field(default_factory=list)


async def get_file_status(cwd: str | None = None) -> GitFileStatus:
    git_root = await get_git_root(cwd)
    if git_root is None:
        return GitFileStatus()
    code, stdout, _stderr = await _run_git(
        ["--no-optional-locks", "status", "--porcelain"], cwd=git_root
    )
    if code != 0:
        return GitFileStatus()

    tracked: list[str] = []
    untracked: list[str] = []

    for line in stdout.strip().split("\n"):
        if len(line) < 3:
            continue
        status = line[:2]
        filename = line[2:].strip()
        if status == "??":
            untracked.append(filename)
        elif filename:
            tracked.append(filename)

    return GitFileStatus(tracked=tracked, untracked=untracked)


async def git_diff(
    staged: bool = False,
    target: str | None = None,
    paths: list[str] | None = None,
    cwd: str | None = None,
) -> str:
    git_root = await get_git_root(cwd)
    if git_root is None:
        return ""
    args = ["diff"]
    if staged:
        args.append("--staged")
    if target:
        args.append(target)
    args.append("--")
    if paths:
        args.extend(paths)
    code, stdout, _stderr = await _run_git(args, cwd=git_root)
    return stdout if code == 0 else ""


@dataclass
class GitRepoState:
    commit_hash: str
    branch_name: str
    remote_url: str | None
    is_head_on_remote: bool
    is_clean: bool
    worktree_count: int = 1


async def get_git_state(cwd: str | None = None) -> GitRepoState | None:
    try:
        commit_hash, branch_name, remote_url, is_head_on_remote, is_clean = await asyncio.gather(
            get_head(cwd=cwd),
            get_branch(cwd=cwd),
            get_remote_url(cwd=cwd),
            get_is_head_on_remote(cwd=cwd),
            get_is_clean(cwd=cwd),
        )

        return GitRepoState(
            commit_hash=commit_hash,
            branch_name=branch_name,
            remote_url=remote_url,
            is_head_on_remote=is_head_on_remote,
            is_clean=is_clean,
            worktree_count=1,
        )
    except Exception:
        return None


async def stash_to_clean_state(message: str | None = None, cwd: str | None = None) -> bool:
    git_root = await get_git_root(cwd)
    if git_root is None:
        return False

    stash_message = message or f"Claude Code auto-stash - {_now_iso()}"

    file_status = await get_file_status(cwd=git_root)
    if file_status.untracked:
        code, _stdout, _stderr = await _run_git(["add"] + file_status.untracked, cwd=git_root)
        if code != 0:
            return False

    code, _stdout, _stderr = await _run_git(
        ["stash", "push", "--message", stash_message], cwd=git_root
    )
    return code == 0


async def find_remote_base(cwd: str | None = None) -> str | None:
    git_root = await get_git_root(cwd)
    if git_root is None:
        return None

    code, stdout, _stderr = await _run_git(
        ["rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{u}"],
        cwd=git_root,
    )
    if code == 0 and stdout.strip():
        return stdout.strip()

    code, stdout, _stderr = await _run_git(["remote", "show", "origin", "--", "HEAD"], cwd=git_root)
    if code == 0:
        match = re.search(r"HEAD branch:\s+(\S+)", stdout)
        if match:
            return f"origin/{match.group(1)}"

    for candidate in ["origin/main", "origin/staging", "origin/master"]:
        code, _stdout, _stderr = await _run_git(["rev-parse", "--verify", candidate], cwd=git_root)
        if code == 0:
            return candidate

    return None


async def get_github_repo(cwd: str | None = None) -> str | None:
    remote_url = await get_remote_url(cwd=cwd)
    if not remote_url:
        return None

    parsed = _parse_git_remote(remote_url)
    if parsed and parsed.get("host") == "github.com":
        return f"{parsed['owner']}/{parsed['name']}"
    return None


def _parse_git_remote(url: str) -> dict[str, str] | None:
    trimmed = url.strip()
    if not trimmed:
        return None

    ssh_match = re.match(r"^git@([^:]+):(.+?)(?:\.git)?$", trimmed)
    if ssh_match:
        host = ssh_match.group(1)
        path = ssh_match.group(2)
        parts = path.split("/")
        if len(parts) >= 2:
            return {"host": host, "owner": parts[0], "name": parts[-1]}

    url_match = re.match(r"^(?:https?|ssh):\/\/(?:[^@]+@)?([^/]+)\/(.+?)(?:\.git)?$", trimmed)
    if url_match:
        host = url_match.group(1)
        path = url_match.group(2)
        parts = path.split("/")
        if len(parts) >= 2:
            return {"host": host, "owner": parts[0], "name": parts[-1]}

    return None


def _now_iso() -> str:
    from datetime import datetime

    return datetime.now(UTC).isoformat()


async def is_at_git_root(cwd: str | None = None) -> bool:
    if cwd is None:
        cwd = os.getcwd()
    git_root = find_git_root(cwd)
    if git_root is None:
        return False
    try:
        return Path(cwd).resolve() == Path(git_root).resolve()
    except OSError:
        return cwd == git_root


async def dir_is_in_git_repo(cwd: str) -> bool:
    return find_git_root(cwd) is not None


async def get_git_diff_summary(cwd: str | None = None) -> str:
    git_root = await get_git_root(cwd)
    if git_root is None:
        return ""
    code, stdout, _stderr = await _run_git(["diff", "--stat"], cwd=git_root)
    return stdout if code == 0 else ""


async def get_git_diff_context(cwd: str | None = None) -> dict[str, Any]:
    git_root = await get_git_root(cwd)
    if git_root is None:
        return {
            "is_git": False,
            "branch": "",
            "remote_url": None,
            "is_clean": True,
            "changed_files": [],
            "diff_summary": "",
        }

    branch, remote_url, is_clean, changed_files, diff_summary = await asyncio.gather(
        get_branch(cwd=git_root),
        get_remote_url(cwd=git_root),
        get_is_clean(cwd=git_root),
        get_changed_files(cwd=git_root),
        get_git_diff_summary(cwd=git_root),
    )

    return {
        "is_git": True,
        "branch": branch,
        "remote_url": remote_url,
        "is_clean": is_clean,
        "changed_files": changed_files,
        "diff_summary": diff_summary,
    }


async def is_shallow_clone(cwd: str | None = None) -> bool:
    git_root = await get_git_root(cwd)
    if git_root is None:
        return False
    shallow_path = Path(git_root) / ".git" / "shallow"
    return shallow_path.exists()


async def get_recent_commits(count: int = 5, cwd: str | None = None) -> str:
    git_root = await get_git_root(cwd)
    if git_root is None:
        return ""
    code, stdout, _stderr = await _run_git(
        ["--no-optional-locks", "log", "--oneline", "-n", str(count)],
        cwd=git_root,
    )
    return stdout.strip() if code == 0 else ""


async def get_git_user_name(cwd: str | None = None) -> str:
    git_root = await get_git_root(cwd)
    if git_root is None:
        return ""
    code, stdout, _stderr = await _run_git(["config", "user.name"], cwd=git_root)
    return stdout.strip() if code == 0 else ""


async def get_git_status_short(cwd: str | None = None) -> str:
    git_root = await get_git_root(cwd)
    if git_root is None:
        return ""
    code, stdout, _stderr = await _run_git(
        ["--no-optional-locks", "status", "--short"], cwd=git_root
    )
    return stdout if code == 0 else ""


async def get_git_status_text(cwd: str | None = None) -> str | None:
    git_root = await get_git_root(cwd)
    if git_root is None:
        return None

    MAX_STATUS_CHARS = 2000

    try:
        branch, main_branch, status_short, recent_commits, user_name = await asyncio.gather(
            get_branch(cwd=git_root),
            get_default_branch(cwd=git_root),
            get_git_status_short(cwd=git_root),
            get_recent_commits(cwd=git_root),
            get_git_user_name(cwd=git_root),
        )

        status = status_short.strip()
        if len(status) > MAX_STATUS_CHARS:
            status = (
                status[:MAX_STATUS_CHARS]
                + "\n... (truncated because it exceeds 2k characters. "
                + 'If you need more information, run "git status" using BashTool)'
            )

        lines: list[str] = [
            "This is the git status at the start of the conversation. "
            "Note that this status is a snapshot in time, and will not update during the conversation.",
            f"Current branch: {branch}",
            f"Main branch (you will usually use this for PRs): {main_branch}",
        ]
        if user_name:
            lines.append(f"Git user: {user_name}")
        lines.append(f"Status:\n{status or '(clean)'}")
        lines.append(f"Recent commits:\n{recent_commits}")

        return "\n\n".join(lines)
    except Exception:
        return None
