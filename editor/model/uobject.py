"""UObject and Component classes for save file parsing.

These match the C# lib.remnant2.saves/Model/UObject and Component structures.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from editor.log import log
from editor.model.parts import FName, SerializationContext, UObjectLoadedData
from editor.model.properties import PropertyBag

if TYPE_CHECKING:
    from editor.io.reader import Reader
    from editor.io.writer import Writer


@dataclass
class Variable:
    """A single variable in a Variables collection."""

    name: FName
    type_name: str
    value: Any

    # Type names indexed by enum value (byte)
    VAR_TYPE_NAMES = [
        'None',
        'BoolProperty',
        'IntProperty',
        'FloatProperty',
        'NameProperty',
    ]

    @classmethod
    def read(cls, reader: Reader, ctx: SerializationContext) -> Variable:
        """Read Variable from reader."""
        name = FName.read(reader, ctx.names_table)

        if name.name == 'None':
            raise ValueError('Unexpected None in variable')

        # Type is stored as enum byte, not FString
        enum_val = reader.read_uint8()
        if enum_val >= len(cls.VAR_TYPE_NAMES):
            log.warning(f'Unknown variable type enum: {enum_val}')
            type_name = 'None'
        else:
            type_name = cls.VAR_TYPE_NAMES[enum_val]

        # Read value based on type
        value = None
        if type_name == 'None':
            pass
        elif type_name == 'BoolProperty' or type_name == 'IntProperty':
            value = reader.read_uint32()
        elif type_name == 'FloatProperty':
            value = reader.read_float()
        elif type_name == 'NameProperty':
            value = FName.read(reader, ctx.names_table)

        return cls(name=name, type_name=type_name, value=value)

    def write(self, writer: Writer, ctx: SerializationContext) -> None:
        """Write Variable to writer."""
        self.name.write(writer, ctx)

        # Write type as enum byte
        try:
            enum_val = self.VAR_TYPE_NAMES.index(self.type_name)
        except ValueError:
            log.warning(f'Unknown variable type name: {self.type_name}, writing as None')
            enum_val = 0
        writer.write_uint8(enum_val)

        if self.type_name == 'None':
            pass
        elif self.type_name == 'BoolProperty' or self.type_name == 'IntProperty':
            writer.write_uint32(self.value)
        elif self.type_name == 'FloatProperty':
            writer.write_float(self.value)
        elif self.type_name == 'NameProperty':
            self.value.write(writer, ctx)


@dataclass
class Variables:
    """A collection of variables."""

    name: FName
    unknown: int  # uint64
    items: list[tuple[str, Variable]] = field(default_factory=list)
    _lookup: dict[str, Variable] = field(default_factory=dict, repr=False)

    @classmethod
    def read(cls, reader: Reader, ctx: SerializationContext) -> Variables:
        """Read Variables from reader."""
        name = FName.read(reader, ctx.names_table)
        unknown = reader.read_uint64()
        count = reader.read_int32()

        items = []
        lookup = {}
        for _ in range(count):
            var = Variable.read(reader, ctx)
            items.append((var.name.name, var))
            if var.name.name not in lookup:
                lookup[var.name.name] = var

        return cls(name=name, unknown=unknown, items=items, _lookup=lookup)

    def write(self, writer: Writer, ctx: SerializationContext) -> None:
        """Write Variables to writer."""
        self.name.write(writer, ctx)
        writer.write_uint64(self.unknown)
        writer.write_int32(len(self.items))

        for _, var in self.items:
            var.write(writer, ctx)

    def __getitem__(self, key: str) -> Variable:
        return self._lookup[key]

    def __contains__(self, key: str) -> bool:
        return key in self._lookup


@dataclass
class Component:
    """A component attached to an actor."""

    component_key: str
    properties: PropertyBag | None = None
    variables: Variables | None = None
    extra_data: bytes | None = None

    @classmethod
    def read(cls, reader: Reader, ctx: SerializationContext) -> Component:
        """Read Component from reader."""
        component_key = reader.read_fstring()
        if component_key is None:
            raise ValueError('Unexpected null component key')

        length = reader.read_int32()
        start = reader.position

        properties = None
        variables = None

        # Route based on component key
        if component_key in ('GlobalVariables', 'Variables', 'Variable',
                            'PersistenceKeys', 'PersistanceKeys1', 'PersistenceKeys1'):
            variables = Variables.read(reader, ctx)
        else:
            properties = PropertyBag.read(reader, ctx)

        # Check for extra data
        extra_data = None
        if reader.position != start + length:
            if reader.position > start + length:
                raise ValueError('Component read too much data')
            extra_data = reader.read_bytes(start + length - reader.position)
            if any(b != 0 for b in extra_data):
                log.warning(f'Non-zero extra data in component {component_key}')

        return cls(
            component_key=component_key,
            properties=properties,
            variables=variables,
            extra_data=extra_data,
        )

    def write(self, writer: Writer, ctx: SerializationContext) -> None:
        """Write Component to writer."""
        writer.write_fstring(self.component_key)

        # Write length placeholder
        length_pos = writer.position
        writer.write_int32(0)
        start = writer.position

        if self.variables is not None:
            self.variables.write(writer, ctx)
        elif self.properties is not None:
            self.properties.write(writer, ctx)

        if self.extra_data is not None:
            writer.write_bytes(self.extra_data)

        # Patch length
        end = writer.position
        writer.position = length_pos
        writer.write_int32(end - start)
        writer.position = end


@dataclass
class UObject:
    """A serialized Unreal object."""

    was_loaded: int  # byte
    object_path: str | None = None
    loaded_data: UObjectLoadedData | None = None
    object_index: int = 0
    properties: PropertyBag | None = None
    extra_properties_data: bytes | None = None
    is_actor: int = 0  # byte
    components: list[Component] | None = None

    @classmethod
    def read_header(cls, reader: Reader, ctx: SerializationContext, index: int) -> UObject:
        """Read UObject header (without data) from reader."""
        was_loaded = reader.read_uint8()

        # Determine object path
        if was_loaded != 0 and index == 0 and ctx.class_path is not None:
            object_path = ctx.class_path
        else:
            object_path = reader.read_fstring()

        loaded_data = None
        if was_loaded == 0:
            loaded_data = UObjectLoadedData.read(reader, ctx.names_table)

        return cls(
            was_loaded=was_loaded,
            object_path=object_path,
            loaded_data=loaded_data,
        )

    def read_data(self, reader: Reader, ctx: SerializationContext) -> None:
        """Read UObject data (properties and components)."""
        self.object_index = reader.read_int32()

        # Read properties
        length = reader.read_uint32()
        start = reader.position

        if length > 0:
            self.properties = PropertyBag.read(reader, ctx)

            # Check for extra data after properties
            if reader.position != start + length:
                if reader.position > start + length:
                    raise ValueError('Properties read too much data')
                self.extra_properties_data = reader.read_bytes(start + length - reader.position)
                if any(b != 0 for b in self.extra_properties_data):
                    log.debug(f'Non-zero extra properties data at offset {reader.position:x}')

        # Read actor flag and components
        self.is_actor = reader.read_uint8()
        if self.is_actor != 0:
            self.components = self._read_components(reader, ctx)

    @staticmethod
    def _read_components(reader: Reader, ctx: SerializationContext) -> list[Component]:
        """Read components list."""
        count = reader.read_uint32()
        components = []
        for _ in range(count):
            comp = Component.read(reader, ctx)
            components.append(comp)
        return components

    def write_header(self, writer: Writer, ctx: SerializationContext) -> None:
        """Write UObject header (without data)."""
        writer.write_uint8(self.was_loaded)

        # Write object path unless first loaded object with class path
        if self.was_loaded == 0 or self.object_index != 0 or ctx.class_path is None:
            writer.write_fstring(self.object_path)

        if self.was_loaded == 0 and self.loaded_data is not None:
            self.loaded_data.write(writer, ctx)

    def write_data(self, writer: Writer, ctx: SerializationContext) -> None:
        """Write UObject data (properties and components)."""
        writer.write_int32(self.object_index)

        # Write properties
        length_pos = writer.position
        writer.write_uint32(0)  # Placeholder

        if self.properties is not None:
            start = writer.position
            self.properties.write(writer, ctx)

            if self.extra_properties_data is not None:
                writer.write_bytes(self.extra_properties_data)

            # Patch length
            end = writer.position
            writer.position = length_pos
            writer.write_uint32(end - start)
            writer.position = end

        # Write actor flag and components
        writer.write_uint8(self.is_actor)
        if self.is_actor != 0 and self.components is not None:
            writer.write_uint32(len(self.components))
            for comp in self.components:
                comp.write(writer, ctx)
