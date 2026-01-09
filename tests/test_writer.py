"""
Tests for binary writer, especially FString encoding.
"""

from editor.io.writer import Writer


def test_fstring_ascii() -> None:
    """Test ASCII FString encoding."""
    writer = Writer()
    writer.write_fstring("Hello")

    data = writer.to_bytes()

    # Length should be 6 (5 chars + null terminator)
    assert data[0:4] == b'\x06\x00\x00\x00'
    # Content should be "Hello\0"
    assert data[4:10] == b'Hello\x00'


def test_fstring_none() -> None:
    """Test None FString encoding."""
    writer = Writer()
    writer.write_fstring(None)

    data = writer.to_bytes()

    # Should be just 0
    assert data == b'\x00\x00\x00\x00'


def test_fstring_utf16() -> None:
    """Test UTF-16 FString encoding.

    This tests the fix for the UTF-16 length bug where Python was writing
    -char_count instead of -2*char_count like C# does.
    """
    writer = Writer()
    # Use a string with non-ASCII character to trigger UTF-16 encoding
    writer.write_fstring("Héllo")

    data = writer.to_bytes()

    # Length should be negative: -2 * (5 chars + 1 null) = -12
    import struct
    length = struct.unpack('<i', data[0:4])[0]
    assert length == -12, f"UTF-16 length should be -12, got {length}"

    # Content should be UTF-16-LE encoded "Héllo" + null terminator
    content = data[4:]
    # "Héllo" in UTF-16-LE is 10 bytes, plus 2-byte null = 12 bytes
    assert len(content) == 12
    # Decode and verify (excluding null terminator)
    decoded = content[:-2].decode('utf-16-le')
    assert decoded == "Héllo"


def test_fstring_utf16_length_matches_csharp() -> None:
    """Verify UTF-16 length calculation matches C# implementation.

    C# code: Write(-2*(value.Length + 1))
    Python should do: write_int32(-2 * char_count) where char_count = len(value) + 1
    """
    import struct

    test_cases = [
        ("á", -4),      # 1 char + null = 2, * -2 = -4
        ("áé", -6),     # 2 chars + null = 3, * -2 = -6
        ("Tëst", -10),  # 4 chars + null = 5, * -2 = -10
    ]

    for text, expected_length in test_cases:
        writer = Writer()
        writer.write_fstring(text)
        data = writer.to_bytes()
        length = struct.unpack('<i', data[0:4])[0]
        assert length == expected_length, \
            f"For '{text}': expected length {expected_length}, got {length}"
