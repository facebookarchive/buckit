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
                "mypackage.mymodule": "mymodule",
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

    config: Dict[str, Dict[str, Union[bool, int, str, List, Dict]]
        This provides a way to override or add settings to conf.py,
        sphinx-build and others

        Section headers:
            conf.py
            sphinx-build
            sphinx-apidoc

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
"""

from __future__ import absolute_import, division, print_function, unicode_literals

FBSPHINX_WRAPPER = "//fbsphinx:buck"
SPHINXCONFIG_TGT = "//:.sphinxconfig"

if False:
    # avoid flake8 warnings for some things
    from . import load, read_config, include_defs


def import_macro_lib(path):
    global _import_macro_lib__imported
    include_defs(
        "{}/{}.py".format(read_config("fbcode", "macro_lib", "//macro_lib"), path),
        "_import_macro_lib__imported",
    )
    ret = _import_macro_lib__imported
    del _import_macro_lib__imported  # Keep the global namespace clean
    return ret


base = import_macro_lib("convert/base")

load("@fbcode_macros//build_defs/lib:target_utils.bzl", "target_utils")
load("@fbcode_macros//build_defs/lib:sphinx_common.bzl", "sphinx_common")
load("@fbsource//tools/build_defs:fb_native_wrapper.bzl", "fb_native")
load("@fbcode_macros//build_defs:python_binary.bzl", "python_binary")


class _SphinxConverter(base.Converter):
    """
    Produces a RuleTarget named after the base_path that points to the
    correct platform default as defined in data
    """

    def __init__(self):
        super(_SphinxConverter, self).__init__()

    def get_allowed_args(self):
        return {
            "apidoc_modules",
            "config",
            "genrule_srcs",
            "name",
            "python_binary_deps",
            "python_library_deps",
            "srcs",
        }

    def get_buck_rule_type(self):
        return "genrule"

    def convert(
        self,
        base_path,
        name,
        apidoc_modules=None,
        config=None,
        genrule_srcs=None,
        python_binary_deps=(),
        python_library_deps=(),
        srcs=None,
        visibility=None,
        **kwargs
    ):
        """
        Entry point for converting sphinx rules
        """

        sphinx_common.sphinx_rule(
            base_path=base_path,
            name=name,
            rule_type=self.get_fbconfig_rule_type(),
            builder=self.get_builder(),
            labels=self.get_labels(name, **kwargs),
            apidoc_modules=apidoc_modules,
            config=config,
            genrule_srcs=genrule_srcs,
            python_binary_deps=python_binary_deps,
            python_library_deps=python_library_deps,
            srcs=srcs
        )

        return []


class SphinxWikiConverter(_SphinxConverter):
    """
    Concrete class for converting sphinx_wiki rules
    """

    def get_allowed_args(self):
        allowed_args = super(SphinxWikiConverter, self).get_allowed_args()
        allowed_args.update({"wiki_root_path"})
        return allowed_args

    def get_fbconfig_rule_type(self):
        return "sphinx_wiki"

    def get_builder(self):
        return "wiki"

    def get_labels(self, name, **kwargs):
        return ("wiki_root_path:%s" % kwargs.get("wiki_root_path"),)


class SphinxManpageConverter(_SphinxConverter):
    """
    Concrete class for converting sphinx_manpage rules
    """

    def get_allowed_args(self):
        allowed_args = super(SphinxManpageConverter, self).get_allowed_args()
        allowed_args.update(
            {"author", "description", "section", "manpage_name"}
        )
        return allowed_args

    def get_fbconfig_rule_type(self):
        return "sphinx_manpage"

    def get_builder(self):
        return "manpage"

    def get_labels(self, name, **kwargs):
        return (
            "description:%s" % kwargs.get("description"),
            "author:%s" % kwargs.get("author"),
            "section:%d" % kwargs.get("section", 1),
            "manpage_name:%s" % kwargs.get("manpage_name", name),
        )
