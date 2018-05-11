#!/usr/bin/env python2

# Copyright 2017-present, Facebook, Inc.
# All rights reserved.
#
# This source code is licensed under the BSD-style license found in the
# LICENSE file in the root directory of this source tree. An additional grant
# of patent rights can be found in the PATENTS file in the same directory.


"""
Rules for building documentation with Sphinx (sphinx-doc.org)

This provides two new targets:
    * sphinx_wiki
    * sphinx_manpage

Common Attributes:
    name: str
        Name of the buck target

    python_binary_deps: List[target]
    python_library_deps: List[target]
        list of python_binary dependencies to include in the link-tree

        Sphinx ``autodoc`` allows documents to reference doc-blocks from
        modules, classes, etc.  For python it does this by importing the
        modules.  This means the dependencies need to be assembled in the
        same PYTHONPATH, with all native library dependencies built, etc.

        It is important to differentiate between python_binary_deps and
        python_library_deps because we cannot do introspection on the targets
        themselves.  For ``python_binary`` we actually depend on the
        "{name}-library" target rather than the binary itself.

    apidoc_modules: Dict[module_path, destination_dir]
        ``sphinx-apidoc`` is a command many run to auto-generate ".rst" files
        for a Python package.  ``sphinx-apidoc`` runs and outputs a document
        tree, with ``.. automodule::`` and ``.. autoclass::`` references, which
        is used by the subsequent Sphinx run to build out docs for those
        modules, classes, functions, etc.

        The output if ``sphinx-apidoc`` is a directory tree of its own, which
        will merged in with the directory tree in ``srcs`` using ``rsync``.
        The destination directory will be the name of ``destination_dir``
        provided.

        Keep in mind ``sphinx-apidoc`` runs at the root of ``PYTHONPATH``.

        A rule like::
            apidoc_modules = {
                "mypackage/mymodule": "mymodule",
            }

        Will run ``sphinx-apidoc`` with the argument mypackage/mymodule,
        and merge the output into the "mymodule" subdirectory with the
        rest of ``srcs``.

    genrule_srcs: Dict[binary_target, destination_dir]
        Similar to ``apidoc_modules``, ``genrule_srcs`` provides a way to
        generate source files during the build.  The target needs to be a
        binary target (runnable with "$(exe {target}) $OUT"), and needs to
        accept a single argument "$OUT": the directory to write files to.

        The ``destination_dir`` is the sub-directory to merge the files
        into, alongside the declared ``srcs``.

    confpy: Dict[str, Union[bool, int, str, List, Dict]
        This provides a way to override or add settings to conf.py

        These need to serialize to JSON

    label: List[str]
        This provides a way to add one or more labels to the target, similar
        to ``label`` for ``genrule``

sphinx_wiki
----------
This utilizes the Sphinx "xml" builder to generate a document
compliant with the Docutils DTD

Attributes:
    srcs: List[Path]
        list of document source files (usually .rst or .md)

    wiki_root_path
        Base URI location for documents to reside

        This gets added to the conf.py, but typically is not used by Sphinx
        in the build process.  It is included here as metadata which can
        be used by other tools via ``buck query``.


sphinx_manpage
--------------
This utilizes the Sphinx "man" builder to generate a Unix `Manual Page`

Attributes:
    src: Path
        The path to the source file (usually .rst or .md)

    description: str
        A one-line description of the program suitable for the NAME section

    author: str
        The program author

    section: int
        The manpage ``section``, defaults to ``1`` which is reserved for
        programs

    manpage_name: str [Optional]
        The name of the manpage to use.  The default is to use the target name
"""

from __future__ import absolute_import
from __future__ import division
from __future__ import print_function
from __future__ import unicode_literals

with allow_unsafe_import():  # noqa: magic
    import collections
    import json
    import os

FBSPHINX_WRAPPER = '//fbsphinx:fbsphinx'
SPHINX_WRAPPER = '//fbsphinx:sphinx'
SPHINXCONFIG_TGT = '//:.sphinxconfig'

if False:
    # avoid flake8 warnings for some things
    from . import (
        load,
        read_config,
        include_defs,
    )


def import_macro_lib(path):
    global _import_macro_lib__imported
    include_defs('{}/{}.py'.format(
        read_config('fbcode', 'macro_lib', '//macro_lib'), path
    ), '_import_macro_lib__imported')
    ret = _import_macro_lib__imported
    del _import_macro_lib__imported  # Keep the global namespace clean
    return ret


