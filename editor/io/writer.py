"""Binary writer with seek support for save file serialization."""

from __future__ import annotations

import io
import struct


class Writer:
    """Binary writer with seek support for two-pass offset patching."""

    def __init__(self) -> None:
        self._buffer = io.BytesIO()

    @property
    def position(self) -> int:
        """Current write position."""
        return self._buffer.tell()

    @position.setter
    def position(self, value: int) -> None:
        """Seek to position."""
        self._buffer.seek(value)

    @property
    def size(self) -> int:
        """Current size of written data."""
        current = self._buffer.tell()
        self._buffer.seek(0, 2)  # Seek to end
        size = self._buffer.tell()
        self._buffer.seek(current)  # Restore position
        return size

    def to_bytes(self) -> bytes:
        """Get all written data as bytes."""
        return self._buffer.getvalue()

    def write_bytes(self, data: bytes) -> None:
        """Write raw bytes."""
        self._buffer.write(data)

    def write_int8(self, value: int) -> None:
        """Write signed 8-bit integer."""
        self._buffer.write(struct.pack('<b', value))

    def write_uint8(self, value: int) -> None:
        """Write unsigned 8-bit integer."""
        self._buffer.write(struct.pack('<B', value))

    def write_int16(self, value: int) -> None:
        """Write signed 16-bit integer (little-endian)."""
        self._buffer.write(struct.pack('<h', value))

    def write_uint16(self, value: int) -> None:
        """Write unsigned 16-bit integer (little-endian)."""
        self._buffer.write(struct.pack('<H', value))

    def write_int32(self, value: int) -> None:
        """Write signed 32-bit integer (little-endian)."""
        self._buffer.write(struct.pack('<i', value))

    def write_uint32(self, value: int) -> None:
        """Write unsigned 32-bit integer (little-endian)."""
        self._buffer.write(struct.pack('<I', value))

    def write_int64(self, value: int) -> None:
        """Write signed 64-bit integer (little-endian)."""
        self._buffer.write(struct.pack('<q', value))

    def write_uint64(self, value: int) -> None:
        """Write unsigned 64-bit integer (little-endian)."""
        self._buffer.write(struct.pack('<Q', value))

    def write_float(self, value: float) -> None:
        """Write 32-bit float (little-endian)."""
        self._buffer.write(struct.pack('<f', value))

    def write_double(self, value: float) -> None:
        """Write 64-bit double (little-endian)."""
        self._buffer.write(struct.pack('<d', value))

    def write_bool(self, value: bool) -> None:
        """Write boolean (1 byte)."""
        self.write_uint8(1 if value else 0)

    def write_fstring(self, value: str | None) -> None:
        """Write Unreal FString.

        Automatically chooses ASCII or UTF-16 encoding based on content.
        Format:
        - None: write 0
        - ASCII: write positive length (including null) + bytes + null byte
        - UTF-16: write negative char count (including null) + UTF-16 bytes + null short

        Note: We match the C# lib.remnant2.saves format exactly.
        """
        if value is None:
            self.write_int32(0)
            return

        # Check if all characters are ASCII
        if all(ord(c) < 128 for c in value):
            # ASCII encoding
            byte_count = len(value) + 1  # +1 for null terminator
            self.write_int32(byte_count)
            self._buffer.write(value.encode('ascii'))
            self.write_uint8(0)  # null terminator
        else:
            # UTF-16 encoding - negative length indicates Unicode
            # C# writes: -2 * (value.Length + 1) = -2 * char_count
            char_count = len(value) + 1  # +1 for null terminator
            self.write_int32(-2 * char_count)
            self._buffer.write(value.encode('utf-16-le'))
            self.write_int16(0)  # null terminator (2 bytes)

    def write_zeros(self, count: int) -> None:
        """Write zero bytes (for placeholders)."""
        self._buffer.write(b'\x00' * count)
