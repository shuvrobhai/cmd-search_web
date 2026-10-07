"""
Unit tests for the deepened surfaces module (Provider and Conversation resolution).
"""

from __future__ import annotations

import time
from pathlib import Path

import pytest

from scripts.engine import (
    ERR_AMBIGUOUS_SESSION,
    ERR_INVALID_ARGS,
    ERR_NO_SESSION,
    ERR_NO_TRANSCRIPT,
)
from scripts.surfaces import (
    Conversation,
    SessionResolutionError,
    resolve_brain_dir,
    resolve_conversation,
    resolve_session_dir,
)

VALID_UUID = "550e8400-e29b-41d4-a716-446655440000"
SECOND_UUID = "660e8400-e29b-41d4-a716-446655440001"


class TestResolveConversation:
    def test_ide_surface_rejection(self, tmp_path: Path) -> None:
        with pytest.raises(SessionResolutionError) as exc_info:
            resolve_conversation(surface="ide", brain_dir=tmp_path)
        assert exc_info.value.error_code == ERR_NO_TRANSCRIPT
        assert "IDE surface" in exc_info.value.message

    def test_missing_brain_directory(self, tmp_path: Path) -> None:
        non_existent = tmp_path / "does_not_exist"
        with pytest.raises(SessionResolutionError) as exc_info:
            resolve_conversation(conv_id=VALID_UUID, brain_dir=non_existent)
        assert exc_info.value.error_code == ERR_NO_SESSION

    def test_explicit_valid_uuid(self, tmp_path: Path) -> None:
        session_dir = tmp_path / VALID_UUID
        session_dir.mkdir()

        conv = resolve_conversation(conv_id=VALID_UUID, brain_dir=tmp_path)
        assert isinstance(conv, Conversation)
        assert conv.id == VALID_UUID
        assert conv.conversation_dir == session_dir
        assert conv.brain_dir == tmp_path

    def test_explicit_invalid_uuid(self, tmp_path: Path) -> None:
        with pytest.raises(SessionResolutionError) as exc_info:
            resolve_conversation(conv_id="not-a-uuid", brain_dir=tmp_path)
        assert exc_info.value.error_code == ERR_INVALID_ARGS

    def test_explicit_nonexistent_session(self, tmp_path: Path) -> None:
        with pytest.raises(SessionResolutionError) as exc_info:
            resolve_conversation(conv_id=VALID_UUID, brain_dir=tmp_path)
        assert exc_info.value.error_code == ERR_NO_SESSION

    def test_auto_active_marker(self, tmp_path: Path) -> None:
        session_dir = tmp_path / VALID_UUID
        session_dir.mkdir()
        marker = tmp_path / ".active_session"
        marker.write_text(VALID_UUID)

        conv = resolve_conversation(auto=True, brain_dir=tmp_path)
        assert conv.id == VALID_UUID
        assert conv.conversation_dir == session_dir

    def test_auto_recent_window(self, tmp_path: Path) -> None:
        session_dir = tmp_path / VALID_UUID
        session_dir.mkdir()

        conv = resolve_conversation(auto=True, brain_dir=tmp_path)
        assert conv.id == VALID_UUID
        assert conv.conversation_dir == session_dir

    def test_auto_ambiguous_sessions(self, tmp_path: Path) -> None:
        (tmp_path / VALID_UUID).mkdir()
        (tmp_path / SECOND_UUID).mkdir()

        with pytest.raises(SessionResolutionError) as exc_info:
            resolve_conversation(auto=True, brain_dir=tmp_path)
        assert exc_info.value.error_code == ERR_AMBIGUOUS_SESSION
        assert "Multiple active sessions" in exc_info.value.message

    def test_auto_no_sessions(self, tmp_path: Path) -> None:
        with pytest.raises(SessionResolutionError) as exc_info:
            resolve_conversation(auto=True, brain_dir=tmp_path)
        assert exc_info.value.error_code == ERR_NO_SESSION

    def test_neither_conv_id_nor_auto(self, tmp_path: Path) -> None:
        with pytest.raises(SessionResolutionError) as exc_info:
            resolve_conversation(auto=False, brain_dir=tmp_path)
        assert exc_info.value.error_code == ERR_INVALID_ARGS


class TestConversationProperties:
    def test_transcript_paths(self, tmp_path: Path) -> None:
        session_dir = tmp_path / VALID_UUID
        session_dir.mkdir()
        logs_dir = session_dir / ".system_generated" / "logs"
        logs_dir.mkdir(parents=True)

        conv = Conversation(
            id=VALID_UUID,
            surface="cli",
            conversation_dir=session_dir,
            brain_dir=tmp_path,
        )

        assert conv.transcript_path is None

        std_transcript = logs_dir / "transcript.jsonl"
        std_transcript.write_text("{}\n")
        assert conv.transcript_path == std_transcript

        full_transcript = logs_dir / "transcript_full.jsonl"
        full_transcript.write_text("{}\n")
        assert conv.transcript_path == full_transcript


class TestLegacyAdapters:
    def test_resolve_session_dir_adapter(self, tmp_path: Path) -> None:
        session_dir = tmp_path / VALID_UUID
        session_dir.mkdir()

        conv_id, conv_dir = resolve_session_dir(
            brain_dir=tmp_path,
            conv_id=VALID_UUID,
            auto=False,
        )
        assert conv_id == VALID_UUID
        assert conv_dir == session_dir
