"""PersistenceContainer and Actor classes for save file parsing.

Matches the C# lib.remnant2.saves/Model structures.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from editor.io.reader import Reader as ByteReader
from editor.io.writer import Writer as ByteWriter
from editor.model.memory import FTransform
from editor.model.parts import ActorDynamicData, FInfo, SerializationContext
from editor.model.save_data import SaveData

if TYPE_CHECKING:
    from editor.io.reader import Reader
    from editor.io.writer import Writer


@dataclass
class Actor:
    """An actor in a persistence container.

    Contains optional transform and nested SaveData archive.
    """

    has_transform: int  # uint32
    transform: FTransform | None = None
    archive: SaveData | None = None
    dynamic_data: ActorDynamicData | None = None

    @classmethod
    def read(
        cls,
        reader: Reader,
        ctx: SerializationContext,
        container_offset: int = 0,
    ) -> Actor:
        """Read Actor from reader.

        Args:
            reader: Binary reader
            ctx: Serialization context
            container_offset: Offset of container
        """
        has_transform = reader.read_uint32()
        transform = None
        if has_transform != 0:
            transform = FTransform.read(reader)

        # Archive has no PackageVersion or TopLevelAssetPath
        archive = SaveData.read(
            reader,
            has_package_version=False,
            has_top_level_asset_path=False,
            container_offset=container_offset,
            options=ctx.options,
        )

        return cls(
            has_transform=has_transform,
            transform=transform,
            archive=archive,
        )

    def write_non_dynamic(
        self,
        writer: Writer,
        container_offset: int = 0,
    ) -> None:
        """Write Actor (excluding DynamicData) to writer.

        Args:
            writer: Binary writer
            container_offset: Offset of container
        """
        writer.write_uint32(self.has_transform)
        if self.has_transform != 0 and self.transform is not None:
            self.transform.write(writer)

        if self.archive is not None:
            self.archive.write(writer, container_offset)


@dataclass
class PersistenceContainer:
    """Container for persisted actors in a save file.

    Contains version, destroyed actors list, and actor data.
    """

    version: int  # uint32
    destroyed: list[int] = field(default_factory=list)  # List of uint64
    actors: list[tuple[int, Actor]] = field(default_factory=list)  # List of (unique_id, Actor)

    @classmethod
    def read(
        cls,
        reader: Reader,
        ctx: SerializationContext,
        container_offset: int = 0,
    ) -> PersistenceContainer:
        """Read PersistenceContainer from reader.

        Args:
            reader: Binary reader
            ctx: Serialization context
            container_offset: Offset of container
        """
        version = reader.read_uint32()
        index_offset = reader.read_int32()
        dynamic_offset = reader.read_int32()

        # Read actor info table at index offset
        reader.position = index_offset
        info_count = reader.read_uint32()
        actor_info: list[FInfo] = []
        for _ in range(info_count):
            actor_info.append(FInfo.read(reader))

        # Read destroyed actors list
        destroyed: list[int] = []
        destroyed_count = reader.read_uint32()
        for _ in range(destroyed_count):
            destroyed.append(reader.read_uint64())

        # Read each actor using info table
        actors: list[tuple[int, Actor]] = []
        for info in actor_info:
            reader.position = info.offset
            actor_bytes = reader.read_bytes(info.size)
            actor_reader = ByteReader(actor_bytes)
            actor = Actor.read(actor_reader, ctx, info.offset + container_offset)
            actors.append((info.unique_id, actor))

        # Read dynamic data at dynamic offset
        reader.position = dynamic_offset
        dynamic_count = reader.read_uint32()
        for _ in range(dynamic_count):
            dynamic_data = ActorDynamicData.read(reader)
            # Find matching actor by unique_id
            for unique_id, actor in actors:
                if unique_id == dynamic_data.unique_id:
                    actor.dynamic_data = dynamic_data
                    break

        return cls(
            version=version,
            destroyed=destroyed,
            actors=actors,
        )

    def write(
        self,
        writer: Writer,
        container_offset: int = 0,
    ) -> None:
        """Write PersistenceContainer to writer.

        Args:
            writer: Binary writer
            container_offset: Offset of container
        """
        writer.write_uint32(self.version)

        # Write placeholder offsets (will be patched)
        patch_offset = writer.position
        writer.write_int32(0)  # index_offset placeholder
        writer.write_int32(0)  # dynamic_offset placeholder

        # Write each actor and collect info
        actor_info: list[FInfo] = []
        for unique_id, actor in self.actors:
            actor_writer = ByteWriter()
            actor.write_non_dynamic(actor_writer, int(writer.position) + container_offset)
            actor_data = actor_writer.to_bytes()

            actor_info.append(FInfo(
                unique_id=unique_id,
                offset=writer.position,
                size=len(actor_data),
            ))
            writer.write_bytes(actor_data)

        # Record dynamic offset and write dynamic data
        dynamic_offset = writer.position
        dynamic_count = sum(1 for _, a in self.actors if a.dynamic_data is not None)
        writer.write_uint32(dynamic_count)
        for _, actor in self.actors:
            if actor.dynamic_data is not None:
                actor.dynamic_data.write(writer)

        # Record index offset and write actor info table
        index_offset = writer.position
        writer.write_uint32(len(actor_info))
        for info in actor_info:
            info.write(writer)

        # Write destroyed list
        writer.write_uint32(len(self.destroyed))
        for destroyed_id in self.destroyed:
            writer.write_uint64(destroyed_id)

        # Patch offsets
        end_position = writer.position
        writer.position = patch_offset
        writer.write_int32(index_offset)
        writer.write_int32(dynamic_offset)
        writer.position = end_position
