from librarian.errors import (LibError, DetectError, ExtractError, ScanError,
                              EncryptedError, BrokenFileError, LimitError, UnknownBookError)

def test_hierarchy():
    for exc in (ScanError, EncryptedError, BrokenFileError, LimitError):
        assert issubclass(exc, ExtractError)
    for exc in (DetectError, ExtractError, UnknownBookError):
        assert issubclass(exc, LibError)
