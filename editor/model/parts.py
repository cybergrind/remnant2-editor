"""Parts and helper types for save file parsing.

These match the C# lib.remnant2.saves/Model/Parts structures.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from editor.io.reader import Reader
    from editor.io.writer import Writer


@dataclass
class FName:
    """Unreal FName - an interned string reference.

    FNames are stored as indices into a names table, with an optional
    instance number suffix. The index uses bit 15 to indicate if an
    instance number follows.
    """

    name: str
    index: int = 0
    number: int | None = None

    # Bit 15 indicates if there's an instance number
    INDEX_HAS_NUMBER_MASK = 0x8000
    INDEX_MASK = 0x7FFF

    @classmethod
    def read(cls, reader: Reader, names_table: list[str]) -> FName:
        """Read FName from reader using the names table."""
        raw_index = reader.read_uint16()
        has_number = (raw_index & cls.INDEX_HAS_NUMBER_MASK) != 0
        index = raw_index & cls.INDEX_MASK

        if index >= len(names_table):
            raise ValueError(f'FName index {index} out of range (table has {len(names_table)} entries)')

        name = names_table[index]
        number = reader.read_int32() if has_number else None

        return cls(name=name, index=index, number=number)

    def write(self, writer: Writer, ctx: SerializationContext) -> None:
        """Write FName to writer, adding to names table if needed."""
        # Check if we can use the original index (optimization and correctness)
        # This is important because inner/outer names tables can have the same
        # name at different indices, and we need to preserve the original index
        # when the name hasn't changed.
        if self.index < len(ctx.names_table) and ctx.names_table[self.index] == self.name:
            # Original index is still valid - use it
            index = self.index
        else:
            # Name was modified or doesn't match - look up by name
            index = ctx.get_or_add_name(self.name)

        # Set bit 15 if we have an instance number
        raw_index = index
        if self.number is not None:
            raw_index |= self.INDEX_HAS_NUMBER_MASK

        writer.write_uint16(raw_index)
        if self.number is not None:
            writer.write_int32(self.number)

    def __str__(self) -> str:
        if self.number is not None:
            return f'{self.name}_{self.number}'
        return self.name


@dataclass
class UObjectLoadedData:
    """Loaded data for a UObject (name and outer ID)."""

    name: FName
    outer_id: int  # uint32

    @classmethod
    def read(cls, reader: Reader, names_table: list[str]) -> UObjectLoadedData:
        """Read UObjectLoadedData from reader."""
        return cls(
            name=FName.read(reader, names_table),
            outer_id=reader.read_uint32(),
        )

    def write(self, writer: Writer, ctx: SerializationContext) -> None:
        """Write UObjectLoadedData to writer."""
        self.name.write(writer, ctx)
        writer.write_uint32(self.outer_id)


@dataclass
class FInfo:
    """Info structure for persistence container (unique_id, offset, size)."""

    unique_id: int  # uint64
    offset: int  # int32
    size: int  # int32

    @classmethod
    def read(cls, reader: Reader) -> FInfo:
        """Read FInfo from reader."""
        return cls(
            unique_id=reader.read_uint64(),
            offset=reader.read_int32(),
            size=reader.read_int32(),
        )

    def write(self, writer: Writer) -> None:
        """Write FInfo to writer."""
        writer.write_uint64(self.unique_id)
        writer.write_int32(self.offset)
        writer.write_int32(self.size)


@dataclass
class ActorDynamicData:
    """Dynamic data for an actor in persistence container."""

    unique_id: int  # uint64
    transform: Any  # FTransform - imported at runtime to avoid circular import
    class_path: str | None

    @classmethod
    def read(cls, reader: Reader) -> ActorDynamicData:
        """Read ActorDynamicData from reader."""
        from editor.model.memory import FTransform

        return cls(
            unique_id=reader.read_uint64(),
            transform=FTransform.read(reader),
            class_path=reader.read_fstring(),
        )

    def write(self, writer: Writer) -> None:
        """Write ActorDynamicData to writer."""
        writer.write_uint64(self.unique_id)
        self.transform.write(writer)
        writer.write_fstring(self.class_path)


@dataclass
class SerializationContext:
    """Context for serialization operations.

    Holds shared state like the names table and object references.
    """

    names_table: list[str] = field(default_factory=list)
    class_path: str | None = None
    objects: list[Any] | None = None  # List of UObjects
    container_offset: int = 0
    options: dict[str, Any] | None = None

    # Cache for name lookups during writing
    _name_to_index: dict[str, int] = field(default_factory=dict, repr=False)

    def __post_init__(self) -> None:
        """Build the name lookup cache."""
        self._rebuild_name_cache()

    def _rebuild_name_cache(self) -> None:
        """Rebuild the name-to-index cache."""
        self._name_to_index = {name: i for i, name in enumerate(self.names_table)}

    def get_or_add_name(self, name: str) -> int:
        """Get the index of a name, adding it to the table if needed."""
        if name in self._name_to_index:
            return self._name_to_index[name]

        # Add new name to table
        index = len(self.names_table)
        self.names_table.append(name)
        self._name_to_index[name] = index
        return index

    def get_name_index(self, name: str) -> int:
        """Get the index of a name (must exist)."""
        return self._name_to_index[name]
