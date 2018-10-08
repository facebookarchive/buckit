#!/usr/bin/env python3
from configparser import ConfigParser
from typing import Iterator, List, NamedTuple, Tuple


class YumConfRepo(NamedTuple):
    name: str
    base_url: str
    gpg_key_urls: Tuple[str]

    @classmethod
    def from_config_section(cls, name, cfg_sec):
        assert '/' not in name and '\0' not in name, f'Bad repo name {name}'
        return YumConfRepo(
            name=name,
            base_url=cfg_sec['baseurl'],
            gpg_key_urls=tuple(cfg_sec['gpgkey'].split('\n'))
                if 'gpgkey' in cfg_sec else (),
        )


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

    def gen_repos(self) -> Iterator[YumConfRepo]:
        'Raises if repo names cannot be used as directory names.'
        for repo, cfg in self._cp.items():
            if repo not in self._NON_REPO_SECTIONS:
                yield YumConfRepo.from_config_section(repo, cfg)

    def modify_repo_configs(self, repos: List[YumConfRepo], out: 'TextIO'):
        '''
        Outputs a new `yum.conf` file which has the same configuration data
        as the file consumed by `self.__init__`, except that the given repos
        get new config values from the specified YumConfRepo.  Any config
        keys we do not parse are left unchanged.

        WATCH OUT: Passing an empty repo list will leve the configuration
        UNCHANGED -- it will not delete repos from the configuration.  To
        turn off repos, you would instead want to set `enabled=0`.
        '''
        cp_copy = ConfigParser()
        cp_copy.read_dict(self._cp)
        for repo in repos:
            assert repo.name not in self._NON_REPO_SECTIONS
            cp_copy[repo.name]['baseurl'] = repo.base_url
            cp_copy[repo.name]['gpgkey'] = '\n'.join(repo.gpg_key_urls)
        cp_copy.write(out)
