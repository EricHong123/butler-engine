"""
Memory file manager. Python port of Claude Code's memdir.ts.

Manages the file-based memory system for one tenant:
  data/{tenant_id}/memory/
    MEMORY.md          # Index file (one line per memory, max 200 lines)
    topic_*.md         # Long-form memory entries
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from butler.memory.memory_types import (
    MAX_ENTRYPOINT_BYTES,
    MAX_ENTRYPOINT_LINES,
    MEMORY_FILENAME,
    MemoryType,
)


@dataclass
class MemoryEntry:
    """A single memory record."""
    name: str
    description: str
    memory_type: MemoryType
    content: str
    created_at: datetime = field(default_factory=lambda: datetime.now(tz=timezone.utc))
    updated_at: datetime = field(default_factory=lambda: datetime.now(tz=timezone.utc))
    file_name: str = ""  # e.g., "topic_2026_q1.md"

    def to_frontmatter(self) -> str:
        return (
            f"---\n"
            f"name: {self.name}\n"
            f"description: {self.description}\n"
            f"type: {self.memory_type.value}\n"
            f"---\n\n"
            f"{self.content}\n"
        )

    def to_index_line(self) -> str:
        return (
            f"- [{self.memory_type.value}] {self.name}: "
            f"{self.description} → {self.file_name}"
        )


class MemoryManager:
    """
    Manages the file-based memory system for one tenant.

    Directory structure:
      data/{tenant_id}/memory/
        MEMORY.md          # Index file (one line per memory)
        topic_<uuid>.md    # Individual memory files
    """

    def __init__(self, tenant_id: str, data_root: Path):
        self.tenant_id = tenant_id
        self.memory_dir = data_root / tenant_id / "memory"
        self.index_path = self.memory_dir / MEMORY_FILENAME

    async def ensure_dir(self) -> None:
        """Create the memory directory if it doesn't exist. Port of ensureMemoryDirExists."""
        self.memory_dir.mkdir(parents=True, exist_ok=True)

    async def load_index(self) -> str:
        """
        Load and truncate the MEMORY.md index.
        Port of loadMemoryPrompt + truncateEntrypointContent from Claude Code.
        """
        if not self.index_path.exists():
            return ""

        raw = self.index_path.read_text().strip()
        if not raw:
            return ""

        lines = raw.split("\n")
        line_count = len(lines)
        byte_count = len(raw.encode("utf-8"))

        was_line_truncated = line_count > MAX_ENTRYPOINT_LINES
        was_byte_truncated = byte_count > MAX_ENTRYPOINT_BYTES

        if not was_line_truncated and not was_byte_truncated:
            return raw

        # Truncate lines first, then bytes
        if was_line_truncated:
            raw = "\n".join(lines[:MAX_ENTRYPOINT_LINES])

        if was_byte_truncated:
            encoded = raw.encode("utf-8")[:MAX_ENTRYPOINT_BYTES]
            raw = encoded.decode("utf-8", errors="ignore")
            # Cut at last newline to avoid mid-line truncation
            last_nl = raw.rfind("\n")
            if last_nl > 0:
                raw = raw[:last_nl]

        raw += "\n\n> WARNING: MEMORY.md truncated due to size limits."
        return raw

    async def save(self, entry: MemoryEntry) -> None:
        """
        Save a new memory — writes the topic file AND updates the index.
        Port of the Write tool + memdir interaction from Claude Code.
        """
        await self.ensure_dir()

        # Generate file name if not set
        if not entry.file_name:
            entry.file_name = f"topic_{uuid.uuid4().hex[:8]}.md"

        # Write topic file
        topic_path = self.memory_dir / entry.file_name
        topic_path.write_text(entry.to_frontmatter(), encoding="utf-8")

        # Update index
        index_line = entry.to_index_line()
        if self.index_path.exists():
            current = self.index_path.read_text().rstrip()
            self.index_path.write_text(current + "\n" + index_line + "\n", encoding="utf-8")
        else:
            self.index_path.write_text(index_line + "\n", encoding="utf-8")

    async def update(self, file_name: str, entry: MemoryEntry) -> None:
        """Update an existing memory file. Index line is regenerated."""
        topic_path = self.memory_dir / file_name
        if not topic_path.exists():
            raise FileNotFoundError(f"Memory file not found: {file_name}")

        entry.file_name = file_name
        entry.updated_at = datetime.now(tz=timezone.utc)
        topic_path.write_text(entry.to_frontmatter(), encoding="utf-8")

        # Rebuild index (replace the old line)
        await self._rebuild_index()

    async def delete(self, file_name: str) -> None:
        """Delete a memory file and remove from index."""
        topic_path = self.memory_dir / file_name
        if topic_path.exists():
            topic_path.unlink()
        await self._rebuild_index()

    async def list_files(self) -> list[str]:
        """List all memory topic files (excluding MEMORY.md)."""
        if not self.memory_dir.exists():
            return []
        return sorted(
            f.name
            for f in self.memory_dir.iterdir()
            if f.is_file() and f.name != MEMORY_FILENAME and f.name.endswith(".md")
        )

    async def read(self, file_name: str) -> str | None:
        """Read a specific memory topic file."""
        topic_path = self.memory_dir / file_name
        if not topic_path.exists():
            return None
        return topic_path.read_text(encoding="utf-8")

    async def _rebuild_index(self) -> None:
        """Rebuild the index from all topic files."""
        lines: list[str] = []
        for file_name in await self.list_files():
            content = await self.read(file_name)
            if not content:
                continue
            # Extract frontmatter
            entry = self._parse_frontmatter(content, file_name)
            if entry:
                lines.append(entry.to_index_line())

        self.index_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    @staticmethod
    def _parse_frontmatter(content: str, file_name: str) -> MemoryEntry | None:
        """Parse YAML frontmatter from a memory file."""
        lines = content.split("\n")
        if not lines or lines[0].strip() != "---":
            return None

        fm: dict[str, str] = {}
        for i, line in enumerate(lines[1:], 1):
            if line.strip() == "---":
                body_start = i + 1
                break
            if ":" in line:
                key, _, val = line.partition(":")
                fm[key.strip()] = val.strip()
        else:
            body_start = len(lines)

        body = "\n".join(lines[body_start:]).strip()
        if not body:
            return None

        name = fm.get("name", file_name.replace(".md", "").replace("topic_", ""))
        desc = fm.get("description", "")
        mem_type_str = fm.get("type", "user")
        try:
            mem_type = MemoryType(mem_type_str)
        except ValueError:
            mem_type = MemoryType.USER

        return MemoryEntry(
            name=name,
            description=desc,
            memory_type=mem_type,
            content=body,
            file_name=file_name,
        )
