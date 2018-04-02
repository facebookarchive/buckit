#!/usr/bin/env python3
#
# Copyright 2016-present, Facebook, Inc.
# All rights reserved.
#
# This source code is licensed under the BSD-style license found in the
# LICENSE file in the root directory of this source tree. An additional grant
# of patent rights can be found in the PATENTS file in the same directory.
'See the SubvolumeOnDisk docblock.'
import json
import logging
import os
import socket
import subprocess

from collections import namedtuple

log = logging.Logger(__name__)

# These constants can represent both JSON keys for
# serialization/deserialization, and namedtuple keys.  Legend:
#  (1) Field in the namedtuple SubvolumeOnDisk
#  (2) Parsed from the dictionary received from the image build tool's
#      option `--print-buck-plumbing`
#  (3) Output into the on-disk dictionary format
#  (4) Read from the on-disk dictionary format
_BTRFS_UUID = 'btrfs_uuid'  # (1-4)
_HOSTNAME = 'hostname'  # (1-4)
_SUBVOLUMES_DIR = 'subvolumes_dir'  # (1)
_SUBVOLUME_PATH = 'subvolume_path'  # (2) + SubvolumeOnDisk.subvolume_path()
_SUBVOLUME_NAME = 'subvolume_name'  # (1, 3-4)
_SUBVOLUME_VERSION = 'subvolume_version'  # (1, 3-4)
_DANGER = 'DANGER'  # (3)


def _warn_on_unknown_keys(d, known_keys):
    unknown_keys = known_keys - set(d.keys())
    if unknown_keys:
        log.warning(f'Unknown keys {unknown_keys} in {d}')  # pragma: no cover


def _btrfs_get_volume_props(subvolume_path):
    SNAPSHOTS = 'Snapshot(s)'
    props = {}
    # It's unfair to assume that the OS encoding is UTF-8, but our JSON
    # serialization kind of requires it, and Python3 makes it hyper-annoying
    # to work with bytestrings, so **shrug**.
    #
    # If this turns out to be a problem for a practical use case, we can add
    # `surrogateescape` all over the place, or even set
    # `PYTHONIOENCODING=utf-8:surrogateescape` in the environment.
    for l in subprocess.check_output([
        'sudo', 'btrfs', 'subvolume', 'show', subvolume_path,
    ]).decode('utf-8').split('\n')[1:]:  # Skip the header line
        if SNAPSHOTS in props:
            if l:  # Ignore the trailing empty line
                TABS = 4
                assert l[:TABS] == '\t' * TABS, 'Not a snapshot line' + repr(l)
                props[SNAPSHOTS].append(l[TABS:])
        else:
            k, v = l.strip().split(':', 1)
            k = k.rstrip(':')
            v = v.strip()
            if k == SNAPSHOTS:
                assert v == '', f'Should have nothing after ":" in: {l}'
                props[SNAPSHOTS] = []
            else:
                assert k not in props, f'{l} already had a value {props[k]}'
                props[k] = v
    return props


