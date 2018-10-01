#!/usr/bin/env python3

from .storage import Storage, StorageInput, StorageOutput

__all__ = [Storage, StorageInput, StorageOutput]

# Register implementations with Storage
from . import filesystem_storage  # noqa: F401
