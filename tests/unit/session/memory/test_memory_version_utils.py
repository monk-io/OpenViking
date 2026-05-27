from datetime import datetime

from openviking.session.memory.dataclass import MemoryFile, VersionHistory, VersionHistoryItem
from openviking.session.memory.utils.memory_file_utils import MemoryFileUtils
from openviking.session.memory.utils.messages import parse_memory_file_with_fields


def test_parse_memory_file_without_version_history():
    raw = """hello\n\n<!-- MEMORY_FIELDS
{
  \"memory_type\": \"preferences\"
}
-->"""

    parsed = parse_memory_file_with_fields(raw)

    assert parsed["content"] == "hello"
    assert parsed["memory_type"] == "preferences"
    assert "version_history" not in parsed


def test_parse_memory_file_with_version_history():
    raw = """hello\n\n<!-- MEMORY_FIELDS
{
  \"memory_type\": \"preferences\"
}
-->\n\n<!-- VERSION_HISTORY
{
  \"data_version\": 123,
  \"updated_at\": \"2026-05-27T15:10:23.456Z\",
  \"status\": \"active\",
  \"versions\": [
    {\"data_version\": 123, \"op\": \"update\", \"reverse_diff\": \"abc\"}
  ]
}
-->"""

    parsed = parse_memory_file_with_fields(raw)

    assert parsed["content"] == "hello"
    assert parsed["version_history"]["data_version"] == 123
    assert parsed["version_history"]["status"] == "active"
    assert parsed["version_history"]["versions"][0]["reverse_diff"] == "abc"


def test_write_memory_file_with_version_history():
    memory_file = MemoryFile(
        content="hello",
        extra_fields={"memory_type": "preferences"},
        version_history=VersionHistory(
            data_version=123,
            updated_at=datetime.fromisoformat("2026-05-27T15:10:23.456+00:00"),
            status="active",
            versions=[VersionHistoryItem(data_version=123, op="update", reverse_diff="abc")],
        ),
    )

    raw = MemoryFileUtils.write(memory_file)

    assert "<!-- MEMORY_FIELDS" in raw
    assert "<!-- VERSION_HISTORY" in raw
    assert '"data_version": 123' in raw
    assert '"status": "active"' in raw

    parsed = MemoryFileUtils.read(raw)
    assert parsed.version_history is not None
    assert parsed.version_history.data_version == 123
    assert parsed.version_history.status == "active"
    assert parsed.version_history.versions[0].reverse_diff == "abc"
