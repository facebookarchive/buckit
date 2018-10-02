#!/usr/bin/env python3
import io
import textwrap
import unittest

from ..yum_conf import YumConfParser


class YumConfTestCase(unittest.TestCase):
    def setUp(self):
        self.yum_conf = YumConfParser(io.StringIO(textwrap.dedent('''\
        # Unfortunately, comments are discarded by ConfigParser, but I don't
        # want to depend on `ConfigObj` or `iniparse` for this.
        [main]
        debuglevel=2
        gpgcheck=1

        [potato]
        baseurl=file:///pot.at/to
        enabled=1

        [oleander]
        baseurl=http://example.com/oleander
        enabled=1
        ''')))

    def test_get_urls(self):
        self.assertEqual({
            'potato': 'file:///pot.at/to',
            'oleander': 'http://example.com/oleander',
        }, self.yum_conf.get_repo_to_baseurl())

    def test_replace_urls(self):
        out = io.StringIO()
        self.yum_conf.replace_repo_baseurls(
            {'potato': 'https://example.com/potato'}, out
        )
        self.assertEqual(textwrap.dedent('''\
        [main]
        debuglevel = 2
        gpgcheck = 1

        [potato]
        baseurl = https://example.com/potato
        enabled = 1

        [oleander]
        baseurl = http://example.com/oleander
        enabled = 1

        '''), out.getvalue())
