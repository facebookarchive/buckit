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


sphinx_manpage
--------------
This utilizes the Sphinx "man" builder to generate a Unix `Manual Page`

Attributes:
    srcs: List[Path]
        A list of paths to the source file (usually .rst or .md)

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
Rule = import_macro_lib("rule").Rule
fbcode_target = import_macro_lib("fbcode_target")
load("@fbcode_macros//build_defs/lib:python_typing.bzl", "get_typing_config_target")
SPHINX_SECTION = "sphinx"

load("@fbcode_macros//build_defs/lib:target_utils.bzl", "target_utils")
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
            "name",
            "python_binary_deps",
            "python_library_deps",
            "apidoc_modules",
            "genrule_srcs",
            "config",
        }

    def get_buck_rule_type(self):
        return "genrule"

    def _gen_genrule_srcs_rules(self, base_path, name, genrule_srcs):
        """
        A simple genrule wrapper for running some target which generates rst
        """
        if not genrule_srcs:
            return []

        rules = []

        for target, outdir in genrule_srcs.items():
            rule = target_utils.parse_target(target, default_base_path=base_path)
            if "/" in outdir:
                root, rest = outdir.split("/", 1)
            else:
                root = outdir
                rest = "."
            rule_name = name + "-genrule_srcs-" + rule.name
            fb_native.genrule(
                name=rule_name,
                out=root,
                bash=" ".join(
                    (
                        "mkdir -p $OUT/{rest} &&",
                        "PYTHONWARNINGS=i $(exe {target})",
                        "$OUT/{rest}",
                    )
                ).format(target=target, rest=rest),
            )
            rules.append(rule_name)

        return rules

    def _gen_apidoc_rules(self, base_path, name, fbsphinx_buck_target, apidoc_modules):
        """
        A simple genrule wrapper for running sphinx-apidoc
        """
        if not apidoc_modules:
            return []

        rules = []

        for module, outdir in apidoc_modules.items():
            command = " ".join(
                (
                    "mkdir -p $OUT &&",
                    "PYTHONWARNINGS=i $(exe :{fbsphinx_buck_target})",
                    "buck apidoc",
                    module,
                    "$OUT",
                )
            ).format(fbsphinx_buck_target=fbsphinx_buck_target)
            rule_name = name + "-apidoc-" + module
            fb_native.genrule(
                name=rule_name,
                out=outdir,
                bash=command,
            )
            rules.append(rule_name)

        return rules

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
        python_deps = (
            tuple(python_library_deps)
            + tuple((_dep + "-library" for _dep in tuple(python_binary_deps)))
            + (FBSPHINX_WRAPPER,)
        )
        fbsphinx_buck_target = "%s-fbsphinx-buck" % name
        python_binary(
            name=fbsphinx_buck_target,
            par_style="xar",
            py_version=">=3.6",
            main_module="fbsphinx.bin.fbsphinx_buck",
            deps=python_deps,
        )

        additional_doc_rules = []

        additional_doc_rules.extend(
            self._gen_apidoc_rules(
                base_path, name, fbsphinx_buck_target, apidoc_modules
            )
        )

        additional_doc_rules.extend(
            self._gen_genrule_srcs_rules(base_path, name, genrule_srcs)
        )

        command = " ".join(
            (
                "echo {BUCK_NONCE} >/dev/null &&",
                "PYTHONWARNINGS=i $(exe :{fbsphinx_buck_target})",
                "buck run",
                "--target {target}",
                "--builder {builder}",
                "--sphinxconfig $(location {SPHINXCONFIG_TGT})",
                "--config '{config}'",
                "--generated-sources '{generated_sources}'",
                ".",  # source dir
                "$OUT",
            )
        ).format(
            BUCK_NONCE=read_config("sphinx", "buck_nonce", ""),
            fbsphinx_buck_target=fbsphinx_buck_target,
            target="//{}:{}".format(base_path, name),
            builder=self.get_builder(),
            SPHINXCONFIG_TGT=SPHINXCONFIG_TGT,
            config=struct(config=(config or {})).to_json(),
            generated_sources="[" + ",".join([
                "\"$(location :{})\"".format(rule)
                for rule in additional_doc_rules
            ]) + "]",
        )

        # fb_native rule adds extra labels that genrule fails to swallow
        native.genrule(
            name=name,
            type=self.get_fbconfig_rule_type(),
            out="builder=%s" % self.get_builder(),
            bash=command,
            srcs=srcs,
            labels=self.get_labels(name, **kwargs),
        )
        return []

    def get_labels(self, name, **kwargs):
        return ()

    def get_extra_confpy_assignments(self, name, **kwargs):
        return {}


class SphinxWikiConverter(_SphinxConverter):
    """
    Concrete class for converting sphinx_wiki rules
    """

    def get_allowed_args(self):
        allowed_args = super(SphinxWikiConverter, self).get_allowed_args()
        allowed_args.update({"srcs", "wiki_root_path"})
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
            {"srcs", "author", "description", "section", "manpage_name"}
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

    def get_extra_confpy_assignments(self, name, **kwargs):
        return {
            "man_pages": [
                {
                    "doc": "master_doc",
                    "name": kwargs.get("manpage_name", name),
                    "description": kwargs.get("description"),
                    "author": kwargs.get("author"),
                    "section": kwargs.get("section", 1),
                }
            ]
        }
