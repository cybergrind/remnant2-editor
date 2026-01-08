"""
Remnant 2 save file compression/decompression.

Save files use zlib compression with chunked format:
- CompressedFileHeader (12 bytes): CRC32, DecompressedSize, Version
- Chunks: Each up to 65536 bytes uncompressed, with 49-byte headers
"""

import struct
import zlib
from dataclasses import dataclass

from editor.log import log


CHUNK_HEADER_MAGIC = 0x222222229E2A83C1
CHUNK_MAX_SIZE = 0x20000  # 131072 bytes
COMPRESSOR_ZLIB = 0x3
EXPECTED_VERSION = 9


@dataclass
class CompressedFileHeader:
    crc32: int
    decompressed_size: int
    version: int


@dataclass
class ChunkHeader:
    magic: int
    chunk_size: int
    compressor: int
    compressed_size: int
    decompressed_size: int


def read_compressed_header(data: bytes, offset: int = 0) -> tuple[CompressedFileHeader, int]:
    """Read the 12-byte compressed file header."""
    crc32, decompressed_size, version = struct.unpack_from('<IiI', data, offset)
    header = CompressedFileHeader(crc32=crc32, decompressed_size=decompressed_size, version=version)
    return header, offset + 12


def read_chunk_header(data: bytes, offset: int) -> tuple[ChunkHeader, int]:
    """Read the 49-byte chunk header."""
    # Format: uint64 magic, uint64 chunk_size, byte compressor,
    #         uint64 compressed1, uint64 decompressed1, uint64 compressed2, uint64 decompressed2
    magic, chunk_size, compressor = struct.unpack_from('<QQB', data, offset)
    offset += 17
    compressed1, decompressed1, _compressed2, _decompressed2 = struct.unpack_from('<QQQQ', data, offset)
    offset += 32

    header = ChunkHeader(
        magic=magic,
        chunk_size=chunk_size,
        compressor=compressor,
        compressed_size=compressed1,
        decompressed_size=decompressed1,
    )
    return header, offset


def decompress_save(data: bytes) -> bytes:
    """Decompress a Remnant 2 save file."""
    offset = 0

    # Read compressed file header
    header, offset = read_compressed_header(data, offset)
    log.debug(f'Compressed header: version={header.version}, size={header.decompressed_size}')

    if header.version != EXPECTED_VERSION:
        log.warning(f'Unexpected version {header.version}, expected {EXPECTED_VERSION}')

    # Decompress chunks (chunks start immediately after header, no padding)
    # The C# code reserves 8 bytes at the start of the output, then appends decompressed data.
    # Finally it writes CRC32 (4), DecompressedSize (4), Version (4) at positions 0, 4, 8.
    # So the final structure is:
    # [0-3]: CRC32
    # [4-7]: DecompressedSize
    # [8-11]: Version (from CompressedFileHeader, overwrites first 4 bytes of chunk data)
    # [12+]: Rest of decompressed data

    # First, decompress all chunks
    chunks_data = bytearray()
    while offset < len(data):
        chunk_header, offset = read_chunk_header(data, offset)

        if chunk_header.magic != CHUNK_HEADER_MAGIC:
            raise ValueError(f'Invalid chunk magic: {chunk_header.magic:#x}')

        if chunk_header.compressor != COMPRESSOR_ZLIB:
            raise ValueError(f'Unknown compressor: {chunk_header.compressor}')

        # Read compressed data
        compressed_data = data[offset : offset + chunk_header.compressed_size]
        offset += chunk_header.compressed_size

        # Decompress
        decompressed = zlib.decompress(compressed_data)
        if len(decompressed) != chunk_header.decompressed_size:
            raise ValueError(f'Decompressed size mismatch: {len(decompressed)} != {chunk_header.decompressed_size}')

        chunks_data.extend(decompressed)

    # Build the final output with header
    # The chunk data starts at position 8 in the output stream (skipping 8 bytes)
    # Then bytes 0-11 are overwritten with the header values
    output = bytearray(8 + len(chunks_data))
    output[8:] = chunks_data

    # Write the header values
    struct.pack_into('<I', output, 0, header.crc32)
    struct.pack_into('<i', output, 4, header.decompressed_size)
    struct.pack_into('<i', output, 8, header.version)

    log.debug(f'Decompressed {len(output)} bytes from {len(data)} bytes')
    return bytes(output)


def calculate_crc32(data: bytes) -> int:
    """
    Calculate CRC32 checksum for decompressed save data.

    The CRC32 is calculated on bytes [4:] of the decompressed data,
    skipping the first 4 bytes which store the CRC itself.

    Args:
        data: Decompressed save data

    Returns:
        CRC32 checksum as unsigned 32-bit integer
    """
    return zlib.crc32(data[4:]) & 0xFFFFFFFF


def verify_crc32(data: bytes) -> bool:
    """
    Verify the CRC32 checksum of decompressed save data.

    Args:
        data: Decompressed save data

    Returns:
        True if the stored CRC32 matches the calculated CRC32
    """
    stored_crc = struct.unpack_from('<I', data, 0)[0]
    calculated_crc = calculate_crc32(data)
    return stored_crc == calculated_crc


def update_crc32(data: bytearray) -> None:
    """
    Update the CRC32 checksum in decompressed save data.

    Modifies the first 4 bytes of data in-place with the new CRC32.

    Args:
        data: Decompressed save data (mutable bytearray)
    """
    crc = calculate_crc32(data)
    struct.pack_into('<I', data, 0, crc)
