"""SaveFile - top-level entry point for save file operations."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from editor.compression import calculate_crc32, compress_save, decompress_save
from editor.io.reader import Reader
from editor.io.writer import Writer
from editor.model.memory import FileHeader
from editor.model.save_data import SaveData

if TYPE_CHECKING:
    pass


@dataclass
class SaveFile:
    """Complete save file with FileHeader and SaveData.

    Provides high-level load/save operations with compression handling.
    """

    file_header: FileHeader
    save_data: SaveData

    # Store raw bytes before SaveData for exact round-trip
    _pre_save_data: bytes

    @classmethod
    def load(cls, path: Path) -> SaveFile:
        """Load and decompress a save file.

        Args:
            path: Path to compressed save file

        Returns:
            Parsed SaveFile
        """
        compressed_data = path.read_bytes()
        return cls.from_compressed(compressed_data)

    @classmethod
    def from_compressed(cls, compressed_data: bytes) -> SaveFile:
        """Parse a save file from compressed bytes.

        Args:
            compressed_data: Compressed save file bytes

        Returns:
            Parsed SaveFile
        """
        decompressed = decompress_save(compressed_data)
        return cls.from_decompressed(decompressed)

    @classmethod
    def from_decompressed(cls, data: bytes) -> SaveFile:
        """Parse a save file from decompressed bytes.

        Args:
            data: Decompressed save file bytes

        Returns:
            Parsed SaveFile
        """
        reader = Reader(data)

        # Read FileHeader (16 bytes)
        file_header = FileHeader.read(reader)

        # Read SaveData
        save_data = SaveData.read(reader)

        # Store any bytes between FileHeader and SaveData (should be none, but preserve for safety)
        pre_save_data = b''  # FileHeader ends at 16, SaveData starts immediately after

        return cls(
            file_header=file_header,
            save_data=save_data,
            _pre_save_data=pre_save_data,
        )

    def to_decompressed(self) -> bytes:
        """Serialize to decompressed bytes with proper offsets and checksums.

        Returns:
            Decompressed save file bytes
        """
        writer = Writer()

        # Write placeholder FileHeader (will be patched)
        placeholder_header = FileHeader(crc32=0, decompressed_size=0, version=self.file_header.version, build_number=self.file_header.build_number)
        placeholder_header.write(writer)

        # Write any pre-SaveData bytes
        writer.write_bytes(self._pre_save_data)

        # Write SaveData
        self.save_data.write(writer)

        # Get data and patch header
        data = bytearray(writer.to_bytes())

        # Patch DecompressedSize at offset 4
        import struct

        struct.pack_into('<i', data, 4, len(data))

        # Patch CRC32 at offset 0 (calculated on bytes[4:])
        crc32 = calculate_crc32(bytes(data))
        struct.pack_into('<I', data, 0, crc32)

        return bytes(data)

    def to_compressed(self) -> bytes:
        """Serialize to compressed bytes.

        Returns:
            Compressed save file bytes
        """
        decompressed = self.to_decompressed()
        return compress_save(decompressed)

    def save(self, path: Path) -> None:
        """Save to file with compression.

        Args:
            path: Output file path
        """
        compressed = self.to_compressed()
        path.write_bytes(compressed)

    def replace_name(self, old_name: str, new_name: str) -> bool:
        """Replace a name in the names table.

        All references using the old name's index will now point to the new name.

        Args:
            old_name: Name to replace
            new_name: Replacement name

        Returns:
            True if replacement was successful, False if old_name not found
        """
        try:
            idx = self.save_data.names_table.index(old_name)
            self.save_data.names_table[idx] = new_name
            return True
        except ValueError:
            return False

    def get_persistence_blob(self) -> SaveData | None:
        """Get the inner PersistenceBlob SaveData if present.

        For profile saves, the PersistenceBlob contains character data
        including prism segments and inventory.

        Returns:
            Inner SaveData or None if not found
        """
        from editor.model.properties import StructProperty

        for obj in self.save_data.objects:
            if obj.properties:
                for name, prop in obj.properties.properties:
                    if prop.type_name.name == 'StructProperty':
                        if isinstance(prop.value, StructProperty):
                            if prop.value.type_name.name == 'PersistenceBlob':
                                inner = prop.value.value
                                if isinstance(inner, SaveData):
                                    return inner
        return None

    def replace_inner_name(self, old_name: str, new_name: str) -> bool:
        """Replace a name in the inner PersistenceBlob names table.

        This is used for modifying prism segments and other character data.

        Args:
            old_name: Name to replace
            new_name: Replacement name

        Returns:
            True if replacement was successful, False if old_name not found
        """
        inner = self.get_persistence_blob()
        if inner is None:
            return False

        try:
            idx = inner.names_table.index(old_name)
            inner.names_table[idx] = new_name
            return True
        except ValueError:
            return False

    def find_prism_segments(self) -> list[tuple[Any, str]]:
        """Find all prism segment FNames in the save file.

        Returns a list of (FName, segment_name) tuples for all prism segments.
        The FName objects can be modified directly to change segment names.

        Returns:
            List of (FName, segment_name) tuples
        """
        from editor.model.parts import FName
        from editor.model.properties import ArrayStructProperty, PropertyBag

        inner = self.get_persistence_blob()
        if inner is None:
            return []

        segments = []

        # Search through all objects in the inner SaveData
        for obj in inner.objects:
            if obj.properties is None:
                continue

            # Look for CurrentSegments property
            if 'CurrentSegments' not in obj.properties:
                continue

            segments_prop = obj.properties['CurrentSegments']
            if not isinstance(segments_prop.value, ArrayStructProperty):
                continue

            # Each item in the array is a PropertyBag containing RowName
            for item in segments_prop.value.items:
                if not isinstance(item, PropertyBag):
                    continue

                if 'RowName' not in item:
                    continue

                row_name_prop = item['RowName']
                if isinstance(row_name_prop.value, FName):
                    segments.append((row_name_prop.value, row_name_prop.value.name))

        return segments

    def modify_prism_segment(self, old_segment: str, new_segment: str) -> int:
        """Modify a prism segment by directly changing FName values.

        This approach matches the dotnet/WPF interface - it modifies the FName.name
        property directly. During serialization, the new name will be added to
        the names table automatically.

        Args:
            old_segment: Current segment name to replace
            new_segment: New segment name

        Returns:
            Number of modifications made
        """
        segments = self.find_prism_segments()
        count = 0

        for fname, name in segments:
            if name == old_segment:
                fname.name = new_segment
                count += 1

        return count
