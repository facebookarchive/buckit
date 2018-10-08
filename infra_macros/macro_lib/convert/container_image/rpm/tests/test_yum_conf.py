#!/usr/bin/env python3
import io
import textwrap
import unittest

from ..yum_conf import YumConfRepo, YumConfParser


class YumConfTestCase(unittest.TestCase):
    def setUp(self):
        # More output for easier debugging
        unittest.util._MAX_LENGTH = 12345
        self.maxDiff = 12345

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
        gpgkey=https://example.com/zupa
        \thttps://example.com/super/safe
        enabled=1
        ''')))

    def test_gen_repos(self):
        self.assertEqual([
            YumConfRepo('potato', 'file:///pot.at/to', ()),
            YumConfRepo(
                name='oleander',
                base_url='http://example.com/oleander',
                gpg_key_urls=(
                    'https://example.com/zupa',
                    'https://example.com/super/safe',
                ),
            ),
        ], list(self.yum_conf.gen_repos()))

    def test_modify_repos(self):
        out = io.StringIO()
        self.yum_conf.modify_repo_configs([YumConfRepo(
            name='potato',
            base_url='https://example.com/potato',
            gpg_key_urls=('file:///much/secure/so/hack_proof',),
        )], out)
        self.assertEqual(textwrap.dedent('''\
        [main]
        debuglevel = 2
        gpgcheck = 1

        [potato]
        baseurl = https://example.com/potato
        enabled = 1
        gpgkey = file:///much/secure/so/hack_proof

        [oleander]
        baseurl = http://example.com/oleander
        gpgkey = https://example.com/zupa
        \thttps://example.com/super/safe
        enabled = 1

        '''), out.getvalue())
