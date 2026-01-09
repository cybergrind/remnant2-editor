"""Profile save file with nested PersistenceBlob support."""

from __future__ import annotations

import struct
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

from editor.compression import calculate_crc32, compress_save, decompress_save
from editor.io.reader import Reader
from editor.io.writer import Writer
from editor.log import log
from editor.model.memory import FileHeader, FTopLevelAssetPath, OffsetInfo, PackageVersion

if TYPE_CHECKING:
    pass


@dataclass
class ProfileSave:
    """Profile save file with proper handling of nested PersistenceBlob.

    This implementation preserves the entire blob as raw bytes and only
    performs surgical modifications to the names table entries.
    """

    file_header: FileHeader
    outer_package_version: PackageVersion
    outer_class_path: FTopLevelAssetPath
    outer_offset_info: OffsetInfo
    outer_names_table: list[str]

    # Raw data sections for round-trip (outer structure)
    _pre_blob_data: bytes = field(default=b'', repr=False)  # Data before blob size field
    _post_blob_data: bytes = field(default=b'', repr=False)  # Data after blob end
    _outer_objects_table: bytes = field(default=b'', repr=False)  # Raw objects table

    # Entire blob preserved as raw bytes
    _blob_data: bytes = field(default=b'', repr=False)

    # Parsed inner structure (for reading/modifying names)
    inner_offset_info: OffsetInfo | None = None
    inner_names_table: list[str] = field(default_factory=list)

    # Positions within blob for surgical patching
    _blob_names_table_start: int = 0  # Position of names count within blob

    # Track pending name modifications
    _pending_name_changes: dict[str, str] = field(default_factory=dict)

    @classmethod
    def load(cls, path: Path) -> ProfileSave:
        """Load a profile.sav file."""
        compressed = path.read_bytes()
        decompressed = decompress_save(compressed)
        return cls.from_decompressed(decompressed)

    @classmethod
    def from_decompressed(cls, data: bytes) -> ProfileSave:
        """Parse from decompressed data."""
        reader = Reader(data)

        # Parse FileHeader
        file_header = FileHeader.read(reader)
        log.debug(f'FileHeader: version={file_header.version}, build={file_header.build_number}')

        # Parse outer SaveData headers
        outer_package_version = PackageVersion.read(reader)
        outer_class_path = FTopLevelAssetPath.read(reader)
        outer_offset_info = OffsetInfo.read(reader)

        log.debug(f'Outer OffsetInfo: names={outer_offset_info.names}, objects={outer_offset_info.objects}')

        objects_data_start = reader.position

        # Read outer names table
        reader.position = int(outer_offset_info.names)
        outer_names_count = reader.read_int32()
        outer_names_table = []
        for _ in range(outer_names_count):
            outer_names_table.append(reader.read_fstring())

        # Read outer objects table (raw)
        reader.position = int(outer_offset_info.objects)
        outer_objects_table = reader.read_bytes(int(outer_offset_info.names) - int(outer_offset_info.objects))

        # Find PersistenceBlob
        blob_info = cls._find_persistence_blob(data, objects_data_start, int(outer_offset_info.objects))
        if blob_info is None:
            raise ValueError('PersistenceBlob not found in save file')

        blob_size_position, blob_start, blob_size = blob_info
        log.debug(f'Found PersistenceBlob: size_pos={blob_size_position}, start={blob_start}, size={blob_size}')

        # Store raw sections around the blob
        pre_blob_data = data[objects_data_start:blob_size_position]
        post_blob_data = data[blob_start + blob_size:int(outer_offset_info.objects)]

        # Store ENTIRE blob as raw bytes
        blob_data = data[blob_start:blob_start + blob_size]

        # Parse inner structure for reading names
        blob_reader = Reader(blob_data)
        PackageVersion.read(blob_reader)  # Skip, we preserve raw bytes
        inner_offset_info = OffsetInfo.read(blob_reader)

        log.debug(f'Inner OffsetInfo: names={inner_offset_info.names}, objects={inner_offset_info.objects}')

        # Read inner names table
        blob_names_table_start = int(inner_offset_info.names)
        blob_reader.position = blob_names_table_start
        inner_names_count = blob_reader.read_int32()
        inner_names_table = []
        for _ in range(inner_names_count):
            inner_names_table.append(blob_reader.read_fstring())

        log.debug(f'Inner names table: {inner_names_count} entries')

        return cls(
            file_header=file_header,
            outer_package_version=outer_package_version,
            outer_class_path=outer_class_path,
            outer_offset_info=outer_offset_info,
            outer_names_table=outer_names_table,
            _pre_blob_data=pre_blob_data,
            _post_blob_data=post_blob_data,
            _outer_objects_table=outer_objects_table,
            _blob_data=blob_data,
            inner_offset_info=inner_offset_info,
            inner_names_table=inner_names_table,
            _blob_names_table_start=blob_names_table_start,
        )

    @staticmethod
    def _find_persistence_blob(data: bytes, search_start: int, search_end: int) -> tuple[int, int, int] | None:
        """Find PersistenceBlob by scanning for inner OffsetInfo pattern.

        Returns:
            Tuple of (blob_size_position, blob_start, blob_size) or None
        """
        for pos in range(search_start, search_end - 28):
            try:
                names = struct.unpack_from('<q', data, pos)[0]
                version = struct.unpack_from('<I', data, pos + 8)[0]
                objects = struct.unpack_from('<q', data, pos + 12)[0]

                # Check if this could be a valid inner OffsetInfo
                if (1000 < names < 200000 and
                    0 < version < 10 and
                    0 < objects < names and
                    objects > 100):

                    # Blob structure: [size:4][PackageVersion:8][OffsetInfo:20]...
                    blob_start = pos - 8  # PackageVersion is before OffsetInfo
                    size_pos = blob_start - 4

                    if size_pos > search_start:
                        potential_size = struct.unpack_from('<i', data, size_pos)[0]
                        if 10000 < potential_size < 200000:
                            # Verify by checking names table
                            blob_data = data[blob_start:blob_start + potential_size]
                            if len(blob_data) >= names + 4:
                                names_count = struct.unpack_from('<i', blob_data, names)[0]
                                if 0 < names_count < 1000:
                                    return (size_pos, blob_start, potential_size)
            except struct.error:
                pass

        return None

    def _get_modified_blob(self) -> bytes:
        """Get the blob data with any pending name modifications applied.

        This method performs surgical patching of the blob:
        1. Finds and replaces all occurrences of old FStrings with new FStrings
           throughout the entire blob (names table and extra data)
        """
        if not self._pending_name_changes:
            return self._blob_data

        blob = bytearray(self._blob_data)

        # For each pending change, replace ALL occurrences of the old FString
        # This handles both the names table entry and any raw FString occurrences
        for old_name, new_name in self._pending_name_changes.items():
            old_fstring = self._encode_fstring(old_name)
            new_fstring = self._encode_fstring(new_name)

            # Search and replace all occurrences
            search_start = 0
            while True:
                pos = blob.find(old_fstring, search_start)
                if pos == -1:
                    break
                # Replace this occurrence
                log.debug(f'Replacing FString "{old_name}" at blob offset {pos}')
                blob = blob[:pos] + new_fstring + blob[pos + len(old_fstring):]
                search_start = pos + len(new_fstring)

        return bytes(blob)

    @staticmethod
    def _encode_fstring(value: str) -> bytes:
        """Encode a string as FString bytes."""
        if value is None:
            return struct.pack('<i', 0)

        # Check if ASCII
        if all(ord(c) < 128 for c in value):
            byte_count = len(value) + 1  # +1 for null
            return struct.pack('<i', byte_count) + value.encode('ascii') + b'\x00'
        else:
            # UTF-16
            char_count = len(value) + 1  # +1 for null
            return struct.pack('<i', -char_count) + value.encode('utf-16-le') + b'\x00\x00'

    def to_decompressed(self) -> bytes:
        """Serialize to decompressed bytes."""
        # Get the (possibly modified) blob
        blob_data = self._get_modified_blob()

        # Calculate size difference for offset adjustments
        original_blob_size = len(self._blob_data)
        new_blob_size = len(blob_data)
        blob_size_diff = new_blob_size - original_blob_size

        log.debug(f'Blob size: {original_blob_size} -> {new_blob_size} (diff: {blob_size_diff})')

        # Write outer structure
        outer_writer = Writer()

        # FileHeader placeholder
        placeholder_header = FileHeader(crc32=0, decompressed_size=0, version=self.file_header.version, build_number=self.file_header.build_number)
        placeholder_header.write(outer_writer)

        # Outer SaveData headers
        self.outer_package_version.write(outer_writer)
        self.outer_class_path.write(outer_writer)

        # Placeholder for outer OffsetInfo
        outer_offset_info_pos = outer_writer.position
        placeholder_outer_oi = OffsetInfo(names=0, version=self.outer_offset_info.version, objects=0)
        placeholder_outer_oi.write(outer_writer)

        # Pre-blob data
        outer_writer.write_bytes(self._pre_blob_data)

        # Blob size and data
        outer_writer.write_int32(len(blob_data))
        outer_writer.write_bytes(blob_data)

        # Post-blob data
        outer_writer.write_bytes(self._post_blob_data)

        # Record outer objects table position
        outer_objects_pos = outer_writer.position

        # Outer objects table
        outer_writer.write_bytes(self._outer_objects_table)

        # Record outer names table position
        outer_names_pos = outer_writer.position

        # Outer names table
        outer_writer.write_int32(len(self.outer_names_table))
        for name in self.outer_names_table:
            outer_writer.write_fstring(name)

        # Patch outer OffsetInfo
        outer_end_pos = outer_writer.position
        outer_writer.position = outer_offset_info_pos
        actual_outer_oi = OffsetInfo(
            names=outer_names_pos,
            version=self.outer_offset_info.version,
            objects=outer_objects_pos,
        )
        actual_outer_oi.write(outer_writer)
        outer_writer.position = outer_end_pos

        # Get data and patch FileHeader
        data = bytearray(outer_writer.to_bytes())

        # Patch DecompressedSize
        struct.pack_into('<i', data, 4, len(data))

        # Patch CRC32
        crc32 = calculate_crc32(bytes(data))
        struct.pack_into('<I', data, 0, crc32)

        return bytes(data)

    def to_compressed(self) -> bytes:
        """Serialize to compressed bytes."""
        decompressed = self.to_decompressed()
        return compress_save(decompressed)

    def save(self, path: Path) -> None:
        """Save to file."""
        compressed = self.to_compressed()
        path.write_bytes(compressed)

    def replace_inner_name(self, old_name: str, new_name: str) -> bool:
        """Replace a name in the inner (PersistenceBlob) names table.

        Uses surgical patching to preserve all other data in the blob.

        Args:
            old_name: Name to replace
            new_name: Replacement name

        Returns:
            True if replacement was successful
        """
        try:
            idx = self.inner_names_table.index(old_name)
            self.inner_names_table[idx] = new_name
            self._pending_name_changes[old_name] = new_name
            log.info(f'Replaced inner name "{old_name}" with "{new_name}" at index {idx}')
            return True
        except ValueError:
            log.error(f'Name "{old_name}" not found in inner names table')
            return False
