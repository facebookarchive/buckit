#!/usr/bin/env python2

# Copyright 2016-present, Facebook, Inc.
# All rights reserved.
#
# This source code is licensed under the BSD-style license found in the
# LICENSE file in the root directory of this source tree. An additional grant
# of patent rights can be found in the PATENTS file in the same directory.


"""
Support for cython_library

cython_library will produced one or more cxx_python_extension targets
If there are no cython sources, then it will produce a cxx_library targets

We do this so we never produce empty.so files which cxx_python_extension
will do.
"""

from __future__ import absolute_import
from __future__ import division
from __future__ import print_function
from __future__ import unicode_literals

import collections
import itertools

with allow_unsafe_import():  # noqa: magic
    import os


# Hack to make internal Buck macros flake8-clean until we switch to buildozer.
def import_macro_lib(path):
    global _import_macro_lib__imported
    include_defs('{}/{}.py'.format(  # noqa: F821
        read_config('fbcode', 'macro_lib', '//macro_lib'), path  # noqa: F821
    ), '_import_macro_lib__imported')
    ret = _import_macro_lib__imported
    del _import_macro_lib__imported  # Keep the global namespace clean
    return ret


base = import_macro_lib('convert/base')
python = import_macro_lib('convert/python')
Rule = import_macro_lib('rule').Rule
load("@fbcode_macros//build_defs:cpp_library.bzl", "cpp_library")
load("@fbcode_macros//build_defs:cpp_python_extension.bzl", "cpp_python_extension")
load("@fbcode_macros//build_defs/lib:python_typing.bzl",
     "get_typing_config_target", "gen_typing_config")
load("@fbcode_macros//build_defs:auto_headers.bzl", "AutoHeaders")
load("@fbcode_macros//build_defs/lib:target_utils.bzl", "target_utils")
load("@fbcode_macros//build_defs/lib:src_and_dep_helpers.bzl", "src_and_dep_helpers")
load("@fbcode_macros//build_defs/lib:copy_rule.bzl", "copy_rule")
load("@fbcode_macros//build_defs:config.bzl", "config")

def split_matching_extensions(srcs, exts):
    """
    Split the lists/dict srcs/headers on the extensions.
    return those that match and those that don't

    The matches result is always a dict
    """

    # If you get a unicode then just return it as is.
    # Its a AutoHeaders
    if not srcs or isinstance(srcs, unicode):
        return ({}, srcs)

    if not isinstance(srcs, dict):
        srcs = collections.OrderedDict(((src, src) for src in srcs))

    matched = collections.OrderedDict()
    other = collections.OrderedDict()

    for src, dst in srcs.items():
        if dst.endswith(exts):
            matched[src] = dst
        else:
            other[src] = dst
    return matched, other


