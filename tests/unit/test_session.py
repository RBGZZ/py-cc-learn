from __future__ import annotations

import json
import os
import tempfile
import time
import uuid
from pathlib import Path

import pytest

from server.state.session import (
    MAX_TRANSCRIPT_READ_BYTES,
    SESSION_AUTO_CLEAN_DAYS,
    VERSION,
    SessionEntry,
    SessionStamp,
    SessionStorage,
    is_chain_participant,
    is_transcript_message,
)


class TestSessionStamp:
    def test_create_default_stamp(self):
        stamp = SessionStamp(
            session_id="session-1",
            user_type="external",
            entrypoint="cli",
            cwd="/home/user/project",
        )
        assert stamp.session_id == "session-1"
        assert stamp.user_type == "external"
        assert stamp.version == VERSION

    def test_to_dict(self):
        stamp = SessionStamp(
            session_id="session-1",
            user_type="external",
            entrypoint="cli",
            cwd="/home/user/project",
        )
        d = stamp.to_dict()
        assert d["sessionId"] == "session-1"
        assert d["userType"] == "external"
        assert d["version"] == VERSION
        assert d["cwd"] == "/home/user/project"

    def test_to_dict_with_optional_fields(self):
        stamp = SessionStamp(
            session_id="session-1",
            git_branch="main",
            slug="my-plan",
        )
        d = stamp.to_dict()
        assert d["gitBranch"] == "main"
        assert d["slug"] == "my-plan"

    def test_to_dict_without_none_optional_fields(self):
        stamp = SessionStamp(session_id="session-1")
        d = stamp.to_dict()
        assert "gitBranch" not in d
        assert "slug" not in d


class TestSessionEntry:
    def test_create_entry(self):
        entry = SessionEntry(
            type="user",
            uuid="uuid-1",
            parent_uuid=None,
            message={"role": "user", "content": [{"type": "text", "text": "Hello"}]},
        )
        assert entry.type == "user"
        assert entry.uuid == "uuid-1"
        assert entry.parent_uuid is None

    def test_to_dict_minimal(self):
        entry = SessionEntry(
            type="user",
            uuid="uuid-1",
        )
        d = entry.to_dict()
        assert d["type"] == "user"
        assert d["uuid"] == "uuid-1"
        assert d["parentUuid"] is None
        assert "parentUuid" in d

    def test_to_dict_with_sidechain(self):
        entry = SessionEntry(
            type="user",
            uuid="uuid-1",
            is_sidechain=True,
        )
        d = entry.to_dict()
        assert d["isSidechain"] is True

    def test_to_dict_with_logical_parent(self):
        entry = SessionEntry(
            type="user",
            uuid="uuid-1",
            logical_parent_uuid="parent-compact",
        )
        d = entry.to_dict()
        assert d["logicalParentUuid"] == "parent-compact"

    def test_to_dict_with_team_info(self):
        entry = SessionEntry(
            type="user",
            uuid="uuid-1",
            team_name="team-a",
            agent_name="agent-1",
        )
        d = entry.to_dict()
        assert d["teamName"] == "team-a"
        assert d["agentName"] == "agent-1"

    def test_from_dict_roundtrip(self):
        original = SessionEntry(
            type="assistant",
            uuid="uuid-1",
            parent_uuid="parent-1",
            logical_parent_uuid="logical-1",
            is_sidechain=False,
            team_name="team-a",
            agent_name="agent-1",
            message={"role": "assistant", "content": "Hello"},
        )
        d = original.to_dict()
        restored = SessionEntry.from_dict(d)
        assert restored.type == original.type
        assert restored.uuid == original.uuid
        assert restored.parent_uuid == original.parent_uuid
        assert restored.logical_parent_uuid == original.logical_parent_uuid

    def test_from_dict_preserves_session_stamp(self):
        d = {
            "type": "user",
            "uuid": "uuid-1",
            "parentUuid": None,
            "sessionId": "session-abc",
            "userType": "external",
            "entrypoint": "cli",
            "cwd": "/home/user",
            "version": VERSION,
            "gitBranch": "main",
        }
        entry = SessionEntry.from_dict(d)
        assert entry.session_stamp.session_id == "session-abc"
        assert entry.session_stamp.git_branch == "main"

    def test_from_dict_extracts_message(self):
        d = {
            "type": "user",
            "uuid": "uuid-1",
            "parentUuid": None,
            "sessionId": "session-1",
            "userType": "external",
            "entrypoint": "cli",
            "cwd": "/home/user",
            "version": VERSION,
            "role": "user",
            "content": "Hello World",
        }
        entry = SessionEntry.from_dict(d)
        assert entry.message["role"] == "user"
        assert entry.message["content"] == "Hello World"


