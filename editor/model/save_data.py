"""SaveData class for save file parsing.

Matches the C# lib.remnant2.saves/Model/SaveData structure.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from editor.model.memory import FTopLevelAssetPath, OffsetInfo, PackageVersion
from editor.model.parts import SerializationContext
from editor.model.uobject import UObject

if TYPE_CHECKING:
    from editor.io.reader import Reader
    from editor.io.writer import Writer


@dataclass
class SaveData:
    """Serialized save data block.

    Contains the core save data with names table, objects table,
    and all object properties/components.
    """

    package_version: PackageVersion | None = None
    save_game_class_path: FTopLevelAssetPath | None = None
    name_table_offset: int = 0
    version: int = 0
    objects_offset: int = 0
    objects: list[UObject] = field(default_factory=list)
    names_table: list[str] = field(default_factory=list)

    @classmethod
    def read(
        cls,
        reader: Reader,
        has_package_version: bool = True,
        has_top_level_asset_path: bool = True,
        container_offset: int = 0,
        options: dict[str, Any] | None = None,
    ) -> SaveData:
        """Read SaveData from reader.

        Args:
            reader: Binary reader
            has_package_version: Whether to read PackageVersion first
            has_top_level_asset_path: Whether to read FTopLevelAssetPath
            container_offset: Offset of container for nested data
            options: Optional parsing options
        """
        # Read optional headers
        package_version = None
        if has_package_version:
            package_version = PackageVersion.read(reader)

        save_game_class_path = None
        if has_top_level_asset_path:
            save_game_class_path = FTopLevelAssetPath.read(reader)

        # Read offset info
        oi = OffsetInfo.read(reader)
        name_table_offset = oi.names
        version = oi.version
        objects_offset = oi.objects

        objects_data_offset = reader.position
        max_position = reader.position

        # Read names table
        reader.position = int(name_table_offset)
        names_count = reader.read_int32()
        names_table = []
        for _ in range(names_count):
            name = reader.read_fstring()
            if name is None:
                raise ValueError('Unexpected null entry in names table')
            names_table.append(name)

        # Create serialization context
        ctx = SerializationContext(
            names_table=names_table,
            class_path=save_game_class_path.path if save_game_class_path else None,
            container_offset=container_offset,
            options=options,
        )

        max_position = max(max_position, reader.position)

        # Read objects table (headers)
        reader.position = int(objects_offset)
        num_objects = reader.read_int32()
        objects = []
        for i in range(num_objects):
            obj = UObject.read_header(reader, ctx, i)
            objects.append(obj)

        ctx.objects = objects
        max_position = max(max_position, reader.position)

        # Read objects data (properties and components)
        reader.position = objects_data_offset
        for obj in objects:
            obj.read_data(reader, ctx)

        max_position = max(max_position, reader.position)
        reader.position = max_position

        return cls(
            package_version=package_version,
            save_game_class_path=save_game_class_path,
            name_table_offset=name_table_offset,
            version=version,
            objects_offset=objects_offset,
            objects=objects,
            names_table=names_table,
        )

    def write(
        self,
        writer: Writer,
        container_offset: int = 0,
    ) -> None:
        """Write SaveData to writer.

        Args:
            writer: Binary writer
            container_offset: Offset of container for nested data
        """
        # Write optional headers
        if self.package_version is not None:
            self.package_version.write(writer)

        if self.save_game_class_path is not None:
            self.save_game_class_path.write(writer)

        # Write OffsetInfo placeholder
        offset_position = writer.position
        oi = OffsetInfo(names=0, version=self.version, objects=0)
        oi.write(writer)

        # Create serialization context
        ctx = SerializationContext(
            names_table=list(self.names_table),  # Copy for potential additions
            class_path=self.save_game_class_path.path if self.save_game_class_path else None,
            objects=self.objects,
            container_offset=container_offset,
        )

        # Write objects data (properties and components)
        for obj in self.objects:
            obj.write_data(writer, ctx)

        # Write objects table (headers)
        objects_offset = writer.position
        writer.write_int32(len(self.objects))
        for obj in self.objects:
            obj.write_header(writer, ctx)

        # Write names table
        names_offset = writer.position
        writer.write_int32(len(ctx.names_table))
        for name in ctx.names_table:
            writer.write_fstring(name)

        # Patch OffsetInfo with actual offsets
        end_position = writer.position
        writer.position = offset_position
        oi = OffsetInfo(names=names_offset, version=self.version, objects=objects_offset)
        oi.write(writer)
        writer.position = end_position

        # Update names table in case new names were added during write
        self.names_table = ctx.names_table
