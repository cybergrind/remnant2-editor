"""Property types for save file parsing.

These match the C# lib.remnant2.saves/Model/Properties structures.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import TYPE_CHECKING, Any

from editor.log import log
from editor.model.memory import FGuid, FRotator, FVector
from editor.model.parts import FName, SerializationContext

if TYPE_CHECKING:
    from editor.io.reader import Reader
    from editor.io.writer import Writer


@dataclass
class Property:
    """A single property in a PropertyBag."""

    name: FName
    type_name: FName
    size: int  # uint32
    index: int  # uint32
    no_raw: int = 0  # byte
    value: Any = None

    @classmethod
    def read(cls, reader: Reader, ctx: SerializationContext) -> Property:
        """Read Property from reader."""
        name = FName.read(reader, ctx.names_table)

        # "None" marks end of properties
        if name.name == 'None':
            return cls(
                name=name,
                type_name=FName(name='None', index=0),
                size=0,
                index=0,
            )

        type_name = FName.read(reader, ctx.names_table)
        size = reader.read_uint32()
        index = reader.read_uint32()

        # Read the value based on type
        value, no_raw = read_property_value(reader, ctx, type_name.name, size)

        return cls(
            name=name,
            type_name=type_name,
            size=size,
            index=index,
            no_raw=no_raw,
            value=value,
        )

    def write(self, writer: Writer, ctx: SerializationContext) -> None:
        """Write Property to writer."""
        self.name.write(writer, ctx)

        if self.name.name == 'None':
            return

        self.type_name.write(writer, ctx)

        # Write size (use stored size, will patch for struct/array types)
        size_pos = writer.position
        writer.write_uint32(self.size)
        writer.write_uint32(self.index)

        # Write value
        start_pos = writer.position
        write_property_value(writer, ctx, self.type_name.name, self.value, self.no_raw)
        end_pos = writer.position

        # Only patch size for StructProperty and ArrayProperty (matches C# Property.cs)
        # MapProperty does NOT get size adjustment per C# implementation
        if self.type_name.name in ('StructProperty', 'ArrayProperty'):
            actual_size = end_pos - start_pos
            adjusted_size = adjust_size_for_write(self.type_name.name, actual_size)
            writer.position = size_pos
            writer.write_uint32(adjusted_size)
            writer.position = end_pos


@dataclass
class PropertyBag:
    """A collection of properties."""

    properties: list[tuple[str, Property]] = field(default_factory=list)
    _lookup: dict[str, Property] = field(default_factory=dict, repr=False)

    @classmethod
    def read(cls, reader: Reader, ctx: SerializationContext) -> PropertyBag:
        """Read PropertyBag from reader."""
        properties = []
        lookup = {}

        while True:
            prop = Property.read(reader, ctx)
            if prop.name.name == 'None':
                break

            properties.append((prop.name.name, prop))
            if prop.name.name not in lookup:
                lookup[prop.name.name] = prop

        return cls(properties=properties, _lookup=lookup)

    def write(self, writer: Writer, ctx: SerializationContext) -> None:
        """Write PropertyBag to writer."""
        for name, prop in self.properties:
            prop.write(writer, ctx)

        # Write "None" terminator
        none_name = FName(name='None', index=ctx.get_or_add_name('None'))
        none_name.write(writer, ctx)

    def __getitem__(self, key: str) -> Property:
        return self._lookup[key]

    def __contains__(self, key: str) -> bool:
        return key in self._lookup

    def get(self, key: str, default: Any = None) -> Property | Any:
        return self._lookup.get(key, default)


@dataclass
class StructProperty:
    """A struct property value."""

    type_name: FName
    guid: FGuid
    unknown: int  # byte
    value: Any

    @classmethod
    def read(cls, reader: Reader, ctx: SerializationContext) -> StructProperty:
        """Read StructProperty from reader."""
        type_name = FName.read(reader, ctx.names_table)
        guid = FGuid.read(reader)
        unknown = reader.read_uint8()

        if unknown != 0:
            log.warning(f'Unexpected non-zero unknown byte in StructProperty: {unknown}')

        value = read_struct_value(reader, ctx, type_name.name)

        return cls(
            type_name=type_name,
            guid=guid,
            unknown=unknown,
            value=value,
        )

    def write(self, writer: Writer, ctx: SerializationContext) -> None:
        """Write StructProperty to writer."""
        self.type_name.write(writer, ctx)
        self.guid.write(writer)
        writer.write_uint8(self.unknown)
        write_struct_value(writer, ctx, self.type_name.name, self.value)


@dataclass
class ArrayStructProperty:
    """An array of structs property.

    Has a more complex structure than regular ArrayProperty with additional
    header fields for each element type.
    """

    unknown: int  # byte (from outer ArrayProperty)
    outer_element_type: FName  # The "StructProperty" type from outer array
    name_index: int  # uint16 - index for element name in names table
    type_index: int  # uint16 - index for element type in names table
    size: int  # uint32 - size of all struct data
    index: int  # uint32 - index field
    element_type: FName  # Actual struct type name (e.g., "PrismSegmentData")
    guid: FGuid
    unknown2: int  # byte
    items: list[Any] = field(default_factory=list)

    @classmethod
    def read(
        cls,
        reader: Reader,
        ctx: SerializationContext,
        count: int,
        unknown: int,
        outer_element_type: FName,
    ) -> ArrayStructProperty:
        """Read ArrayStructProperty from reader."""
        name_index = reader.read_uint16()
        type_index = reader.read_uint16()
        size = reader.read_uint32()
        index = reader.read_uint32()
        element_type = FName.read(reader, ctx.names_table)
        guid = FGuid.read(reader)
        unknown2 = reader.read_uint8()

        if unknown2 != 0:
            log.warning(f'Unexpected non-zero unknown2 byte in ArrayStructProperty: {unknown2}')

        items = []
        for _ in range(count):
            item = read_struct_value(reader, ctx, element_type.name)
            items.append(item)

        return cls(
            unknown=unknown,
            outer_element_type=outer_element_type,
            name_index=name_index,
            type_index=type_index,
            size=size,
            index=index,
            element_type=element_type,
            guid=guid,
            unknown2=unknown2,
            items=items,
        )

    def write(self, writer: Writer, ctx: SerializationContext) -> None:
        """Write ArrayStructProperty to writer."""
        self.outer_element_type.write(writer, ctx)
        writer.write_uint8(self.unknown)
        writer.write_int32(len(self.items))
        writer.write_uint16(self.name_index)
        writer.write_uint16(self.type_index)

        # Write size placeholder
        size_pos = writer.position
        writer.write_uint32(0)  # Will patch later
        writer.write_uint32(self.index)
        self.element_type.write(writer, ctx)
        self.guid.write(writer)
        writer.write_uint8(self.unknown2)

        start_pos = writer.position
        for item in self.items:
            write_struct_value(writer, ctx, self.element_type.name, item)
        end_pos = writer.position

        # Patch size
        actual_size = end_pos - start_pos
        writer.position = size_pos
        writer.write_uint32(actual_size)
        writer.position = end_pos


@dataclass
class ByteProperty:
    """A byte/enum property."""

    enum_name: FName | None
    unknown: int  # byte
    value: Any  # Either int (byte) or FName (enum)

    @classmethod
    def read(cls, reader: Reader, ctx: SerializationContext, size: int) -> ByteProperty:
        """Read ByteProperty from reader."""
        enum_name = FName.read(reader, ctx.names_table)
        unknown = reader.read_uint8()

        if enum_name.name == 'None':
            # Raw byte value
            value = reader.read_uint8()
        else:
            # Enum value as FName
            value = FName.read(reader, ctx.names_table)

        return cls(enum_name=enum_name, unknown=unknown, value=value)

    def write(self, writer: Writer, ctx: SerializationContext) -> None:
        """Write ByteProperty to writer."""
        if self.enum_name:
            self.enum_name.write(writer, ctx)
        else:
            FName(name='None', index=ctx.get_or_add_name('None')).write(writer, ctx)

        writer.write_uint8(self.unknown)

        if isinstance(self.value, FName):
            self.value.write(writer, ctx)
        else:
            writer.write_uint8(self.value)


@dataclass
class EnumProperty:
    """An enum property."""

    enum_type: FName
    unknown: int  # byte
    value: FName

    @classmethod
    def read(cls, reader: Reader, ctx: SerializationContext) -> EnumProperty:
        """Read EnumProperty from reader."""
        enum_type = FName.read(reader, ctx.names_table)
        unknown = reader.read_uint8()
        value = FName.read(reader, ctx.names_table)

        return cls(enum_type=enum_type, unknown=unknown, value=value)

    def write(self, writer: Writer, ctx: SerializationContext) -> None:
        """Write EnumProperty to writer."""
        self.enum_type.write(writer, ctx)
        writer.write_uint8(self.unknown)
        self.value.write(writer, ctx)


@dataclass
class MapProperty:
    """A map property (key-value pairs)."""

    key_type: FName
    value_type: FName
    unknown: bytes  # 5 bytes
    entries: list[tuple[Any, Any]] = field(default_factory=list)

    @classmethod
    def read(cls, reader: Reader, ctx: SerializationContext, size: int) -> MapProperty:
        """Read MapProperty from reader."""
        key_type = FName.read(reader, ctx.names_table)
        value_type = FName.read(reader, ctx.names_table)
        unknown = reader.read_bytes(5)
        count = reader.read_int32()

        entries = []
        for _ in range(count):
            key = read_map_element(reader, ctx, key_type.name)
            value = read_map_element(reader, ctx, value_type.name)
            entries.append((key, value))

        return cls(
            key_type=key_type,
            value_type=value_type,
            unknown=unknown,
            entries=entries,
        )

    def write(self, writer: Writer, ctx: SerializationContext) -> None:
        """Write MapProperty to writer."""
        self.key_type.write(writer, ctx)
        self.value_type.write(writer, ctx)
        writer.write_bytes(self.unknown)
        writer.write_int32(len(self.entries))

        for key, value in self.entries:
            write_map_element(writer, ctx, self.key_type.name, key)
            write_map_element(writer, ctx, self.value_type.name, value)


@dataclass
class ArrayProperty:
    """An array property."""

    element_type: FName
    unknown: int  # byte
    items: list[Any] = field(default_factory=list)

    @classmethod
    def read(cls, reader: Reader, ctx: SerializationContext, size: int) -> ArrayProperty | ArrayStructProperty:
        """Read ArrayProperty from reader."""
        element_type = FName.read(reader, ctx.names_table)
        unknown = reader.read_uint8()
        count = reader.read_int32()

        if element_type.name == 'StructProperty':
            # Special handling for struct arrays - has additional header
            return ArrayStructProperty.read(reader, ctx, count, unknown, element_type)

        items = []
        for _ in range(count):
            item = read_array_element_raw(reader, ctx, element_type.name)
            items.append(item)

        return cls(element_type=element_type, unknown=unknown, items=items)

    def write(self, writer: Writer, ctx: SerializationContext) -> None:
        """Write ArrayProperty to writer."""
        self.element_type.write(writer, ctx)
        writer.write_uint8(self.unknown)
        writer.write_int32(len(self.items))

        for item in self.items:
            write_array_element_raw(writer, ctx, self.element_type.name, item)


@dataclass
class TextProperty:
    """A text property (localized string)."""

    flags: int  # uint32
    history_type: int  # int8
    data: Any  # Varies based on history_type

    @classmethod
    def read(cls, reader: Reader, size: int) -> TextProperty:
        """Read TextProperty from reader."""
        flags = reader.read_uint32()
        history_type = reader.read_int8()

        if history_type == 0:
            # Type 0: namespace, key, source_string
            namespace = reader.read_fstring()
            key = reader.read_fstring()
            source_string = reader.read_fstring()
            data = (namespace, key, source_string)
        elif history_type == -1 or history_type == 255:
            # Type -1/255: flag, value
            flag = reader.read_uint32()
            value = reader.read_fstring() if flag != 0 else None
            data = (flag, value)
        else:
            # Unknown type - read raw bytes
            log.warning(f'Unknown TextProperty history type: {history_type}')
            remaining = size - 5  # Already read 4 + 1 bytes
            data = reader.read_bytes(remaining)

        return cls(flags=flags, history_type=history_type, data=data)

    def write(self, writer: Writer) -> None:
        """Write TextProperty to writer."""
        writer.write_uint32(self.flags)
        writer.write_int8(self.history_type)

        if self.history_type == 0:
            namespace, key, source_string = self.data
            writer.write_fstring(namespace)
            writer.write_fstring(key)
            writer.write_fstring(source_string)
        elif self.history_type == -1 or self.history_type == 255:
            flag, value = self.data
            writer.write_uint32(flag)
            if flag != 0:
                writer.write_fstring(value)
        else:
            writer.write_bytes(self.data)


# ============================================================================
# Property value reading/writing functions
# ============================================================================

def read_property_value(reader: Reader, ctx: SerializationContext, type_name: str, size: int) -> tuple[Any, int]:
    """Read a property value based on type name. Returns (value, no_raw_byte)."""
    no_raw = 0

    if type_name == 'IntProperty':
        no_raw = reader.read_uint8()
        return reader.read_int32(), no_raw

    elif type_name == 'Int16Property':
        no_raw = reader.read_uint8()
        return reader.read_int16(), no_raw

    elif type_name == 'Int64Property':
        no_raw = reader.read_uint8()
        return reader.read_int64(), no_raw

    elif type_name == 'UInt16Property':
        no_raw = reader.read_uint8()
        return reader.read_uint16(), no_raw

    elif type_name == 'UInt32Property':
        no_raw = reader.read_uint8()
        return reader.read_uint32(), no_raw

    elif type_name == 'UInt64Property':
        no_raw = reader.read_uint8()
        return reader.read_uint64(), no_raw

    elif type_name == 'FloatProperty':
        no_raw = reader.read_uint8()
        return reader.read_float(), no_raw

    elif type_name == 'DoubleProperty':
        no_raw = reader.read_uint8()
        return reader.read_double(), no_raw

    elif type_name == 'BoolProperty':
        value = reader.read_uint8()
        no_raw = reader.read_uint8()
        return value != 0, no_raw

    elif type_name == 'StrProperty':
        no_raw = reader.read_uint8()
        return reader.read_fstring(), no_raw

    elif type_name == 'NameProperty':
        no_raw = reader.read_uint8()
        return FName.read(reader, ctx.names_table), no_raw

    elif type_name == 'SoftClassProperty' or type_name == 'SoftObjectProperty':
        no_raw = reader.read_uint8()
        return reader.read_fstring(), no_raw

    elif type_name == 'ObjectProperty':
        no_raw = reader.read_uint8()
        return reader.read_int32(), no_raw  # Object index

    elif type_name == 'ByteProperty':
        return ByteProperty.read(reader, ctx, size), 0

    elif type_name == 'EnumProperty':
        return EnumProperty.read(reader, ctx), 0

    elif type_name == 'StructProperty':
        return StructProperty.read(reader, ctx), 0

    elif type_name == 'ArrayProperty':
        return ArrayProperty.read(reader, ctx, size), 0

    elif type_name == 'MapProperty':
        return MapProperty.read(reader, ctx, size), 0

    elif type_name == 'TextProperty':
        no_raw = reader.read_uint8()
        return TextProperty.read(reader, size), no_raw

    else:
        log.warning(f'Unknown property type: {type_name}, reading {size} raw bytes')
        no_raw = reader.read_uint8()
        return reader.read_bytes(size), no_raw


def write_property_value(writer: Writer, ctx: SerializationContext, type_name: str, value: Any, no_raw: int) -> None:
    """Write a property value based on type name."""
    if type_name == 'IntProperty':
        writer.write_uint8(no_raw)
        writer.write_int32(value)

    elif type_name == 'Int16Property':
        writer.write_uint8(no_raw)
        writer.write_int16(value)

    elif type_name == 'Int64Property':
        writer.write_uint8(no_raw)
        writer.write_int64(value)

    elif type_name == 'UInt16Property':
        writer.write_uint8(no_raw)
        writer.write_uint16(value)

    elif type_name == 'UInt32Property':
        writer.write_uint8(no_raw)
        writer.write_uint32(value)

    elif type_name == 'UInt64Property':
        writer.write_uint8(no_raw)
        writer.write_uint64(value)

    elif type_name == 'FloatProperty':
        writer.write_uint8(no_raw)
        writer.write_float(value)

    elif type_name == 'DoubleProperty':
        writer.write_uint8(no_raw)
        writer.write_double(value)

    elif type_name == 'BoolProperty':
        writer.write_uint8(1 if value else 0)
        writer.write_uint8(no_raw)

    elif type_name == 'StrProperty':
        writer.write_uint8(no_raw)
        writer.write_fstring(value)

    elif type_name == 'NameProperty':
        writer.write_uint8(no_raw)
        value.write(writer, ctx)

    elif type_name == 'SoftClassProperty' or type_name == 'SoftObjectProperty':
        writer.write_uint8(no_raw)
        writer.write_fstring(value)

    elif type_name == 'ObjectProperty':
        writer.write_uint8(no_raw)
        writer.write_int32(value)

    elif type_name == 'ByteProperty':
        value.write(writer, ctx)

    elif type_name == 'EnumProperty':
        value.write(writer, ctx)

    elif type_name == 'StructProperty':
        value.write(writer, ctx)

    elif type_name == 'ArrayProperty':
        value.write(writer, ctx)

    elif type_name == 'MapProperty':
        value.write(writer, ctx)

    elif type_name == 'TextProperty':
        writer.write_uint8(no_raw)
        value.write(writer)

    else:
        writer.write_uint8(no_raw)
        writer.write_bytes(value)


def adjust_size_for_write(type_name: str, actual_size: int) -> int:
    """Adjust the written size for type-specific overhead."""
    if type_name == 'StructProperty':
        return actual_size - 19  # Subtract FName(2) + FGuid(16) + unknown(1)
    elif type_name == 'ArrayProperty':
        return actual_size - 3  # Subtract FName(2) + unknown(1)
    elif type_name == 'MapProperty':
        return actual_size - 9  # Subtract FName(2) + FName(2) + unknown(5)
    elif type_name == 'ByteProperty':
        return actual_size - 3  # Subtract FName(2) + unknown(1)
    elif type_name == 'EnumProperty':
        return actual_size - 3  # Subtract FName(2) + unknown(1)
    return actual_size


def read_struct_value(reader: Reader, ctx: SerializationContext, type_name: str) -> Any:
    """Read a struct value based on type name."""
    if type_name == 'SoftClassPath' or type_name == 'SoftObjectPath':
        return reader.read_fstring()
    elif type_name == 'Timespan':
        return timedelta(microseconds=reader.read_int64() // 10)
    elif type_name == 'Guid':
        return FGuid.read(reader)
    elif type_name == 'Vector':
        return FVector.read(reader)
    elif type_name == 'Rotator':
        return FRotator.read(reader)
    elif type_name == 'DateTime':
        ticks = reader.read_int64()
        # Convert .NET ticks to datetime (ticks since 1/1/0001)
        return datetime(1, 1, 1) + timedelta(microseconds=ticks // 10)
    elif type_name == 'PersistenceBlob':
        return read_persistence_blob(reader, ctx)
    else:
        # Default to PropertyBag
        return PropertyBag.read(reader, ctx)


def write_struct_value(writer: Writer, ctx: SerializationContext, type_name: str, value: Any) -> None:
    """Write a struct value based on type name."""
    if type_name == 'SoftClassPath' or type_name == 'SoftObjectPath':
        writer.write_fstring(value)
    elif type_name == 'Timespan':
        ticks = int(value.total_seconds() * 10_000_000)
        writer.write_int64(ticks)
    elif type_name == 'Guid':
        value.write(writer)
    elif type_name == 'Vector':
        value.write(writer)
    elif type_name == 'Rotator':
        value.write(writer)
    elif type_name == 'DateTime':
        # Convert datetime to .NET ticks
        delta = value - datetime(1, 1, 1)
        ticks = int(delta.total_seconds() * 10_000_000)
        writer.write_int64(ticks)
    elif type_name == 'PersistenceBlob':
        write_persistence_blob(writer, ctx, value)
    else:
        # Default to PropertyBag
        value.write(writer, ctx)


def read_array_element_raw(reader: Reader, ctx: SerializationContext, type_name: str) -> Any:
    """Read an array element in raw mode (no header bytes).

    In C# this is PropertyValue.ReadPropertyValue with isRaw=true.
    """
    if type_name == 'IntProperty':
        return reader.read_int32()
    elif type_name == 'Int16Property':
        return reader.read_int16()
    elif type_name == 'Int64Property':
        return reader.read_int64()
    elif type_name == 'UInt16Property':
        return reader.read_uint16()
    elif type_name == 'UInt32Property':
        return reader.read_uint32()
    elif type_name == 'UInt64Property':
        return reader.read_uint64()
    elif type_name == 'FloatProperty':
        return reader.read_float()
    elif type_name == 'DoubleProperty':
        return reader.read_double()
    elif type_name == 'StrProperty' or type_name == 'SoftClassPath' or type_name == 'SoftObjectProperty':
        return reader.read_fstring()
    elif type_name == 'BoolProperty':
        return reader.read_uint8() != 0
    elif type_name == 'NameProperty':
        return FName.read(reader, ctx.names_table)
    elif type_name == 'ByteProperty':
        return reader.read_uint8()
    elif type_name == 'StructProperty':
        # Raw struct is just a GUID
        return FGuid.read(reader)
    elif type_name == 'ObjectProperty':
        # ObjectProperty reads through ObjectProperty class even in raw mode
        return reader.read_int32()  # Simplified - just read the index
    else:
        log.warning(f'Unknown array element type: {type_name}')
        return None


def write_array_element_raw(writer: Writer, ctx: SerializationContext, type_name: str, value: Any) -> None:
    """Write an array element in raw mode (no header bytes)."""
    if type_name == 'IntProperty':
        writer.write_int32(value)
    elif type_name == 'Int16Property':
        writer.write_int16(value)
    elif type_name == 'Int64Property':
        writer.write_int64(value)
    elif type_name == 'UInt16Property':
        writer.write_uint16(value)
    elif type_name == 'UInt32Property':
        writer.write_uint32(value)
    elif type_name == 'UInt64Property':
        writer.write_uint64(value)
    elif type_name == 'FloatProperty':
        writer.write_float(value)
    elif type_name == 'DoubleProperty':
        writer.write_double(value)
    elif type_name == 'StrProperty' or type_name == 'SoftClassPath' or type_name == 'SoftObjectProperty':
        writer.write_fstring(value)
    elif type_name == 'BoolProperty':
        writer.write_uint8(1 if value else 0)
    elif type_name == 'NameProperty':
        value.write(writer, ctx)
    elif type_name == 'ByteProperty':
        writer.write_uint8(value)
    elif type_name == 'StructProperty':
        # Raw struct is just a GUID
        value.write(writer)
    elif type_name == 'ObjectProperty':
        writer.write_int32(value)


# Aliases for backwards compatibility
def read_array_element(reader: Reader, ctx: SerializationContext, type_name: str) -> Any:
    """Read an array element (raw mode)."""
    return read_array_element_raw(reader, ctx, type_name)


def write_array_element(writer: Writer, ctx: SerializationContext, type_name: str, value: Any) -> None:
    """Write an array element (raw mode)."""
    write_array_element_raw(writer, ctx, type_name, value)


def read_map_element(reader: Reader, ctx: SerializationContext, type_name: str) -> Any:
    """Read a map element based on type name."""
    return read_array_element(reader, ctx, type_name)


def write_map_element(writer: Writer, ctx: SerializationContext, type_name: str, value: Any) -> None:
    """Write a map element based on type name."""
    write_array_element(writer, ctx, type_name, value)


def read_persistence_blob(reader: Reader, ctx: SerializationContext) -> Any:
    """Read a PersistenceBlob (nested SaveData)."""
    from editor.model.save_data import SaveData

    size = reader.read_int32()
    container_offset = reader.position
    blob_data = reader.read_bytes(size)

    from editor.io.reader import Reader as BlobReader
    blob_reader = BlobReader(blob_data)

    # Check if this is a profile save (has SaveData) or world save (has PersistenceContainer)
    if ctx.class_path == '/Game/_Core/Blueprints/Base/BP_RemnantSaveGameProfile':
        return SaveData.read(
            blob_reader,
            has_package_version=True,
            has_top_level_asset_path=False,
            container_offset=container_offset,
            options=ctx.options,
        )
    else:
        from editor.model.persistence import PersistenceContainer
        return PersistenceContainer.read(blob_reader, ctx, container_offset)


def write_persistence_blob(writer: Writer, ctx: SerializationContext, value: Any) -> None:
    """Write a PersistenceBlob (nested SaveData)."""
    from editor.io.writer import Writer as BlobWriter
    from editor.model.save_data import SaveData

    blob_writer = BlobWriter()

    if isinstance(value, SaveData):
        value.write(blob_writer, container_offset=writer.position + 4)
    else:
        from editor.model.persistence import PersistenceContainer
        value.write(blob_writer, container_offset=writer.position + 4)

    blob_data = blob_writer.to_bytes()
    writer.write_int32(len(blob_data))
    writer.write_bytes(blob_data)