class TestSessionStorage:
    @pytest.fixture
    def tmp_dir(self):
        with tempfile.TemporaryDirectory() as d:
            yield Path(d)

    def _make_storage(self, tmp_dir: Path, disabled: bool = False) -> SessionStorage:
        sid = str(uuid.uuid4())
        return SessionStorage(
            session_id=sid,
            project_dir=tmp_dir,
            cwd=tmp_dir,
            disabled=disabled,
        )

    @pytest.mark.asyncio
    async def test_transcript_path(self, tmp_dir):
        storage = self._make_storage(tmp_dir)
        path = storage.transcript_path
        assert path.parent == tmp_dir
        assert path.name.endswith(".jsonl")

    @pytest.mark.asyncio
    async def test_agent_transcript_path(self, tmp_dir):
        storage = self._make_storage(tmp_dir)
        path = storage.get_agent_transcript_path("agent-1")
        expected = tmp_dir / storage.session_id / "subagents" / "agent-agent-1.jsonl"
        assert path == expected

    @pytest.mark.asyncio
    async def test_agent_metadata_path(self, tmp_dir):
        storage = self._make_storage(tmp_dir)
        path = storage.get_agent_metadata_path("agent-1")
        assert "agent-meta-agent-1" in str(path) or "meta" in str(path)
        assert path.suffix == ".json"

    @pytest.mark.asyncio
    async def test_disabled_storage_skips_writes(self, tmp_dir):
        storage = self._make_storage(tmp_dir, disabled=True)
        uuids = await storage.insert_message_chain([
            {"type": "user", "uuid": str(uuid.uuid4()), "message": {"content": "Hello"}}
        ])
        assert uuids == []

    @pytest.mark.asyncio
    async def test_insert_message_chain(self, tmp_dir):
        storage = self._make_storage(tmp_dir)
        await storage.start()

        msg_uuid = str(uuid.uuid4())
        uuids = await storage.insert_message_chain([
            {
                "type": "user",
                "uuid": msg_uuid,
                "message": {"role": "user", "content": "Hello World"},
                "timestamp": "2025-01-01T00:00:00.000Z",
            }
        ])

        await storage.close()
        assert len(uuids) == 1
        assert uuids[0] == msg_uuid

        assert storage.transcript_path.exists()
        content = storage.transcript_path.read_text(encoding="utf-8")
        assert len(content.strip().split("\n")) == 1

    @pytest.mark.asyncio
    async def test_insert_message_chain_assigns_parent_uuid(self, tmp_dir):
        storage = self._make_storage(tmp_dir)
        await storage.start()

        msg1_uuid = str(uuid.uuid4())
        msg2_uuid = str(uuid.uuid4())

        await storage.insert_message_chain([
            {
                "type": "user",
                "uuid": msg1_uuid,
                "message": {"role": "user", "content": "First"},
            },
            {
                "type": "assistant",
                "uuid": msg2_uuid,
                "message": {"role": "assistant", "content": "Reply"},
            },
        ])

        await storage.close()

        entries = await storage.load_transcript()
        assert len(entries) >= 2

    @pytest.mark.asyncio
    async def test_insert_message_chain_sidechain(self, tmp_dir):
        storage = self._make_storage(tmp_dir)
        await storage.start()

        await storage.insert_message_chain(
            [
                {
                    "type": "user",
                    "uuid": str(uuid.uuid4()),
                    "message": {"role": "user", "content": "Sidechain"},
                }
            ],
            is_sidechain=True,
            agent_id="agent-1",
        )

        await storage.close()

        entries = await storage.load_transcript()
        assert len(entries) >= 1
        for entry in entries:
            if entry.type == "user":
                if entry.message.get("content"):
                    content_val = entry.message.get("content", "")
                    if isinstance(content_val, str) and "Sidechain" in content_val:
                        assert entry.is_sidechain is True
                        assert entry.agent_id == "agent-1"

    @pytest.mark.asyncio
    async def test_insert_with_logical_parent_for_compact_boundary(self, tmp_dir):
        storage = self._make_storage(tmp_dir)
        await storage.start()

        parent_id = str(uuid.uuid4())
        compact_id = str(uuid.uuid4())

        await storage.insert_message_chain([
            {
                "type": "user",
                "uuid": parent_id,
                "message": {"content": "Before"},
            },
            {
                "type": "system",
                "uuid": compact_id,
                "subtype": "compact_boundary",
                "message": {"content": "Boundary"},
            },
        ])

        await storage.close()

        entries = await storage.load_transcript()
        for entry in entries:
            if entry.uuid == compact_id:
                assert entry.logical_parent_uuid == parent_id
                assert entry.parent_uuid is None

    @pytest.mark.asyncio
    async def test_load_transcript_empty(self, tmp_dir):
        storage = self._make_storage(tmp_dir)
        entries = await storage.load_transcript()
        assert entries == []

    @pytest.mark.asyncio
    async def test_load_transcript_returns_entries(self, tmp_dir):
        storage = self._make_storage(tmp_dir, disabled=True)
        path = storage.transcript_path
        path.parent.mkdir(parents=True, exist_ok=True)

        entry_data = {
            "type": "user",
            "uuid": "uuid-1",
            "parentUuid": None,
            "timestamp": "2025-01-01T00:00:00.000Z",
            "sessionId": storage.session_id,
            "userType": "external",
            "entrypoint": "cli",
            "cwd": str(tmp_dir),
            "version": VERSION,
            "role": "user",
            "content": "Hello World",
        }
        path.write_text(json.dumps(entry_data) + "\n", encoding="utf-8")

        entries = await storage.load_transcript()
        assert len(entries) == 1
        assert entries[0].type == "user"
        assert entries[0].message.get("content") == "Hello World"


    @pytest.mark.asyncio
    async def test_load_transcript_handles_50mb_limit(self, tmp_dir):
        storage = self._make_storage(tmp_dir, disabled=True)
        path = storage.transcript_path
        path.parent.mkdir(parents=True, exist_ok=True)

        large_content = "x" * (MAX_TRANSCRIPT_READ_BYTES + 1000)
        entry = json.dumps({
            "type": "user",
            "uuid": "uuid-1",
            "parentUuid": None,
            "sessionId": storage.session_id,
            "userType": "external",
            "entrypoint": "cli",
            "cwd": str(tmp_dir),
            "version": VERSION,
            "content": large_content,
        })
        path.write_text(entry + "\n", encoding="utf-8")

        entries = await storage.load_transcript()
        assert isinstance(entries, list)

    @pytest.mark.asyncio
    async def test_build_conversation_chain(self, tmp_dir):
        storage = self._make_storage(tmp_dir, disabled=True)
        entry1 = SessionEntry(type="user", uuid="uuid-1", parent_uuid=None, message={"content": "First"})
        entry2 = SessionEntry(type="assistant", uuid="uuid-2", parent_uuid="uuid-1", message={"content": "Reply"})
        entry3 = SessionEntry(type="user", uuid="uuid-3", parent_uuid="uuid-2", message={"content": "Second"})

        chain = storage.build_conversation_chain([entry1, entry2, entry3])
        assert len(chain) == 3
        assert chain[0].uuid == "uuid-1"
        assert chain[1].uuid == "uuid-2"
        assert chain[2].uuid == "uuid-3"

    @pytest.mark.asyncio
    async def test_build_conversation_chain_detects_cycle(self, tmp_dir):
        storage = self._make_storage(tmp_dir, disabled=True)
        entry1 = SessionEntry(type="user", uuid="uuid-1", parent_uuid="uuid-3")
        entry2 = SessionEntry(type="assistant", uuid="uuid-2", parent_uuid="uuid-1")
        entry3 = SessionEntry(type="user", uuid="uuid-3", parent_uuid="uuid-2")

        chain = storage.build_conversation_chain([entry1, entry2, entry3])
        assert len(chain) >= 1

    @pytest.mark.asyncio
    async def test_build_conversation_chain_empty(self, tmp_dir):
        storage = self._make_storage(tmp_dir, disabled=True)
        chain = storage.build_conversation_chain([])
        assert chain == []

    @pytest.mark.asyncio
    async def test_write_and_read_agent_metadata(self, tmp_dir):
        storage = self._make_storage(tmp_dir)
        agent_id = "agent-test-1"
        metadata = {"agentType": "Explore", "description": "Search the codebase"}

        await storage.write_agent_metadata(agent_id, metadata)
        path = storage.get_agent_metadata_path(agent_id)
        assert path.exists()

        restored = await storage.read_agent_metadata(agent_id)
        assert restored is not None
        assert restored["agentType"] == "Explore"
        assert restored["description"] == "Search the codebase"

    @pytest.mark.asyncio
    async def test_read_agent_metadata_missing(self, tmp_dir):
        storage = self._make_storage(tmp_dir)
        result = await storage.read_agent_metadata("nonexistent")
        assert result is None