class Converter(base.Converter):
    LIB_SUFFIX = '__cython-lib'
    INCLUDES_SUFFIX = '__cython-includes'
    CONVERT_SUFFIX = '__cython'
    TYPING_SUFFIX = '__typing'

    SOURCE_EXTS = (
        '.pyx',
        '.py',
    )
    HEADER_EXTS = (
        '.pxd',
        '.pxi',
    )

    def __init__(self):
        super(Converter, self).__init__()
        self.python_library = python.PythonConverter(
            'python_library',
        )

    def get_fbconfig_rule_type(self):
        return 'cython_library'

    def get_source_with_path(self, package, src):
        """Attach the package to the src path to get a full module path"""
        return os.path.join(package, src_and_dep_helpers.get_source_name(src))

    def get_module_name_and_path(self, package, src):
        module_path = os.path.relpath(os.path.splitext(src)[0], package)
        module_name = os.path.basename(module_path)
        return module_name, module_path

    def gen_deps_tree(
        self, name, package, headers, deps
    ):
        """
        Every cython_library will have a cython-includes target to go
        along with it, it contains all of its headers and those of its
        deps.

        Get all pxd and pxi so we can do transitive deps
        """
        tree_suffix = self.INCLUDES_SUFFIX
        package_path = package.replace('.', '/')

        cmds = []
        # Merge the cython-includes from our parents into ours
        for dep in deps:
            cmds.append(
                'rsync -a $(location {}{})/ "$OUT"'.format(dep, tree_suffix)
            )
        files = []
        for header, dst in headers.items():
            dst = self.get_source_with_path(package_path, dst)
            cmds.append('mkdir -p `dirname $OUT/{}`'.format(dst))
            if header[0] in '@/:':
                # Generated, so copy into place from the genrule
                cmds.append('cp $(location {}) $OUT/{}'.format(header, dst))
                continue
            files.append(header)
            cmds.append('mv {} $OUT/{}'.format(header, dst))
        attrs = collections.OrderedDict()
        attrs['name'] = name + tree_suffix
        attrs['labels'] = ["generated"]
        attrs['out'] = os.curdir
        attrs['srcs'] = files
        # Use find to create a __init__ file so cython knows the directories
        # are packages
        cmds.append(
            'find "$OUT" -type d | xargs -I {} touch {}/__init__.pxd'
        )
        attrs['cmd'] = '\n'.join(cmds)
        return ':' + attrs['name'], Rule('genrule', attrs)

    def convert_src(
        self,
        base_path,
        parent,
        module_path,
        src,    # original, for passing to genrule
        flags,
        dst_src,  # src with final pkg path attached
        out_src,
    ):
        """
        This creates a genrule to run the cython transpiler. It returns
        the target name and the rule
        """

        cython_compiler = config.get_cython_compiler()
        attrs = collections.OrderedDict()
        attrs['name'] = os.path.join(parent + self.CONVERT_SUFFIX, module_path)
        attrs['out'] = os.curdir
        attrs['labels'] = ["generated"]

        cmds = []
        package_path = os.path.dirname(dst_src)
        # We need to make sure the pyx is located in its package path
        # so cython can correctly detect its import location
        if package_path:
            cmds.append('mkdir -p {}'.format(package_path))
            # Generate __init__ files so cython knows we have packages
            cmds.append(
                'find "{}" -type d | xargs -I %% touch %%/__init__.pxd'
                .format(package_path.split('/')[0])
            )

        if src[0] in '@/:':
            # Generated file copy it into place, don't use 'srcs' since
            # it has the path stripping bug for gen targets
            cmds.append('cp $(location {}) {}'.format(src, dst_src))
        else:
            # These are straight files so we pass them in via 'srcs'
            attrs['srcs'] = [src]
            if src != dst_src:
                cmds.append('mv {} {}'.format(src, dst_src))

        # Generate c/c++ source
        cmds.append(
            '$(exe {cython_compiler}) {flags} -o $OUT/{result} {pyx_file}'
            .format(
                cython_compiler=cython_compiler,
                result=out_src,
                flags=' '.join(flags),
                pyx_file=dst_src,
            )
        )

        # Insure an _api.h file is always generated
        cmds.append(
            'touch $OUT/{module}_api.h'
            .format(module=os.path.splitext(out_src)[0])
        )

        attrs['cmd'] = ' && '.join(cmds)

        # Return the name and genrule
        return ':' + attrs['name'], Rule('genrule', attrs)

    def prefix_target_copy_rule(
        self, prefix, target, in_src, out_src, visibility,
    ):
        """
        Copy a file from a {target} at location {in_src} to {out_src}
        The genrule will use {prefix}={out_src} for its target_name
        """
        name = '{}={}'.format(prefix, out_src)
        src = '$(location {})/{}'.format(target, in_src)
        copy_rule(
            src,
            name,
            out_src,
            labels = ["generated"],
            visibility = visibility,
        )
        return ':' + name

    def gen_typing_target(
        self,
        parent,
        base_path,
        package,
        types,
        typing_options,
    ):
        name = parent + self.TYPING_SUFFIX
        return ':' + name, self.python_library.convert(
            name=name,
            base_path=base_path,
            base_module=package,
            srcs=types,
            typing=True,
            typing_options=typing_options,
            tags=["generated"],
        )

    def py_normalize_externals(self, external_deps):
        """
        We normalize for py so we can pass them to cpp as externals deps
        for a cpp_python_extension.  So we parse them then turn them
        back into tuple form as expected by the convert method of cpp.py
        """
        for dep in external_deps:
            parsed, version = target_utils.parse_external_dep(dep, lang_suffix='-py')
            if parsed.repo is None:
                yield (parsed.base_path, version, parsed.name)
            else:
                yield (parsed.repo, parsed.base_path, version, parsed.name)

    def gen_extension_rule(
        self,
        base_path,
        parent,
        module_path,
        package,
        src,
        python_deps=(),
        python_external_deps=(),
        cpp_compiler_flags=(),
        raw_deps=(),
        visibility=None,
        name=None,
        tests=None,
    ):
        typing_rule_name_prefix = os.path.join(parent, module_path)
        name = name or typing_rule_name_prefix
        cpp_python_extension(
            name=name,
            base_module=package,
            module_name=os.path.basename(module_path),
            srcs=[src],
            deps=(
                [':' + parent + self.LIB_SUFFIX] +
                list(python_deps)
            ) + list(raw_deps),
            external_deps=tuple(
                self.py_normalize_externals(python_external_deps)
            ),
            compiler_flags=['-w'] + list(cpp_compiler_flags),
            visibility=visibility,
            tests=tests,
            typing_rule_name_prefix=typing_rule_name_prefix,
        )
        return ':' + name

    def gen_api_header(
        self, name, cython_name, module_path, module_name, api, visibility
    ):
        """
        If a cython module exposes an api then the enduser needs to
        add that module/path to the api list if they wish to make use of it.

        Cython API is a complex beast, its generated from a pyx/pxd so
        it is placed in the namespace how python modules are. but its used
        by C++ or C so the user may want it to be placed in a different location

        If that is the case they can use a dictionary instead of a list
        of api modules.

        thrift_py3 uses this to move it into the gen-py3 directory.
        ex: {'path/module': 'gen-py3/path/module'}
        """
        if isinstance(api, dict):
            api_map = api
        else:
            api_map = {k: module_path for k in api}

        api_suffix = '_api.h'
        dst = api_map.get(module_path)
        if dst:
            return self.prefix_target_copy_rule(
                name, cython_name, module_name + api_suffix, dst + api_suffix, visibility,
            )
        return None

    def gen_shared_lib(
        self, name, api_headers, deps, cpp_compiler_flags, cpp_deps,
        srcs, headers, header_namespace, cpp_external_deps, visibility,
    ):
        # Ok so cxx_library header map, is dst -> src
        # python_library is src -> dst
        # cython_library will follow python_library in this so we need to
        # convert one direction to the other
        if isinstance(headers, dict):
            headers = collections.OrderedDict(((v, k)
                                               for k, v in headers.items()))

        if api_headers:
            # Add all the api_headers to our headers
            if isinstance(headers, dict):
                headers.update({src_and_dep_helpers.get_source_name(h): h for h in api_headers})
            else:  # Its a list, if it was a unicode we would have rasied already
                headers.extend(api_headers)

        cpp_deps = list(cpp_deps)  # Incase its empty
        # All cython deps need to have their LIB targets added as a
        # dependency for our LIB TARGET
        for dep in deps:
            # We need to turn it back into fbcode targets for cpp_library
            cpp_deps.append(dep + self.LIB_SUFFIX)

        # We need to depend on libpython for the build
        cpp_external_deps = list(cpp_external_deps)
        cpp_external_deps.append(('python', None, 'python'))

        cpp_library(
            name=name + self.LIB_SUFFIX,
            srcs=list(srcs),  # cpp_library doesn't accept dict sources
            deps=cpp_deps,
            # TODO(T36778537): Cython-generated `*_api.h` headers aren't
            # modular.
            modular_headers=False,
            compiler_flags=cpp_compiler_flags,
            auto_headers=AutoHeaders.NONE,
            headers=headers,
            header_namespace=header_namespace,
            external_deps=cpp_external_deps,
            visibility=visibility,
            tags=["generated"],
        )

    def convert_rule(
        self,
        base_path,
        name,
        package=None,
        srcs=(),
        headers=(),
        header_namespace=None,
        deps=(),
        external_deps=(),
        cpp_deps=(),
        cpp_external_deps=(),
        cpp_compiler_flags=(),
        flags=(),
        api=(),
        generate_cpp=True,
        python_deps=(),
        python_external_deps=(),
        types=(),
        typing_options='',
        tests=(),
        visibility=None,
    ):
        # Empty srcs results in a cxx_library, not an cxx_python_extension
        # Used for gathering pxd files,
        # It also means it could not possibly depend on python code.
        if not srcs and (python_deps or python_external_deps):
            raise AttributeError('"python_deps" and "python_external_deps" '
                                 'cannot be used with empty "srcs"')

        if isinstance(headers, bytes):
            raise ValueError('"headers" must be a collection or AutoHeaders')

        if isinstance(headers, unicode) and api:
            raise ValueError('"api" and AutoHeaders can not be used together')

        def _get_visibility():
            if visibility and 'PUBLIC' not in visibility:
                # Make it harder to break subrules
                return ("//" + base_path + ":", ) + tuple(visibility)
            else:
                return visibility

        def set_visibility(rule):
            rule_visibility = _get_visibility()
            if rule_visibility:
                rule.attributes['visibility'] = rule_visibility
            return rule

        def set_tests(rule):
            if tests:
                rule.attributes.setdefault('tests', tests)
            return rule

        pyx_srcs, srcs = split_matching_extensions(srcs, self.SOURCE_EXTS)
        pxd_headers, headers = split_matching_extensions(
            headers, self.HEADER_EXTS)

        deps = [src_and_dep_helpers.convert_build_target(base_path, d) for d in deps]
        external_deps = [src_and_dep_helpers.convert_external_build_target(e)
                         for e in external_deps]

        python_deps = [src_and_dep_helpers.convert_build_target(base_path, d) for d in python_deps]

        # This is normally base_path if package is not set
        if package is None:
            package = base_path.replace('.', '/')

        deps_tree, deps_tree_rule = self.gen_deps_tree(
            name,
            package,
            pxd_headers,
            itertools.chain(deps, external_deps),
        )
        yield set_visibility(deps_tree_rule)

        # Set some default flags that everyone should use
        # Also Add instruct cython how to find its deps_tree
        flags = ('-3', '--fast-fail') + tuple(flags) + (
            '-I', '$(location {})'.format(deps_tree)
        )
        if generate_cpp:
            flags = flags + ('--cplus', )

        out_ext = '.cpp' if '--cplus' in flags else '.c'

        api_headers = []
        if pyx_srcs:
            extensions = []
            items = pyx_srcs.items()
            def _create_sos(pyx_src, pyx_dst, main_name, visibility, extra_deps, update_extensions, tests):
                pyx_dst = self.get_source_with_path(package, pyx_dst)
                module_name, module_path = self.get_module_name_and_path(
                    package, pyx_dst)
                out_src = module_name + out_ext
                # generate rule to convert source file.
                cython_name, cython_rule = self.convert_src(
                    base_path, name, module_path, pyx_src, flags, pyx_dst,
                    out_src
                )
                yield set_visibility(cython_rule)
                # Generate the copy_rule
                src_target = self.prefix_target_copy_rule(
                    name, cython_name, out_src, module_path + out_ext, _get_visibility(),
                )

                # generate an extension for the generated src
                so_target = self.gen_extension_rule(
                    base_path, name, module_path, os.path.dirname(pyx_dst),
                    src_target, python_deps, python_external_deps,
                    cpp_compiler_flags, raw_deps=extra_deps, visibility=visibility,
                    name=main_name, tests=tests,
                )

                # The fist extension will not be a sub extension
                # So we can have this rule be a cxx_python_extension
                # and not be an empty .so

                if update_extensions:
                    extensions.append(so_target)

                # Generate _api.h header rules.
                api_target = self.gen_api_header(
                    name, cython_name, module_path, module_name, api, _get_visibility(),
                )
                if api_target:
                    api_headers.append(api_target)

            subrule_visibility = _get_visibility()
            for pyx_src, pyx_dst in items[1:]:
                for rule in _create_sos(
                        pyx_src,
                        pyx_dst,
                        main_name=None,
                        visibility=subrule_visibility,
                        extra_deps=(),
                        update_extensions=True,
                        tests=None):
                    yield rule

            typing_target = None
            if types:
                typing_target, typing_rules = self.gen_typing_target(
                    name, base_path, package, types, typing_options
                )
                for rule in typing_rules:
                    yield set_visibility(rule)

            pyx_src, pyx_dst = items[0]
            first_pyx_deps = extensions + deps + external_deps
            if typing_target:
                first_pyx_deps.append(typing_target)

            # The first pyx will be the named target and it will depend on all
            # the other generated extensions
            # Don't forget to depend on the .so from our cython deps
            for rule in _create_sos(
                    pyx_src,
                    pyx_dst,
                    main_name=name,
                    visibility=visibility,
                    extra_deps=first_pyx_deps,
                    update_extensions=False,
                    tests=tests):
                yield rule
        else:
            # gen an empty cpp_library instead, so we don't get an empty .so
            # this allows use to use cython_library as a way to gather up
            # pxd and pxi files not just create .so modules
            # This also makes generated cython dep trees possible for
            # thrift-py3 in thrift_library
            cpp_library(
                name=name,
                deps=[':' + name + self.LIB_SUFFIX],
                visibility = _get_visibility(),
                tests = tests,
            )

        # Generate a typing_config target to gather up all types for us and
        # our deps
        if get_typing_config_target():
            if types:
                tdeps = itertools.chain(
                    python_deps,
                    deps,
                    [':{}{}'.format(name, self.TYPING_SUFFIX)]
                )
            else:
                tdeps = itertools.chain(python_deps, deps)
            gen_typing_config(name, deps=tdeps, visibility=visibility)

        # Generate the cython-lib target for allowing cython_libraries
        # to depend on other cython_libraries and inherit their cpp_deps
        # All c++ options are consumed here
        self.gen_shared_lib(
            name,
            api_headers,
            itertools.chain(deps, external_deps),
            cpp_compiler_flags,
            cpp_deps,
            srcs,
            headers,
            header_namespace,
            cpp_external_deps,
            visibility=visibility,
        )

    def get_allowed_args(self):
        return {
            'api',
            'cpp_compiler_flags',
            'cpp_deps',
            'cpp_external_deps',
            'deps',
            'external_deps',
            'flags',
            'generate_cpp',
            'headers',
            'header_namespace',
            'name',
            'package',
            'python_deps',
            'python_external_deps',
            'srcs',
            'tests',
            'types',
            'typing_options',
            'visibility',

        }

    def convert(self, base_path, name, **kwargs):
        """
        Entry point for converting cython_library rules
        """
        # in python3 this method becomes just.
        # yield from self.convert_rule(base_path, name, **kwargs)
        for rule in self.convert_rule(base_path, name, **kwargs):
            yield rule
