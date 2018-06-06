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

import tests.utils
from tests.utils import dedent

class ExportFilesTest(tests.utils.TestCase):

    @tests.utils.with_project()
    def test_buck_export_file_handles_visibility(self, root):
        root.add_file("file1.sh", "echo file1")
        root.add_file("file2.sh", "echo file2")
        root.add_file("file3.sh", "echo file3")

        root.add_file(
            "BUCK",
            dedent(
                """\
            load("@fbcode_macros//build_defs:export_files.bzl",
                    "buck_export_file")
            buck_export_file(name="file1.sh")
            buck_export_file(name="file2.sh", visibility=["//..."])
            buck_export_file(name="file3.sh", visibility=None)
        """
            )
        )

        expected = dedent(
            """\
        export_file(
          name = "file1.sh",
          visibility = [
            "PUBLIC",
          ],
        )

        export_file(
          name = "file2.sh",
          visibility = [
            "//...",
          ],
        )

        export_file(
          name = "file3.sh",
          visibility = [
            "PUBLIC",
          ],
        )
        """
        )

        result = root.run_audit(["BUCK"])
        self.validateAudit({"BUCK": expected}, result)

    @tests.utils.with_project()
    def test_buck_export_file_exports_copy_mode_by_default(self, root):
        root.add_file("file1.sh", "echo file1")
        root.add_file("file2.sh", "echo file2")
        root.add_file("file3.sh", "echo file3")

        root.add_file(
            "BUCK",
            dedent(
                """\
            load("@fbcode_macros//build_defs:export_files.bzl",
                "buck_export_file")
            buck_export_file(name="file1.sh")
            buck_export_file(name="file2.sh", mode="reference")
            buck_export_file(name="file3.sh", mode="copy")
        """
            )
        )

        expected = dedent(
            """\
        export_file(
          name = "file1.sh",
          visibility = [
            "PUBLIC",
          ],
        )

        export_file(
          name = "file2.sh",
          mode = "reference",
          visibility = [
            "PUBLIC",
          ],
        )

        export_file(
          name = "file3.sh",
          mode = "copy",
          visibility = [
            "PUBLIC",
          ],
        )
        """
        )

        result = root.run_audit(["BUCK"])
        self.validateAudit({"BUCK": expected}, result)


    @tests.utils.with_project()
    def test_export_file_handles_visibility(self, root):
        root.add_file("file1.sh", "echo file1")
        root.add_file("file2.sh", "echo file2")
        root.add_file("file3.sh", "echo file3")

        root.add_file(
            "BUCK",
            dedent(
                """\
            load("@fbcode_macros//build_defs:export_files.bzl", "export_file")
            export_file(name="file1.sh")
            export_file(name="file2.sh", visibility=["//..."])
            export_file(name="file3.sh", visibility=None)
        """
            )
        )

        expected = dedent(
            """\
        export_file(
          name = "file1.sh",
          mode = "reference",
          visibility = [
            "PUBLIC",
          ],
        )

        export_file(
          name = "file2.sh",
          mode = "reference",
          visibility = [
            "//...",
          ],
        )

        export_file(
          name = "file3.sh",
          mode = "reference",
          visibility = [
            "PUBLIC",
          ],
        )
        """
        )

        result = root.run_audit(["BUCK"])
        self.validateAudit({"BUCK": expected}, result)

    @tests.utils.with_project()
    def test_exports_reference_mode_by_default(self, root):
        root.add_file("file1.sh", "echo file1")
        root.add_file("file2.sh", "echo file2")
        root.add_file("file3.sh", "echo file3")

        root.add_file(
            "BUCK",
            dedent(
                """\
            load("@fbcode_macros//build_defs:export_files.bzl", "export_file")
            export_file(name="file1.sh")
            export_file(name="file2.sh", mode="reference")
            export_file(name="file3.sh", mode="copy")
        """
            )
        )

        expected = dedent(
            """\
        export_file(
          name = "file1.sh",
          mode = "reference",
          visibility = [
            "PUBLIC",
          ],
        )

        export_file(
          name = "file2.sh",
          mode = "reference",
          visibility = [
            "PUBLIC",
          ],
        )

        export_file(
          name = "file3.sh",
          mode = "copy",
          visibility = [
            "PUBLIC",
          ],
        )
        """
        )

        result = root.run_audit(["BUCK"])
        self.validateAudit({"BUCK": expected}, result)

    @tests.utils.with_project()
    def test_export_files_exports_multiple_files(self, root):
        root.add_file("file1.sh", "echo file1")
        root.add_file("file2.sh", "echo file2")
        root.add_file("file3.sh", "echo file3")
        root.add_file("file4.sh", "echo file4")
        root.add_file("file5.sh", "echo file5")
        root.add_file("file6.sh", "echo file6")
        root.add_file(
            "BUCK",
            dedent(
                """\
            load("@fbcode_macros//build_defs:export_files.bzl", "export_files")
            export_files(["file1.sh", "file2.sh"])
            export_files(["file3.sh", "file4.sh"], visibility=[])
            export_files(["file5.sh", "file6.sh"], visibility=[], mode="copy")
        """
            )
        )
        expected = dedent(
            """\
        export_file(
          name = "file1.sh",
          mode = "reference",
          visibility = [
            "PUBLIC",
          ],
        )

        export_file(
          name = "file2.sh",
          mode = "reference",
          visibility = [
            "PUBLIC",
          ],
        )

        export_file(
          name = "file3.sh",
          mode = "reference",
        )

        export_file(
          name = "file4.sh",
          mode = "reference",
        )

        export_file(
          name = "file5.sh",
          mode = "copy",
        )

        export_file(
          name = "file6.sh",
          mode = "copy",
        )
        """
        )

        result = root.run_audit(["BUCK"])
        self.validateAudit({"BUCK": expected}, result)

    @tests.utils.with_project()
    def test_creates_typing_rule_if_enabled_in_config_and_params(self, root):
        root.add_file("file1.sh", "echo file1")
        root.add_file("file2.sh", "echo file2")
        root.update_buckconfig("python", "typing_config", "//python:typing")

        root.add_file(
            "BUCK",
            dedent(
                """\
            load("@fbcode_macros//build_defs:export_files.bzl", "export_file")
            export_file(name="file1.sh")
            export_file(name="file2.sh", create_typing_rule=False)
        """
            )
        )

        expected = dedent(
            """\
        export_file(
          name = "file1.sh",
          mode = "reference",
          visibility = [
            "PUBLIC",
          ],
        )

        genrule(
          name = "file1.sh-typing",
          cmd = "mkdir -p \\"$OUT\\"",
          out = "root",
          visibility = [
            "PUBLIC",
          ],
        )

        export_file(
          name = "file2.sh",
          mode = "reference",
          visibility = [
            "PUBLIC",
          ],
        )

        """
        )

        result = root.run_audit(["BUCK"])
        self.validateAudit({"BUCK": expected}, result)