class SubvolumeOnDisk(namedtuple('SubvolumeOnDisk', [
    _BTRFS_UUID,
    _HOSTNAME,
    _SUBVOLUMES_DIR,
    _SUBVOLUME_NAME,
    _SUBVOLUME_VERSION,
])):
    '''
    This class stores a disk path to a btrfs subvolume (built image layer),
    together with some minimal metadata about the layer.  It knows how to:
     - parse the JSON output of the image build tool, containing the btrfs
       subvolume path and some btrfs metadata.
     - serialize & deserialize this metadata to a similar JSON format that
       can be safely used as as Buck output representing the subvolume.
    '''

    _KNOWN_KEYS = {
        _BTRFS_UUID,
        _HOSTNAME,
        _SUBVOLUME_NAME,
        _SUBVOLUME_VERSION,
        _DANGER,
    }

    def subvolume_path(self):
        return os.path.join(
            self.subvolumes_dir,
            f'{self.subvolume_name}:{self.subvolume_version}'
        )

    @classmethod
    def from_build_buck_plumbing(
        cls, plumbing_output, subvolumes_dir, subvolume_name, subvolume_version
    ):
        d = json.loads(plumbing_output.decode())
        _warn_on_unknown_keys(d, {
            _BTRFS_UUID,
            _HOSTNAME,
            _SUBVOLUME_PATH,
        })
        self = cls(**{
            _BTRFS_UUID: d.pop(_BTRFS_UUID),
            _HOSTNAME: d.pop(_HOSTNAME),
            _SUBVOLUMES_DIR: subvolumes_dir,
            _SUBVOLUME_NAME: subvolume_name,
            _SUBVOLUME_VERSION: subvolume_version,
        })
        subvolume_path = os.path.normpath(d.pop(_SUBVOLUME_PATH))
        expected_subvolume_path = os.path.normpath(self.subvolume_path())
        if subvolume_path != expected_subvolume_path:
            raise RuntimeError(
                f'Layer build returned unexpected subvolume_path '
                f'{subvolume_path} != {expected_subvolume_path} from {d}'
            )
        # NB: No `._validate_and_return()` here, since it is redundant with
        # the self-test that `to_serializable_dict()` will perform.
        # Mandatory validation would also slow down any code that might want
        # to just enumerate & read the refcounts directory.
        return self

    @classmethod
    def from_serializable_dict(cls, d, subvolumes_dir):
        return cls(**{
            _BTRFS_UUID: d[_BTRFS_UUID],
            _HOSTNAME: d[_HOSTNAME],
            _SUBVOLUME_NAME: d[_SUBVOLUME_NAME],
            _SUBVOLUME_VERSION: d[_SUBVOLUME_VERSION],
            _SUBVOLUMES_DIR: subvolumes_dir,
        })._validate_and_return()

    def to_serializable_dict(self):
        # `subvolumes_dir` is an absolute path to a known location inside
        # the repo.  We must not serialize it inside a Buck outputs, since
        # that will break if the repo is moved.  Instead, we always
        # recompute the path relative to the current subvolumes directory.
        d = {
            _BTRFS_UUID: self.btrfs_uuid,
            _HOSTNAME: self.hostname,
            _SUBVOLUME_NAME: self.subvolume_name,
            _SUBVOLUME_VERSION: self.subvolume_version,
            _DANGER: 'Do NOT edit manually: this can break future builds, or '
                'break refcounting, causing us to leak or prematurely destroy '
                'subvolumes.',
        }
        # Self-test -- there should be no way for this assertion to fail
        new_self = self.from_serializable_dict(d, self.subvolumes_dir)
        assert self == new_self, \
          f'Got {new_self} from {d}, when serializing {self}'
        return d

    @classmethod
    def from_json_file(cls, infile, subvolumes_dir):
        parsed_json = '<NO JSON PARSED>'
        try:
            parsed_json = json.load(infile)
            return cls.from_serializable_dict(
                parsed_json, subvolumes_dir
            )._validate_and_return()
        except json.JSONDecodeError as ex:
            raise RuntimeError(
                f'Parsing subvolume JSON from {infile}: {ex.doc}'
            ) from ex
        except Exception as ex:
            raise RuntimeError(
                f'Parsed subvolume JSON from {infile}: {parsed_json}'
            ) from ex

    def to_json_file(self, outfile):
        outfile.write(json.dumps(self.to_serializable_dict()))

    def _validate_and_return(self):
        cur_host = socket.getfqdn()
        if cur_host != self.hostname:
            raise RuntimeError(
                f'Subvolume {self} did not come from current host {cur_host}'
            )
        # This incidentally checks that the subvolume exists and is btrfs.
        volume_props = _btrfs_get_volume_props(self.subvolume_path())
        if volume_props['UUID'] != self.btrfs_uuid:
            raise RuntimeError(
                f'UUID in subvolume JSON {self} does not match that of the '
                f'actual subvolume {volume_props}'
            )
        return self