base = import_macro_lib('convert/base')
Rule = import_macro_lib('rule').Rule
python = import_macro_lib('convert/python')
fbcode_target = import_macro_lib('fbcode_target')
load("@fbcode_macros//build_defs:python_typing.bzl",
     "get_typing_config_target")
SPHINX_SECTION = 'sphinx'


class _SphinxConverter(base.Converter):
    """
    Produces a RuleTarget named after the base_path that points to the
    correct platform default as defined in data
    """
    def __init__(self, context):
        super(_SphinxConverter, self).__init__(context)

        self._converters = {
            'python_binary': python.PythonConverter(context, 'python_binary'),
        }

    def get_allowed_args(self):
        return {
            'name',
            'python_binary_deps',
            'python_library_deps',
            'apidoc_modules',
            'genrule_srcs',
            'confpy',
            'sphinxbuild_opts',
        }

    def get_buck_rule_type(self):
        return 'genrule'

    def _gen_genrule_srcs_rules(
        self,
        base_path,
        name,
        genrule_srcs,
    ):
        """
        A simple genrule wrapper for running some target which generates rst
        """
        if not genrule_srcs:
            return

        for target, outdir in genrule_srcs.items():
            rule = fbcode_target.parse_target(target, base_path)
            yield Rule('genrule', collections.OrderedDict((
                ('name', name + '-genrule_srcs-' + rule.name),
                ('out', outdir),
                ('bash', 'mkdir -p $OUT && $(exe {}) $OUT'.format(target)),
            )))

    def _gen_apidoc_rules(
        self,
        base_path,
        name,
        sphinx_wrapper_target,
        apidoc_modules,
    ):
        """
        A simple genrule wrapper for running sphinx-apidoc
        """
        if not apidoc_modules:
            return

        for module, outdir in apidoc_modules.items():
            command = ' '.join((
                'mkdir',
                '-p',
                '$OUT',
                '&&',
                'SPHINX_APIDOC_OPTIONS=members',
                '$(exe :{sphinx_wrapper_target})',
                'apidoc',
                '--output-dir=$OUT',
                '--follow-links',
                '--no-toc',
                '--implicit-namespaces',
                '{apidoc_root}',
            )).format(
                sphinx_wrapper_target=sphinx_wrapper_target,
                apidoc_root=os.path.join(
                    '..',
                    sphinx_wrapper_target + '#link-tree',
                    module[:].replace('.', '/'),
                )
            )
            yield Rule('genrule', collections.OrderedDict((
                ('name', name + '-apidoc-' + module),
                ('out', outdir),
                ('bash', command),
            )))

    def _get_confpy_rule(
        self,
        base_path,
        name,
        srcs,
        confpy,
        **kwargs
    ):
        """
        Simple genrule wrapper for running fbsphinx-confpy to create a conf.py
        """
        confpy = confpy or {}

        # add confpy extras
        confpy.update(self.get_extra_confpy_assignments(name, **kwargs))

        # add confpy metadata
        confpy['@CONFPY'] = dict(confpy)

        # add sources, let fbsphinx-confpy determine master_doc
        confpy['@srcs'] = srcs

        # add things to buildinfo, filter out None(s) later
        confpy['@BUILDINFO'] = {
            'target': '//{}:{}'.format(base_path, name),
            'target_base_path': base_path,
            'wiki_root_path': confpy.get('wiki_root_path', None),
        }
        for key, val in confpy['@BUILDINFO'].items():
            if val is None:
                del confpy['@BUILDINFO'][key]

        command = ' '.join((
            '$(exe {FBSPHINX_WRAPPER})',
            'buck confpy',  # wrapper subcommand
            '--sphinxconfig $(location {SPHINXCONFIG_TGT})',
            '--extras \'{json_extras}\'',
            '{srcs} > $OUT',
        )).format(
            FBSPHINX_WRAPPER=FBSPHINX_WRAPPER,
            SPHINXCONFIG_TGT=SPHINXCONFIG_TGT,
            json_extras=json.dumps(confpy),
            srcs=' '.join(srcs),
        )
        return Rule('genrule', collections.OrderedDict((
            ('name', name + '-conf_py'),
            ('out', 'conf.py'),
            ('bash', command),
        )))

    def convert(
        self,
        base_path,
        name,
        apidoc_modules=None,
        confpy=None,
        sphinxbuild_opts=None,
        genrule_srcs=None,
        python_binary_deps=(),
        python_library_deps=(),
        src=None,
        srcs=None,
        visibility=None,
        **kwargs
    ):
        """
        Entry point for converting sphinx rules
        """
        if srcs is None:
            srcs = [src]
        python_deps = tuple(python_library_deps) + tuple((
            _dep + '-library'
            for _dep
            in tuple(python_binary_deps) + (FBSPHINX_WRAPPER,)
        ))
        fbsphinx_wrapper_target = '%s-fbsphinx-wrapper' % name
        for rule in self._converters['python_binary'].convert(
            base_path,
            name=fbsphinx_wrapper_target,
            par_style='xar',
            py_version='>=3.6',
            main_module='fbsphinx.bin.fbsphinx_wrapper',
            deps=python_deps,
        ):
            yield rule
        sphinx_wrapper_target = '%s-sphinx-wrapper' % name
        for rule in self._converters['python_binary'].convert(
            base_path,
            name=sphinx_wrapper_target,
            par_style='xar',
            py_version='>=3.6',
            main_module='fbsphinx.bin.sphinx_wrapper',
            deps=python_deps,
        ):
            yield rule

        additional_doc_rules = []
        for rule in self._gen_apidoc_rules(
            base_path,
            name,
            sphinx_wrapper_target,
            apidoc_modules,
        ):
            additional_doc_rules.append(rule)
            yield rule

        for rule in self._gen_genrule_srcs_rules(
            base_path,
            name,
            genrule_srcs,
        ):
            additional_doc_rules.append(rule)
            yield rule

        confpy_rule = self._get_confpy_rule(
            name=name,
            base_path=base_path,
            srcs=srcs,
            confpy=confpy,
            **kwargs
        )
        yield confpy_rule

        command = ' '.join((
            'mkdir $OUT &&',
            '{rsync_additional_docs}',
            '$(exe :{fbsphinx_wrapper_target})',
            'buck build',
            '--confpy $(location {confpy_target})',
            '--builder {builder}',
            '--sphinxconfig $(location {SPHINXCONFIG_TGT})',
            '--extras {json_extras}',
            '.',  # source dir
            '$OUT',
        )).format(
            rsync_additional_docs=(
                'rsync -a {} $SRCDIR &&'.format(
                    ' '.join((
                        '$(location {})'.format(rule.target_name)
                        for rule
                        in additional_doc_rules
                    )),
                )
                if additional_doc_rules
                else ''
            ),
            fbsphinx_wrapper_target=fbsphinx_wrapper_target,
            builder=self.get_builder(),
            confpy_target=confpy_rule.target_name,
            SPHINXCONFIG_TGT=SPHINXCONFIG_TGT,
            json_extras=json.dumps(sphinxbuild_opts or {}),
        )

        yield Rule('genrule', collections.OrderedDict((
            ('name', name),
            ('type', self.get_fbconfig_rule_type()),
            ('out', 'builder=%s' % self.get_builder()),
            ('bash', command),
            ('srcs', srcs),
            ('labels', self.get_labels(name, **kwargs)),
        )))

    def get_labels(self, name, **kwargs):
        return ()

    def get_extra_confpy_assignments(self, name, **kwargs):
        return collections.OrderedDict()


