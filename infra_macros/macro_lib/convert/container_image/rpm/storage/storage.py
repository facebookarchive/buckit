#!/usr/bin/env python3
'''
RPM files can be quite big, so we do not necessarily want to commit them
directly to a version control system (most do not cope well with
frequently-changing large binary blobs).

The Storage abstraction in this file (see class docblock) provides a way
of storing RPM blobs either on the local filesystem, or on a remote,
distributed large blob storage, in a transparent way.

Then, the only thing we then need to version is an index of "repo file" to
"storage ID", which is quite VCS-friendly when emitted as e.g. sorted JSON.
'''

import json

from typing import IO, Mapping


class StorageOutput:
    'Use .write() to add data to the blob being stored.'
    id: str   # Populated once we exit the `writer()` context
    _output: IO

    def __init__(self, *, output: IO):
        self._output = output

    def write(self, data: bytes):
        self._output.write(data)


class StorageInput:
    'Use .read() to get data from a previously stored blob.'
    _input: IO

    def __init__(self, *, input: IO):
        self._input = input

    def read(self, size=None):
        return self._input.read() if size is None else self._input.read(size)


class Storage:
    '''
    Base class for all storage implementations. See FilesystemStorage for
    a simple implementation. Usage:

        # Storage engines should take only plain-old-data keyword arguments,
        # so that they can be configured from outside Python code via
        # `parse_config`.  Parameters other than 'name' are engine-specific.
        storage = Storage.make('filesystem', base_dir=path)

        with storage.writer() as out:
            out.write('various')
            out.write('data')
        print(f'Stored as {out.id}')
        with storage.reader(out.id) as r:
            print(f'Read back: {r.read()}')
    '''

    NAME_TO_CLS: Mapping[str, 'Storage'] = {}

    def __init_subclass__(cls, storage_name: str, **kwargs):
        super().__init_subclass__(**kwargs)
        Storage.NAME_TO_CLS[storage_name] = cls

    @classmethod
    def parse_config(cls, json_cfg):
        'Uniform parsing for Storage configs e.g. on the command-line.'
        cfg = json.loads(json_cfg)
        cfg['name']  # KeyError if not set, or if not a dict
        return cfg

    @classmethod
    def make(cls, name, **kwargs):
        return cls.NAME_TO_CLS[name](**kwargs)
