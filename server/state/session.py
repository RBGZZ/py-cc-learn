from __future__ import annotations

import asyncio
import json
import os
import time
import uuid
from pathlib import Path
from typing import Any

VERSION = "0.1.0"

MAX_TRANSCRIPT_READ_BYTES = 50 * 1024 * 1024
MAX_TOMBSTONE_REWRITE_BYTES = 50 * 1024 * 1024
SESSION_AUTO_CLEAN_DAYS = 30
SESSION_FLUSH_INTERVAL_MS = 100

SKIP_FIRST_PROMPT_PATTERN_STR = r"^(?:\s*<[a-z][\w-]*[\s>]|\[Request interrupted by user[^\]]*\])"

EPHEMERAL_PROGRESS_TYPES = frozenset(
    {
        "bash_progress",
        "powershell_progress",
        "mcp_progress",
    }
)


class SessionStamp:
    def __init__(
        self,
        session_id: str = "",
        user_type: str = "external",
        entrypoint: str = "cli",
        cwd: str = "",
        version: str = VERSION,
        git_branch: str | None = None,
        slug: str | None = None,
    ) -> None:
        self.session_id = session_id
        self.user_type = user_type
        self.entrypoint = entrypoint
        self.cwd = cwd
        self.version = version
        self.git_branch = git_branch
        self.slug = slug

    def to_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {
            "sessionId": self.session_id,
            "userType": self.user_type,
            "entrypoint": self.entrypoint,
            "cwd": self.cwd,
            "version": self.version,
        }
        if self.git_branch is not None:
            result["gitBranch"] = self.git_branch
        if self.slug is not None:
            result["slug"] = self.slug
        return result


class SessionEntry:
    def __init__(
        self,
        type: str,
        uuid: str = "",
        parent_uuid: str | None = None,
        logical_parent_uuid: str | None = None,
        is_sidechain: bool = False,
        team_name: str | None = None,
        agent_name: str | None = None,
        prompt_id: str | None = None,
        agent_id: str | None = None,
        message: dict[str, Any] | None = None,
        session_stamp: SessionStamp | None = None,
        timestamp: str | None = None,
    ) -> None:
        self.type = type
        self.uuid = uuid or str(uuid.uuid4())
        self.parent_uuid = parent_uuid
        self.logical_parent_uuid = logical_parent_uuid
        self.is_sidechain = is_sidechain
        self.team_name = team_name
        self.agent_name = agent_name
        self.prompt_id = prompt_id
        self.agent_id = agent_id
        self.message = message or {}
        self.session_stamp = session_stamp or SessionStamp()
        self.timestamp = timestamp or time.strftime("%Y-%m-%dT%H:%M:%S.000Z", time.gmtime())

    def to_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {
            "type": self.type,
            "uuid": self.uuid,
            "parentUuid": self.parent_uuid,
            "timestamp": self.timestamp,
        }
        if self.logical_parent_uuid is not None:
            result["logicalParentUuid"] = self.logical_parent_uuid
        if self.is_sidechain:
            result["isSidechain"] = self.is_sidechain
        if self.team_name:
            result["teamName"] = self.team_name
        if self.agent_name:
            result["agentName"] = self.agent_name
        if self.prompt_id:
            result["promptId"] = self.prompt_id
        if self.agent_id:
            result["agentId"] = self.agent_id

        result.update(self.session_stamp.to_dict())

        if self.message:
            result.update(self.message)

        return result

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> SessionEntry:
        stamp = SessionStamp(
            session_id=data.get("sessionId", ""),
            user_type=data.get("userType", "external"),
            entrypoint=data.get("entrypoint", "cli"),
            cwd=data.get("cwd", ""),
            version=data.get("version", VERSION),
            git_branch=data.get("gitBranch"),
            slug=data.get("slug"),
        )

        msg_keys = {
            "type",
            "uuid",
            "parentUuid",
            "logicalParentUuid",
            "isSidechain",
            "teamName",
            "agentName",
            "promptId",
            "agentId",
            "timestamp",
            "sessionId",
            "userType",
            "entrypoint",
            "cwd",
            "version",
            "gitBranch",
            "slug",
        }

        message = {k: v for k, v in data.items() if k not in msg_keys}

        return cls(
            type=data.get("type", ""),
            uuid=data.get("uuid", ""),
            parent_uuid=data.get("parentUuid"),
            logical_parent_uuid=data.get("logicalParentUuid"),
            is_sidechain=data.get("isSidechain", False),
            team_name=data.get("teamName"),
            agent_name=data.get("agentName"),
            prompt_id=data.get("promptId"),
            agent_id=data.get("agentId"),
            message=message,
            session_stamp=stamp,
            timestamp=data.get("timestamp"),
        )