class SphinxWikiConverter(_SphinxConverter):
    """
    Concrete class for converting sphinx_wiki rules
    """
    def get_allowed_args(self):
        allowed_args = super(SphinxWikiConverter, self).get_allowed_args()
        allowed_args.update({
            'srcs',
            'wiki_root_path',
        })
        return allowed_args

    def get_fbconfig_rule_type(self):
        return 'sphinx_wiki'

    def get_builder(self):
        return 'wiki'

    def get_labels(self, name, **kwargs):
        return (
            'wiki_root_path:%s' % kwargs.get('wiki_root_path'),
        )


class SphinxManpageConverter(_SphinxConverter):
    """
    Concrete class for converting sphinx_manpage rules
    """
    def get_allowed_args(self):
        allowed_args = super(SphinxManpageConverter, self).get_allowed_args()
        allowed_args.update({
            'src',
            'author',
            'description',
            'section',
            'manpage_name',
        })
        return allowed_args

    def get_fbconfig_rule_type(self):
        return 'sphinx_manpage'

    def get_builder(self):
        return 'manpage'

    def get_labels(self, name, **kwargs):
        return (
            'description:%s' % kwargs.get('description'),
            'author:%s' % kwargs.get('author'),
            'section:%d' % kwargs.get('section', 1),
            'manpage_name:%s' % kwargs.get('manpage_name', name),
        )

    def get_extra_confpy_assignments(self, name, **kwargs):
        return {
            'man_pages': [{
                'doc': 'master_doc',
                'name': kwargs.get('manpage_name', name),
                'description': kwargs.get('description'),
                'author': kwargs.get('author'),
                'section': kwargs.get('section', 1),
            }],
        }
