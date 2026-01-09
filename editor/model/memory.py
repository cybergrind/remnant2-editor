"""Fixed-size memory structures for save file parsing.

These match the C# lib.remnant2.saves memory structures.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from editor.io.reader import Reader
    from editor.io.writer import Writer


@dataclass
class OffsetInfo:
    """Offset information structure (20 bytes).

    Contains exact positions of Names and Objects tables within SaveData.
    This is the key to proper structured parsing - no guessing needed.
    """

    names: int  # int64 - offset to names table
    version: int  # uint32 - version number
    objects: int  # int64 - offset to objects table

    SIZE = 20

    @classmethod
    def read(cls, reader: Reader) -> OffsetInfo:
        """Read OffsetInfo from reader."""
        names = reader.read_int64()
        version = reader.read_uint32()
        objects = reader.read_int64()
        return cls(names=names, version=version, objects=objects)

    def write(self, writer: Writer) -> None:
        """Write OffsetInfo to writer."""
        writer.write_int64(self.names)
        writer.write_uint32(self.version)
        writer.write_int64(self.objects)


@dataclass
class FileHeader:
    """File header structure (16 bytes).

    Present at the start of decompressed save data.
    """

    crc32: int  # uint32 - CRC32 of data after header
    decompressed_size: int  # int32 - total decompressed size
    version: int  # int32 - format version (always 9)
    build_number: int  # int32 - game build number

    SIZE = 16

    @classmethod
    def read(cls, reader: Reader) -> FileHeader:
        """Read FileHeader from reader."""
        crc32 = reader.read_uint32()
        decompressed_size = reader.read_int32()
        version = reader.read_int32()
        build_number = reader.read_int32()
        return cls(
            crc32=crc32,
            decompressed_size=decompressed_size,
            version=version,
            build_number=build_number,
        )

    def write(self, writer: Writer) -> None:
        """Write FileHeader to writer."""
        writer.write_uint32(self.crc32)
        writer.write_int32(self.decompressed_size)
        writer.write_int32(self.version)
        writer.write_int32(self.build_number)


@dataclass
class FGuid:
    """Unreal GUID structure (16 bytes)."""

    a: int  # uint32
    b: int  # uint32
    c: int  # uint32
    d: int  # uint32

    SIZE = 16

    @classmethod
    def read(cls, reader: Reader) -> FGuid:
        """Read FGuid from reader."""
        return cls(
            a=reader.read_uint32(),
            b=reader.read_uint32(),
            c=reader.read_uint32(),
            d=reader.read_uint32(),
        )

    def write(self, writer: Writer) -> None:
        """Write FGuid to writer."""
        writer.write_uint32(self.a)
        writer.write_uint32(self.b)
        writer.write_uint32(self.c)
        writer.write_uint32(self.d)

    @classmethod
    def empty(cls) -> FGuid:
        """Create an empty (zero) GUID."""
        return cls(a=0, b=0, c=0, d=0)

    def is_empty(self) -> bool:
        """Check if GUID is all zeros."""
        return self.a == 0 and self.b == 0 and self.c == 0 and self.d == 0


@dataclass
class PackageVersion:
    """Package version structure (8 bytes)."""

    ue_version: int  # int32
    ue_licensee_version: int  # int32

    SIZE = 8

    @classmethod
    def read(cls, reader: Reader) -> PackageVersion:
        """Read PackageVersion from reader."""
        return cls(
            ue_version=reader.read_int32(),
            ue_licensee_version=reader.read_int32(),
        )

    def write(self, writer: Writer) -> None:
        """Write PackageVersion to writer."""
        writer.write_int32(self.ue_version)
        writer.write_int32(self.ue_licensee_version)


@dataclass
class FTopLevelAssetPath:
    """Top-level asset path (two FStrings)."""

    package_name: str | None
    asset_name: str | None

    @classmethod
    def read(cls, reader: Reader) -> FTopLevelAssetPath:
        """Read FTopLevelAssetPath from reader."""
        return cls(
            package_name=reader.read_fstring(),
            asset_name=reader.read_fstring(),
        )

    def write(self, writer: Writer) -> None:
        """Write FTopLevelAssetPath to writer."""
        writer.write_fstring(self.package_name)
        writer.write_fstring(self.asset_name)

    @property
    def path(self) -> str | None:
        """Get the full path string."""
        return self.package_name


@dataclass
class FVector:
    """Unreal 3D vector (24 bytes - 3 doubles)."""

    x: float
    y: float
    z: float

    SIZE = 24

    @classmethod
    def read(cls, reader: Reader) -> FVector:
        """Read FVector from reader."""
        return cls(
            x=reader.read_double(),
            y=reader.read_double(),
            z=reader.read_double(),
        )

    def write(self, writer: Writer) -> None:
        """Write FVector to writer."""
        writer.write_double(self.x)
        writer.write_double(self.y)
        writer.write_double(self.z)

    @classmethod
    def zero(cls) -> FVector:
        """Create a zero vector."""
        return cls(x=0.0, y=0.0, z=0.0)


@dataclass
class FQuaternion:
    """Unreal quaternion (32 bytes - 4 doubles)."""

    x: float
    y: float
    z: float
    w: float

    SIZE = 32

    @classmethod
    def read(cls, reader: Reader) -> FQuaternion:
        """Read FQuaternion from reader."""
        return cls(
            x=reader.read_double(),
            y=reader.read_double(),
            z=reader.read_double(),
            w=reader.read_double(),
        )

    def write(self, writer: Writer) -> None:
        """Write FQuaternion to writer."""
        writer.write_double(self.x)
        writer.write_double(self.y)
        writer.write_double(self.z)
        writer.write_double(self.w)

    @classmethod
    def identity(cls) -> FQuaternion:
        """Create an identity quaternion."""
        return cls(x=0.0, y=0.0, z=0.0, w=1.0)


@dataclass
class FRotator:
    """Unreal rotator (24 bytes - 3 doubles for pitch/roll/yaw)."""

    pitch: float
    roll: float
    yaw: float

    SIZE = 24

    @classmethod
    def read(cls, reader: Reader) -> FRotator:
        """Read FRotator from reader."""
        return cls(
            pitch=reader.read_double(),
            roll=reader.read_double(),
            yaw=reader.read_double(),
        )

    def write(self, writer: Writer) -> None:
        """Write FRotator to writer."""
        writer.write_double(self.pitch)
        writer.write_double(self.roll)
        writer.write_double(self.yaw)


@dataclass
class FTransform:
    """Unreal transform (rotation + position + scale = 88 bytes)."""

    rotation: FQuaternion
    position: FVector
    scale: FVector

    SIZE = 88

    @classmethod
    def read(cls, reader: Reader) -> FTransform:
        """Read FTransform from reader."""
        return cls(
            rotation=FQuaternion.read(reader),
            position=FVector.read(reader),
            scale=FVector.read(reader),
        )

    def write(self, writer: Writer) -> None:
        """Write FTransform to writer."""
        self.rotation.write(writer)
        self.position.write(writer)
        self.scale.write(writer)

    @classmethod
    def identity(cls) -> FTransform:
        """Create an identity transform."""
        return cls(
            rotation=FQuaternion.identity(),
            position=FVector.zero(),
            scale=FVector(x=1.0, y=1.0, z=1.0),
        )