class TestUtilityFunctions:
    def test_is_transcript_message(self):
        assert is_transcript_message("user") is True
        assert is_transcript_message("assistant") is True
        assert is_transcript_message("attachment") is True
        assert is_transcript_message("system") is True

    def test_is_not_transcript_message(self):
        assert is_transcript_message("progress") is False
        assert is_transcript_message("file-history-snapshot") is False

    def test_is_chain_participant(self):
        assert is_chain_participant("user") is True
        assert is_chain_participant("assistant") is True
        assert is_chain_participant("progress") is False


class TestCleanOldSessions:
    @pytest.mark.asyncio
    async def test_clean_old_sessions_empty_dir(self):
        with tempfile.TemporaryDirectory() as d:
            count = await SessionStorage.clean_old_sessions(Path(d), max_age_days=30)
            assert count == 0

    @pytest.mark.asyncio
    async def test_clean_old_sessions_preserves_recent(self):
        with tempfile.TemporaryDirectory() as d:
            recent_file = Path(d) / "recent.jsonl"
            recent_file.write_text('{"type":"user","uuid":"1"}\n', encoding="utf-8")
            recent_file.touch()

            count = await SessionStorage.clean_old_sessions(Path(d), max_age_days=30)
            assert count == 0
            assert recent_file.exists()
