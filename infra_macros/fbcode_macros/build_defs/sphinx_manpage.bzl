load("@fbcode_macros//build_defs/lib:sphinx_common.bzl", "sphinx_common")

def sphinx_manpage(
        name,
        apidoc_modules = None,
        config = None,
        genrule_srcs = None,
        python_binary_deps = (),
        python_library_deps = (),
        srcs = None,
        author = None,
        description = None,
        section = 1,
        manpage_name = None,
        visibility = None):
    """Utilizes the Sphinx "man" builder to generate a Unix `Manual Page`.

    Args:
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
    _ignore = visibility
    base_path = native.package_name()
    manpage_name = manpage_name or name
    sphinx_common.sphinx_rule(
        base_path = base_path,
        name = name,
        rule_type = "sphinx_manpage",
        builder = "manpage",
        labels = (
            "description:" + description,
            "author:" + author,
            "section:{}".format(section),
            "manpage_name:" + manpage_name,
        ),
        apidoc_modules = apidoc_modules,
        config = config,
        genrule_srcs = genrule_srcs,
        python_binary_deps = python_binary_deps,
        python_library_deps = python_library_deps,
        srcs = srcs,
    )
