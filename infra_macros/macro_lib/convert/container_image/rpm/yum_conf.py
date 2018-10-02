#!/usr/bin/env python3
from configparser import ConfigParser
from typing import Mapping


class YumConfParser:
    # NB: The 'main' section in `yum.conf` acts similarly to ConfigParser's
    # magic 'DEFAULT', in that it provides default values for some of the
    # repo options.  I did not investigate this in enough detail to say that
    # setting `default_section='main'` would be appropriate.  Since this
    # code currently only cares about `baseurl`, this is good enough.
    _NON_REPO_SECTIONS = ['DEFAULT', 'main']

    def __init__(self, yum_conf: 'TextIO'):
        self._cp = ConfigParser()
        self._cp.read_file(yum_conf)

    def get_repo_to_baseurl(self) -> Mapping[str, str]:
        'Raises if repo names cannot be used as directory names.'
        repo_to_baseurl = {
            repo: cfg['baseurl']
                for repo, cfg in self._cp.items()
                    if repo not in self._NON_REPO_SECTIONS
        }
        for repo in repo_to_baseurl:
            assert '/' not in repo and '\0' not in repo, f'Bad repo {repo}'
        return repo_to_baseurl

    def replace_repo_baseurls(
        self, repo_to_baseurl: Mapping[str, str], out: 'TextIO',
    ):
        '''
        Outputs a new `yum.conf` file which has the same configuration
        data as the file consumed by `self.__init__`, except that in the
        specified repos, `baseurl` is replaced by the provided values.
        '''
        for non_repo_sec in self._NON_REPO_SECTIONS:
            assert non_repo_sec not in repo_to_baseurl
        cp_copy = ConfigParser()
        cp_copy.read_dict(self._cp)
        for repo, baseurl in repo_to_baseurl.items():
            cp_copy[repo]['baseurl'] = baseurl
        cp_copy.write(out)