def _get_config_dir() -> Path:
    if os.name == "nt":
        base = os.environ.get("APPDATA", os.path.expanduser("~"))
        return Path(base) / "Claude"
    return Path.home() / ".claude"


def get_projects_dir() -> Path:
    return _get_config_dir() / "projects"


def get_project_dir(cwd: str | Path) -> Path:
    import hashlib

    project_hash = hashlib.sha256(str(cwd).encode()).hexdigest()[:16]
    return get_projects_dir() / project_hash


class SessionStorage:
    def __init__(
        self,
        session_id: str | None = None,
        project_dir: str | Path | None = None,
        cwd: str | Path | None = None,
        disabled: bool = False,
    ) -> None:
        self._session_id = session_id or str(uuid.uuid4())
        self._disabled = disabled
        self._cwd = str(cwd or os.getcwd())
        self._project_dir = Path(project_dir) if project_dir else get_project_dir(self._cwd)
        self._session_file: Path | None = None
        self._pending_entries: list[dict[str, Any]] = []
        self._flush_lock = asyncio.Lock()
        self._flush_task: asyncio.Task | None = None
        self._closed = False
        self._git_branch: str | None = None
        self._slug: str | None = None
        self._last_prompt: str | None = None
        self._entry_count = 0

    @property
    def session_id(self) -> str:
        return self._session_id

    @property
    def transcript_path(self) -> Path:
        return self._project_dir / f"{self._session_id}.jsonl"

    @property
    def is_disabled(self) -> bool:
        return self._disabled

    def get_agent_transcript_path(self, agent_id: str) -> Path:
        return self._project_dir / self._session_id / "subagents" / f"agent-{agent_id}.jsonl"

    def get_agent_metadata_path(self, agent_id: str) -> Path:
        p = self.get_agent_transcript_path(agent_id)
        return p.with_name(p.name.replace("agent-", "agent-meta-").replace(".jsonl", ".json"))

    def _ensure_session_file(self) -> None:
        if self._session_file is None and not self._disabled:
            self._project_dir.mkdir(parents=True, exist_ok=True)
            self._session_file = self.transcript_path

    async def start(self) -> None:
        self._ensure_session_file()
        self._flush_task = asyncio.create_task(self._flush_loop())

    async def close(self) -> None:
        self._closed = True
        if self._flush_task:
            self._flush_task.cancel()
            try:
                await self._flush_task
            except asyncio.CancelledError:
                pass
        await self._flush_pending()

    async def _flush_loop(self) -> None:
        while not self._closed:
            try:
                await asyncio.sleep(SESSION_FLUSH_INTERVAL_MS / 1000)
                await self._flush_pending()
            except asyncio.CancelledError:
                await self._flush_pending()
                raise

    async def _flush_pending(self) -> None:
        if self._disabled or not self._pending_entries:
            return
        async with self._flush_lock:
            if not self._pending_entries:
                return
            entries = self._pending_entries
            self._pending_entries = []
            await self._append_entries_to_file(entries)

    async def _append_entries_to_file(self, entries: list[dict[str, Any]]) -> None:
        if not self._session_file:
            return
        try:
            loop = asyncio.get_running_loop()
            with open(self._session_file, "a", encoding="utf-8") as f:
                for entry in entries:
                    line = json.dumps(entry, ensure_ascii=False, separators=(",", ":"))
                    f.write(line + "\n")
        except OSError as e:
            try:
                from server.utils.log import log_error

                log_error(e)
            except ImportError:
                pass

    def _queue_entry(self, entry: dict[str, Any]) -> None:
        if self._disabled:
            return
        self._pending_entries.append(entry)

    def _build_session_stamp(self) -> SessionStamp:
        from server.state.global_state import GlobalState

        gs = GlobalState.get_instance()
        return SessionStamp(
            session_id=gs.get_session_id() or self._session_id,
            user_type="external",
            entrypoint="cli",
            cwd=gs.get_cwd_state() or str(self._cwd),
            version=VERSION,
            git_branch=self._git_branch,
            slug=self._slug,
        )

    async def insert_message_chain(
        self,
        messages: list[dict[str, Any]],
        is_sidechain: bool = False,
        agent_id: str | None = None,
        starting_parent_uuid: str | None = None,
        team_name: str | None = None,
        agent_name: str | None = None,
    ) -> list[str]:
        if self._disabled:
            return []

        self._ensure_session_file()
        parent_uuid: str | None = starting_parent_uuid
        stamp = self._build_session_stamp()
        uuids: list[str] = []

        for msg in messages:
            msg_type = msg.get("type", "")
            msg_uuid = msg.get("uuid", str(uuid.uuid4()))
            is_compact_boundary = msg.get("subtype") == "compact_boundary"

            effective_parent_uuid = parent_uuid
            if msg_type == "user" and msg.get("sourceToolAssistantUUID"):
                effective_parent_uuid = msg["sourceToolAssistantUUID"]

            entry = {
                "parentUuid": None if is_compact_boundary else effective_parent_uuid,
                "isSidechain": is_sidechain,
                "teamName": team_name,
                "agentName": agent_name,
                "promptId": str(uuid.uuid4()) if msg_type == "user" else None,
                "agentId": agent_id,
                "type": msg_type,
                "uuid": msg_uuid,
                "userType": stamp.user_type,
                "entrypoint": stamp.entrypoint,
                "cwd": stamp.cwd,
                "sessionId": stamp.session_id,
                "version": stamp.version,
                "gitBranch": stamp.git_branch,
                "slug": stamp.slug,
            }

            if is_compact_boundary and parent_uuid is not None:
                entry["logicalParentUuid"] = parent_uuid

            msg_content = msg.get("message", msg.get("content"))
            if msg_content:
                if isinstance(msg_content, dict):
                    entry.update(msg_content)
                else:
                    entry["content"] = msg_content

            entry["timestamp"] = msg.get(
                "timestamp", time.strftime("%Y-%m-%dT%H:%M:%S.000Z", time.gmtime())
            )

            self._queue_entry(entry)
            uuids.append(msg_uuid)

            if is_chain_participant(msg_type):
                parent_uuid = msg_uuid

        if not is_sidechain:
            text = _get_first_meaningful_user_message(messages)
            if text:
                flat = text.replace("\n", " ").strip()
                self._last_prompt = flat[:200].strip() + "…" if len(flat) > 200 else flat

        return uuids

    async def load_transcript(self) -> list[SessionEntry]:
        path = self.transcript_path
        if not path.exists():
            return []

        try:
            file_size = os.path.getsize(path)
        except OSError:
            return []

        if file_size > MAX_TRANSCRIPT_READ_BYTES:
            entries = await self._load_transcript_tail(path)
        else:
            entries = await self._load_transcript_full(path)

        return entries

    async def _load_transcript_full(self, path: Path) -> list[SessionEntry]:
        entries: list[SessionEntry] = []
        loop = asyncio.get_running_loop()

        def _read():
            with open(path, encoding="utf-8") as f:
                return f.readlines()

        lines = await loop.run_in_executor(None, _read)
        for line in lines:
            line = line.strip()
            if not line:
                continue
            try:
                data = json.loads(line)
                entry = SessionEntry.from_dict(data)
                entries.append(entry)
            except json.JSONDecodeError:
                continue

        return entries

    async def _load_transcript_tail(self, path: Path) -> list[SessionEntry]:
        LITE_READ_BUF_SIZE = 8 * 1024

        loop = asyncio.get_running_loop()

        def _read_tail():
            with open(path, "rb") as f:
                f.seek(0, os.SEEK_END)
                file_size = f.tell()
                read_size = min(LITE_READ_BUF_SIZE, file_size)
                f.seek(file_size - read_size)
                return f.read().decode("utf-8", errors="replace")

        tail_data = await loop.run_in_executor(None, _read_tail)
        entries: list[SessionEntry] = []
        for line in tail_data.split("\n"):
            line = line.strip()
            if not line:
                continue
            try:
                data = json.loads(line)
                if data.get("type") in ("session", "user", "assistant"):
                    entries.append(SessionEntry.from_dict(data))
            except json.JSONDecodeError:
                continue

        return entries

    def build_conversation_chain(
        self, entries: list[SessionEntry], leaf_uuid: str | None = None
    ) -> list[SessionEntry]:
        if not entries:
            return []

        messages: dict[str, SessionEntry] = {}
        for entry in entries:
            if entry.uuid:
                messages[entry.uuid] = entry

        if leaf_uuid is None:
            leaf = entries[-1]
        elif leaf_uuid in messages:
            leaf = messages[leaf_uuid]
        else:
            return []

        chain: list[SessionEntry] = []
        seen: set[str] = set()
        current: SessionEntry | None = leaf

        while current is not None:
            if current.uuid in seen:
                break
            seen.add(current.uuid)
            chain.append(current)
            current = messages.get(current.parent_uuid) if current.parent_uuid else None

        chain.reverse()
        return chain

    async def write_agent_metadata(self, agent_id: str, metadata: dict[str, Any]) -> None:
        path = self.get_agent_metadata_path(agent_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(
            None,
            lambda: path.write_text(json.dumps(metadata), encoding="utf-8"),
        )

    async def read_agent_metadata(self, agent_id: str) -> dict[str, Any] | None:
        path = self.get_agent_metadata_path(agent_id)
        if not path.exists():
            return None
        loop = asyncio.get_running_loop()
        content = await loop.run_in_executor(None, lambda: path.read_text(encoding="utf-8"))
        return json.loads(content)

    @classmethod
    async def clean_old_sessions(
        cls,
        project_dir: Path | None = None,
        max_age_days: int = SESSION_AUTO_CLEAN_DAYS,
    ) -> int:
        if project_dir is None:
            project_dir = get_projects_dir()

        if not project_dir.exists():
            return 0

        removed = 0
        cutoff = time.time() - (max_age_days * 24 * 3600)

        loop = asyncio.get_running_loop()

        def _do_clean():
            nonlocal removed
            for root, dirs, files in os.walk(project_dir):
                for file in files:
                    if file.endswith(".jsonl"):
                        filepath = Path(root) / file
                        try:
                            mtime = filepath.stat().st_mtime
                            if mtime < cutoff:
                                filepath.unlink()
                                removed += 1
                        except OSError:
                            pass

        await loop.run_in_executor(None, _do_clean)
        return removed


def is_transcript_message(entry_type: str) -> bool:
    return entry_type in ("user", "assistant", "attachment", "system")


def is_chain_participant(msg_type: str) -> bool:
    return msg_type != "progress"


def _get_first_meaningful_user_message(
    messages: list[dict[str, Any]],
) -> str | None:
    import re

    for msg in messages:
        if msg.get("type") != "user":
            continue
        msg_data = msg.get("message", msg)
        content = msg_data.get("content", "")
        if isinstance(content, str):
            text = content
        elif isinstance(content, list):
            text_blocks = [b.get("text", "") for b in content if b.get("type") == "text"]
            text = "\n".join(text_blocks)
        else:
            continue

        if not text.strip():
            continue

        if re.match(SKIP_FIRST_PROMPT_PATTERN_STR, text):
            continue

        return text

    return None


async def cleanup_all_old_sessions(max_age_days: int = SESSION_AUTO_CLEAN_DAYS) -> int:
    return await SessionStorage.clean_old_sessions(
        project_dir=get_projects_dir(), max_age_days=max_age_days
    )
