#!/usr/bin/env python3
import unittest

from leaf1.ttypes import Leaf1
from leaf2.ttypes import Leaf2
from parent.ttypes import Parent
from tupperware.thriftdoc.validator.validate_thriftdoc import ValidateThriftdoc


class ThrifdocPythonTest(unittest.TestCase):

    def test_valid_parent(self):
        ValidateThriftdoc().validate(
            Parent(first=Leaf1(leaf=5), second=Leaf2(leaf=17))
        )

    def test_error_parent(self):
        with self.assertRaises(Exception) as context:
            ValidateThriftdoc().validate(
                Parent(first=Leaf1(leaf=0), second=Leaf2(leaf=17))
            )
        self.assertIn(
            "validation failed at rule {'level': 'error', 'rule': 'leaf >= 1'}"
            "\nUser input is {'leaf': 0}",
            str(context.exception)
        )

    def NOT_IMPLEMENTED_test_warning_parent(self):
        ValidateThriftdoc().validate(
            Parent(first=Leaf1(leaf=99), second=Leaf2(leaf=1))
        )
