# Copyright 2016-present, Facebook, Inc.
# All rights reserved.
#
# This source code is licensed under the BSD-style license found in the
# LICENSE file in the root directory of this source tree. An additional grant
# of patent rights can be found in the PATENTS file in the same directory.

from __future__ import absolute_import
from __future__ import division
from __future__ import print_function
from __future__ import unicode_literals

import textwrap
import tests.utils


class ExportFilesTest(tests.utils.TestCase):
    maxDiff = None

    @tests.utils.with_project()
    def test_imports_third_party_lib(self, root):
        root.add_file("file1.sh", "echo file1")
        root.add_file("file2.sh", "echo file2")
        root.add_file("file3.sh", "echo file3")
        root.add_file("file4.sh", "echo file4")
        root.add_file("BUCK", textwrap.dedent('''\
            load("@fbcode_macros//build_defs:export_files.bzl", "export_files")
            export_files(["file1.sh", "file2.sh"])
            export_files(["file3.sh", "file4.sh"], visibility=[])
        ''').strip())
        expected = textwrap.dedent('''\
        export_file(
          name = "file1.sh",
          visibility = [
            "PUBLIC",
          ],
        )

        export_file(
          name = "file2.sh",
          visibility = [
            "PUBLIC",
          ],
        )

        export_file(
          name = "file3.sh",
        )

        export_file(
          name = "file4.sh",
        )
        ''').strip()

        result = root.run_audit(["BUCK"])
        self.validateAudit({"BUCK": expected}, result)
