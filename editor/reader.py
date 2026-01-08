"""
Binary reader for Remnant 2 save files.

Handles reading of:
- Primitive types (int32, uint32, float, etc.)
- FString (length-prefixed strings)
- FName (indexed string references)
- Properties and PropertyBags
- SaveData structure navigation
"""

import struct
from dataclasses import dataclass, field
from typing import Any

from editor.log import log


@dataclass
class FName:
    """Reference to a string in the names table."""

    index: int
    number: int | None = None
    name: str = ''


@dataclass
class Property:
    """A property with name, type, and value."""

    name: str
    type_name: str
    size: int
    index: int
    value: Any = None


@dataclass
class SaveReader:
    """Binary reader with position tracking and names table."""

    data: bytes
    pos: int = 0
    names_table: list[str] = field(default_factory=list)

    def read_bytes(self, count: int) -> bytes:
        result = self.data[self.pos : self.pos + count]
        self.pos += count
        return result

    def read_int8(self) -> int:
        result = struct.unpack_from('<b', self.data, self.pos)[0]
        self.pos += 1
        return result

    def read_uint8(self) -> int:
        result = struct.unpack_from('<B', self.data, self.pos)[0]
        self.pos += 1
        return result

    def read_int16(self) -> int:
        result = struct.unpack_from('<h', self.data, self.pos)[0]
        self.pos += 2
        return result

    def read_uint16(self) -> int:
        result = struct.unpack_from('<H', self.data, self.pos)[0]
        self.pos += 2
        return result

    def read_int32(self) -> int:
        result = struct.unpack_from('<i', self.data, self.pos)[0]
        self.pos += 4
        return result

    def read_uint32(self) -> int:
        result = struct.unpack_from('<I', self.data, self.pos)[0]
        self.pos += 4
        return result

    def read_int64(self) -> int:
        result = struct.unpack_from('<q', self.data, self.pos)[0]
        self.pos += 8
        return result

    def read_uint64(self) -> int:
        result = struct.unpack_from('<Q', self.data, self.pos)[0]
        self.pos += 8
        return result

    def read_float(self) -> float:
        result = struct.unpack_from('<f', self.data, self.pos)[0]
        self.pos += 4
        return result

    def read_double(self) -> float:
        result = struct.unpack_from('<d', self.data, self.pos)[0]
        self.pos += 8
        return result

    def read_fstring(self) -> str | None:
        """Read a length-prefixed string (FString)."""
        length = self.read_int32()
        if length == 0:
            return None
        elif length < 0:
            # UTF-16 string
            char_count = -length
            raw = self.read_bytes((char_count - 1) * 2)
            self.read_uint16()  # null terminator
            return raw.decode('utf-16-le')
        else:
            # ASCII string
            raw = self.read_bytes(length - 1)
            self.read_uint8()  # null terminator
            return raw.decode('ascii', errors='replace')

    def read_fname(self) -> FName:
        """Read an FName (index into names table with optional number)."""
        index_with_flag = self.read_uint16()
        has_number = (index_with_flag & 0x8000) != 0
        index = index_with_flag & 0x7FFF

        number = None
        if has_number:
            number = self.read_int32()

        name = self.names_table[index] if index < len(self.names_table) else f'<index:{index}>'
        return FName(index=index, number=number, name=name)

    def read_guid(self) -> tuple[int, int, int, int]:
        """Read an FGuid (16 bytes)."""
        a = self.read_uint32()
        b = self.read_uint32()
        c = self.read_uint32()
        d = self.read_uint32()
        return (a, b, c, d)

    def seek(self, pos: int) -> None:
        self.pos = pos

    def tell(self) -> int:
        return self.pos


def read_names_table(reader: SaveReader, offset: int) -> list[str]:
    """Read the names table at the given offset."""
    saved_pos = reader.tell()
    reader.seek(offset)

    count = reader.read_uint32()
    names = []
    for _ in range(count):
        name = reader.read_fstring()
        names.append(name or '')

    log.debug(f'Read {len(names)} names from table')
    reader.seek(saved_pos)
    return names


