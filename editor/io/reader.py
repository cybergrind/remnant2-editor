"""Binary reader with position tracking for save file parsing."""

from __future__ import annotations

import struct
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    pass


class Reader:
    """Binary reader with position tracking and little-endian support."""

    def __init__(self, data: bytes) -> None:
        self._data = data
        self._position = 0

    @property
    def position(self) -> int:
        """Current read position."""
        return self._position

    @position.setter
    def position(self, value: int) -> None:
        """Set read position."""
        if value < 0 or value > len(self._data):
            raise ValueError(f'Position {value} out of range [0, {len(self._data)}]')
        self._position = value

    @property
    def size(self) -> int:
        """Total size of data."""
        return len(self._data)

    @property
    def remaining(self) -> int:
        """Bytes remaining to read."""
        return len(self._data) - self._position

    def read_bytes(self, count: int) -> bytes:
        """Read raw bytes."""
        if self._position + count > len(self._data):
            raise ValueError(f'Cannot read {count} bytes at position {self._position}, only {self.remaining} remaining')
        result = self._data[self._position : self._position + count]
        self._position += count
        return result

    def read_int8(self) -> int:
        """Read signed 8-bit integer."""
        return struct.unpack('<b', self.read_bytes(1))[0]

    def read_uint8(self) -> int:
        """Read unsigned 8-bit integer."""
        return struct.unpack('<B', self.read_bytes(1))[0]

    def read_int16(self) -> int:
        """Read signed 16-bit integer (little-endian)."""
        return struct.unpack('<h', self.read_bytes(2))[0]

    def read_uint16(self) -> int:
        """Read unsigned 16-bit integer (little-endian)."""
        return struct.unpack('<H', self.read_bytes(2))[0]

    def read_int32(self) -> int:
        """Read signed 32-bit integer (little-endian)."""
        return struct.unpack('<i', self.read_bytes(4))[0]

    def read_uint32(self) -> int:
        """Read unsigned 32-bit integer (little-endian)."""
        return struct.unpack('<I', self.read_bytes(4))[0]

    def read_int64(self) -> int:
        """Read signed 64-bit integer (little-endian)."""
        return struct.unpack('<q', self.read_bytes(8))[0]

    def read_uint64(self) -> int:
        """Read unsigned 64-bit integer (little-endian)."""
        return struct.unpack('<Q', self.read_bytes(8))[0]

    def read_float(self) -> float:
        """Read 32-bit float (little-endian)."""
        return struct.unpack('<f', self.read_bytes(4))[0]

    def read_double(self) -> float:
        """Read 64-bit double (little-endian)."""
        return struct.unpack('<d', self.read_bytes(8))[0]

    def read_bool(self) -> bool:
        """Read boolean (1 byte)."""
        return self.read_uint8() != 0

    def read_fstring(self) -> str | None:
        """Read Unreal FString.

        Format:
        - length == 0: return None
        - length < 0: UTF-16 encoded, -length is char count including null
        - length > 0: ASCII encoded, length is byte count including null

        Returns:
            The string value, or None if length is 0.
        """
        length = self.read_int32()

        if length == 0:
            return None

        if length < 0:
            # UTF-16 encoded: -length is char count including null terminator
            char_count = -length
            # Read (char_count - 1) chars as UTF-16, then the null terminator
            data = self.read_bytes((char_count - 1) * 2)
            result = data.decode('utf-16-le')
            # Read and verify null terminator (2 bytes)
            null_term = self.read_int16()
            if null_term != 0:
                raise ValueError('Expected null terminator in FString')
            return result
        else:
            # ASCII encoded: length is byte count including null terminator
            # Read length-1 bytes, then the null byte
            data = self.read_bytes(length - 1)
            result = data.decode('ascii')
            # Read and verify null terminator
            null_term = self.read_uint8()
            if null_term != 0:
                raise ValueError('Expected null terminator in FString')
            return result

    def peek_bytes(self, count: int) -> bytes:
        """Peek at bytes without advancing position."""
        if self._position + count > len(self._data):
            raise ValueError(f'Cannot peek {count} bytes at position {self._position}')
        return self._data[self._position : self._position + count]

    def peek_uint32(self) -> int:
        """Peek at unsigned 32-bit integer without advancing position."""
        return struct.unpack('<I', self.peek_bytes(4))[0]

    def skip(self, count: int) -> None:
        """Skip bytes."""
        self._position += count
        if self._position > len(self._data):
            raise ValueError(f'Skip past end of data')
