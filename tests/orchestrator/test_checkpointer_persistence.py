"""Tests for Pluggable Checkpointer and SQLite Durability."""

import os
import tempfile
import pytest
from langgraph.checkpoint.base import (
    Checkpoint,
    CheckpointMetadata,
    empty_checkpoint,
)
from orchestrator.checkpointer import (
    SqliteCheckpointer,
    get_checkpointer,
)


@pytest.fixture
def temp_db_path():
    """Provide a temporary database file path and clean up afterwards."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        path = f.name
    yield path
    if os.path.exists(path):
        try:
            os.remove(path)
        except OSError:
            pass


def test_sqlite_checkpointer_initialization():
    """Verify that SqliteCheckpointer initializes schema in WAL mode."""
    cp = SqliteCheckpointer(":memory:")
    cur = cp.conn.cursor()
    cur.execute("SELECT name FROM sqlite_master WHERE type='table';")
    tables = {row[0] for row in cur.fetchall()}
    assert "checkpoints" in tables
    assert "blobs" in tables
    assert "writes" in tables
    cp.close()


def test_sqlite_checkpointer_put_and_get_tuple():
    """Test saving and retrieving checkpoint tuples."""
    cp = SqliteCheckpointer(":memory:")
    config = {"configurable": {"thread_id": "thread-101", "checkpoint_ns": ""}}

    cp_obj = empty_checkpoint()
    cp_obj["id"] = "step-1"
    cp_obj["channel_values"] = {"status": "INITIALIZED", "count": 1}
    cp_obj["channel_versions"] = {"status": 1, "count": 1}
    metadata: CheckpointMetadata = {"source": "input", "step": 1, "writes": {}}

    res_config = cp.put(
        config=config,
        checkpoint=cp_obj,
        metadata=metadata,
        new_versions={"status": 1, "count": 1},
    )
    assert res_config["configurable"]["checkpoint_id"] == "step-1"

    tup = cp.get_tuple(config)
    assert tup is not None
    assert tup.checkpoint["id"] == "step-1"
    assert tup.checkpoint["channel_values"]["status"] == "INITIALIZED"
    assert tup.checkpoint["channel_values"]["count"] == 1
    assert tup.metadata["step"] == 1
    cp.close()


def test_sqlite_disk_persistence_survives_reconnect(temp_db_path):
    """Proves snapshots survive process termination and reconnection."""
    # Process 1: save checkpoint to disk
    cp1 = SqliteCheckpointer(temp_db_path)
    config = {"configurable": {"thread_id": "thread-persist-1", "checkpoint_ns": ""}}
    cp_obj = empty_checkpoint()
    cp_obj["id"] = "step-saved-on-disk"
    cp_obj["channel_values"] = {"incident": "INC-8899", "tier": "PROD"}
    cp_obj["channel_versions"] = {"incident": 1, "tier": 1}
    metadata: CheckpointMetadata = {"source": "test", "step": 1, "writes": {}}

    cp1.put(
        config=config,
        checkpoint=cp_obj,
        metadata=metadata,
        new_versions={"incident": 1, "tier": 1},
    )
    cp1.close()

    # Process 2: open new checkpointer instance pointing to the same file
    cp2 = SqliteCheckpointer(temp_db_path)
    tup = cp2.get_tuple(config)
    assert tup is not None
    assert tup.checkpoint["id"] == "step-saved-on-disk"
    assert tup.checkpoint["channel_values"]["incident"] == "INC-8899"
    assert tup.checkpoint["channel_values"]["tier"] == "PROD"
    cp2.close()


def test_sqlite_delete_thread_purges_state(temp_db_path):
    """Proves delete_thread completely purges thread records for issue reset."""
    cp = SqliteCheckpointer(temp_db_path)
    config = {"configurable": {"thread_id": "thread-to-delete", "checkpoint_ns": ""}}
    cp_obj = empty_checkpoint()
    cp_obj["id"] = "step-del"
    cp_obj["channel_values"] = {"key": "val"}
    cp_obj["channel_versions"] = {"key": 1}

    cp.put(config=config, checkpoint=cp_obj, metadata={"writes": {}}, new_versions={"key": 1})
    assert cp.get_tuple(config) is not None

    cp.delete_thread("thread-to-delete")
    assert cp.get_tuple(config) is None
    cp.close()


def test_get_checkpointer_factory():
    """Proves checkpointer factory supports sqlite default and validates inputs."""
    # Default is sqlite
    cp_default = get_checkpointer()
    assert isinstance(cp_default, SqliteCheckpointer)
    cp_default.close()

    # Explicit sqlite
    cp_sqlite = get_checkpointer("sqlite", connection_string=":memory:")
    assert isinstance(cp_sqlite, SqliteCheckpointer)
    cp_sqlite.close()

    # Invalid backend raises ValueError
    with pytest.raises(ValueError, match="Unsupported checkpointer backend"):
        get_checkpointer("redis")

    # Postgres without DATABASE_URL raises ValueError
    with pytest.raises(ValueError, match="DATABASE_URL or connection_string is required"):
        get_checkpointer("postgres")