def read_property_value(reader: SaveReader, type_name: str, size: int) -> Any:
    """Read a property value based on its type."""
    if type_name == 'IntProperty':
        reader.read_uint8()  # NoRaw byte
        return reader.read_int32()
    elif type_name == 'UInt32Property':
        reader.read_uint8()
        return reader.read_uint32()
    elif type_name == 'Int64Property':
        reader.read_uint8()
        return reader.read_int64()
    elif type_name == 'UInt64Property':
        reader.read_uint8()
        return reader.read_uint64()
    elif type_name == 'FloatProperty':
        reader.read_uint8()
        return reader.read_float()
    elif type_name == 'DoubleProperty':
        reader.read_uint8()
        return reader.read_double()
    elif type_name == 'BoolProperty':
        value = reader.read_uint8()
        reader.read_uint8()  # NoRaw byte
        return value != 0
    elif type_name == 'StrProperty':
        reader.read_uint8()
        return reader.read_fstring()
    elif type_name == 'NameProperty':
        reader.read_uint8()
        return reader.read_fname()
    elif type_name == 'ObjectProperty':
        reader.read_uint8()
        return reader.read_int32()  # Object index
    elif type_name == 'StructProperty':
        struct_type = reader.read_fname()
        reader.read_guid()  # GUID
        reader.read_uint8()  # Unknown
        return {'struct_type': struct_type.name, 'data_start': reader.tell(), 'size': size - 19}
    elif type_name == 'ArrayProperty':
        element_type = reader.read_fname()
        reader.read_uint8()  # Unknown
        count = reader.read_uint32()
        return {'element_type': element_type.name, 'count': count, 'data_start': reader.tell()}
    elif type_name == 'ByteProperty':
        enum_type = reader.read_fname()
        reader.read_uint8()
        if enum_type.name == 'None':
            return reader.read_uint8()
        else:
            return reader.read_fname()
    elif type_name == 'EnumProperty':
        enum_type = reader.read_fname()
        reader.read_uint8()
        return reader.read_fname()
    else:
        # Unknown type - skip the data
        log.debug(f'Unknown property type: {type_name}, size={size}')
        reader.read_bytes(size)
        return None


def read_property(reader: SaveReader) -> Property | None:
    """Read a single property. Returns None if "None" terminator reached."""
    name_fname = reader.read_fname()
    if name_fname.name == 'None':
        return None

    type_fname = reader.read_fname()
    size = reader.read_uint32()
    index = reader.read_uint32()

    value = read_property_value(reader, type_fname.name, size)

    return Property(
        name=name_fname.name,
        type_name=type_fname.name,
        size=size,
        index=index,
        value=value,
    )


def read_property_bag(reader: SaveReader) -> dict[str, Property]:
    """Read properties until "None" terminator."""
    properties = {}
    while True:
        prop = read_property(reader)
        if prop is None:
            break
        properties[prop.name] = prop
    return properties


@dataclass
class ObjectInfo:
    """Information about an object in the save."""

    object_path: str
    name: str
    outer_id: int
    properties_offset: int


def read_objects_table(reader: SaveReader, offset: int, count: int) -> list[ObjectInfo]:
    """Read the objects table."""
    saved_pos = reader.tell()
    reader.seek(offset)

    objects = []
    for _ in range(count):
        was_loaded = reader.read_uint8()
        if was_loaded == 0:
            object_path = reader.read_fstring() or ''
            name = reader.read_fname()
            outer_id = reader.read_uint32()
            objects.append(
                ObjectInfo(
                    object_path=object_path,
                    name=name.name,
                    outer_id=outer_id,
                    properties_offset=0,
                )
            )
        else:
            objects.append(
                ObjectInfo(
                    object_path='',
                    name='',
                    outer_id=0,
                    properties_offset=0,
                )
            )

    reader.seek(saved_pos)
    return objects
