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
import os

from . import base
from . import cpp, python
from ..rule import Rule
from ..global_defns import AutoHeaders


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
    STUB_SUFFIX = '__stubs'

    SOURCE_EXTS = (
        '.pyx',
        '.py',
    )
    HEADER_EXTS = (
        '.pxd',
        '.pxi',
    )

    def __init__(self, context):
        super(Converter, self).__init__(context)
        self.cpp_library = cpp.CppConverter(
            context, 'cpp_library',
        )
        self.python_library = python.PythonConverter(
            context, 'python_library',
        )

    def get_fbconfig_rule_type(self):
        return 'cython_library'

    def get_source_with_path(self, package, src):
        """Attach the package to the src path to get a full module path"""
        return os.path.join(package, self.get_source_name(src))

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
        # Setup the command to run cython.
        # TODO: move cython to a `sh_binary` and use a `$(exe ...)` macro.
        fbcode_dir = (
            os.path.join(
                '$GEN_DIR',
                self.get_fbcode_dir_from_gen_dir()))
        python = (
            os.path.join(
                fbcode_dir,
                self.get_tp2_tool_path('python'),
                'bin/python'))
        cython = (
            os.path.join(
                fbcode_dir,
                self.get_tp2_tool_path('Cython'),
                'lib/python/cython.py'))
        attrs = collections.OrderedDict()
        attrs['name'] = os.path.join(parent + self.CONVERT_SUFFIX, module_path)
        attrs['out'] = os.curdir

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
            '{python} {cython} {flags} -o $OUT/{result} {pyx_file}'
            .format(
                result=out_src,
                python=python,
                cython=cython,
                flags=' '.join(flags),
                pyx_file=dst_src,
            )
        )
        attrs['cmd'] = ' && '.join(cmds)

        # Return the name and genrule
        return ':' + attrs['name'], Rule('genrule', attrs)

    def prefix_target_copy_rule(
        self, prefix, target, in_src, out_src
    ):
        """
        Copy a file from a {target} at location {in_src} to {out_src}
        The genrule will use {prefix}={out_src} for its target_name
        """
        name = '{}={}'.format(prefix, out_src)
        src = '$(location {})/{}'.format(target, in_src)
        rule = self.copy_rule(
            src,
            name,
            out_src,
        )
        return ':' + name, rule

    def gen_stub_rule(
        self,
        parent,
        pyx_src,
        pyx_dst
    ):
        attrs = collections.OrderedDict()
        pyi_path = os.path.splitext(pyx_dst)[0] + '.pyi'
        attrs['name'] = '{}={}'.format(parent, pyi_path)
        attrs['out'] = os.path.basename(pyi_path)

        if pyx_src[0] in '@/:':
            # TODO: In this case the pyi file should have been generated in the
            # rule. Just reference it.
            pyx_src = '$(location {})'.format(pyx_src)
        else:
            attrs['srcs'] = [pyx_src]

        # Although we have only one command to issue here, we still use a list
        # to collect the command to make it convenient for inserting new ones.
        cmds = []
        cmds.append(
            '$(exe //python/stubgency:stubgency) {pyx_file} $OUT'
            .format(
                pyx_file=pyx_src,
            )
        )
        attrs['cmd'] = ' && '.join(cmds)

        return ':' + attrs['name'], Rule('genrule', attrs)

    def convert_stub_pylib(
        self,
        parent,
        base_path,
        package,
        pyx_srcs
    ):
        rules = []
        stub_targets = []

        # Generate stub file for each pyx source
        for pyx_src, pyx_dst in pyx_srcs.items():
            target, stub_rule = self.gen_stub_rule(
                parent, pyx_src, pyx_dst
            )
            stub_targets.append(target)
            rules.append(stub_rule)

        # Wrap the generated stub files in a python_library
        stub_pylib_name = parent + self.STUB_SUFFIX
        stub_pylib_rules = self.python_library.convert(
            base_path=base_path,
            name=stub_pylib_name,
            base_module=package,
            srcs=stub_targets
        )
        rules.extend(stub_pylib_rules)

        return ':' + stub_pylib_name, rules

    def gen_extension_rule(
        self,
        parent,
        module_path,
        package,
        src,
        python_deps=(),
        python_external_deps=(),
        cpp_compiler_flags=()
    ):
        attrs = collections.OrderedDict()
        attrs['name'] = os.path.join(parent, module_path)
        attrs['module_name'] = os.path.basename(module_path)
        attrs['base_module'] = package
        attrs['srcs'] = [(src, ['-w'])]
        attrs['deps'] = [':' + parent + self.LIB_SUFFIX]
        if python_deps:
            attrs['deps'].extend(python_deps)
        if python_external_deps:
            attrs['deps'].extend(python_external_deps)
        if cpp_compiler_flags:
            attrs['compiler_flags'] = cpp_compiler_flags
        return ':' + attrs['name'], Rule('cxx_python_extension', attrs)

    def gen_api_header(
        self, name, cython_name, module_path, module_name, api
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
                name, cython_name, module_name + api_suffix, dst + api_suffix
            )
        return None, None

    def gen_shared_lib(
        self, name, base_path, api_headers, deps, cpp_compiler_flags, cpp_deps,
        srcs, headers, cpp_external_deps,
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
                headers.update({self.get_source_name(h): h for h in api_headers})
            else:  # Its a list, if it was a unicode we would have rasied already
                headers.extend(api_headers)

        cpp_deps = list(cpp_deps)  # Incase its empty
        # All cython deps need to have their LIB targets added as a
        # dependency for our LIB TARGET
        for dep in deps:
            # We need to turn it back into fbcode targets for cpp_library
            cpp_deps.append(self.get_fbcode_target(dep + self.LIB_SUFFIX))

        # We need to depend on libpython for the build
        cpp_external_deps = list(cpp_external_deps)
        cpp_external_deps.append(('python', None, 'python'))

        return self.cpp_library.convert(
            base_path=base_path,
            name=name + self.LIB_SUFFIX,
            srcs=list(srcs),  # cpp_library doesn't accept dict sources
            deps=cpp_deps,
            compiler_flags=cpp_compiler_flags,
            auto_headers=AutoHeaders.NONE,
            headers=headers,
            external_deps=cpp_external_deps,
        )

    def convert_rule(
        self,
        base_path,
        name,
        package=None,
        srcs=(),
        headers=(),
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
        gen_stub=False,
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

        pyx_srcs, srcs = split_matching_extensions(srcs, self.SOURCE_EXTS)
        pxd_headers, headers = split_matching_extensions(
            headers, self.HEADER_EXTS)

        deps = [self.convert_build_target(base_path, d) for d in deps]
        external_deps = [self.convert_external_build_target(e)
                         for e in external_deps]

        python_deps = [self.convert_build_target(base_path, d) for d in python_deps]
        python_external_deps = [self.convert_external_build_target(e)
                                for e in python_external_deps]

        # This is normally base_path if package is not set
        if package is None:
            package = base_path.replace('.', '/')

        deps_tree, deps_tree_rule = self.gen_deps_tree(
            name,
            package,
            pxd_headers,
            itertools.chain(deps, external_deps),
        )
        yield deps_tree_rule

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
            first_pyx = None
            extensions = []
            for pyx_src, pyx_dst in pyx_srcs.items():
                pyx_dst = self.get_source_with_path(package, pyx_dst)
                module_name, module_path = self.get_module_name_and_path(
                    package, pyx_dst)
                out_src = module_name + out_ext
                # generate rule to convert source file.
                cython_name, cython_rule = self.convert_src(
                    name, module_path, pyx_src, flags, pyx_dst, out_src
                )
                yield cython_rule
                # Generate the copy_rule
                src_target, src_rule = self.prefix_target_copy_rule(
                    name, cython_name, out_src, module_path + out_ext
                )
                yield src_rule

                # generate an extension for the generated src
                so_target, so_rule = self.gen_extension_rule(
                    name, module_path, os.path.dirname(pyx_dst), src_target,
                    python_deps, python_external_deps, cpp_compiler_flags
                )

                # The fist extension will not be a sub extension
                # So we can have this rule be a cxx_python_extension
                # and not be an empty .so
                if not first_pyx:
                    first_pyx = so_rule
                else:
                    extensions.append(so_target)
                    yield so_rule

                # Generate _api.h header rules.
                api_target, api_rule = self.gen_api_header(
                    name, cython_name, module_path, module_name, api
                )
                if api_rule:
                    yield api_rule
                    api_headers.append(api_target)

            stubs = []
            if gen_stub:
                stub_target, stub_rules = self.convert_stub_pylib(
                    name, base_path, package, pyx_srcs
                )
                for rule in stub_rules:
                    yield rule
                stubs.append(stub_target)

            # The first pyx will be the named target and it will depend on all
            # the other generated extensions
            first_pyx.attributes['name'] = name
            first_pyx.attributes['deps'].extend(extensions)
            first_pyx.attributes['deps'].extend(stubs)
            # Don't forget to depend on the .so from our cython deps
            first_pyx.attributes['deps'].extend(deps)
            first_pyx.attributes['deps'].extend(external_deps)
            yield first_pyx
        else:
            # gen an empty cpp_library instead, so we don't get an empty .so
            # this allows use to use cython_library as a way to gather up
            # pxd and pxi files not just create .so modules
            # This also makes generated cython dep trees possible for
            # thrift-py3 in thrift_library
            for rule in self.cpp_library.convert(
                base_path=base_path,
                name=name,
                deps=[':' + name + self.LIB_SUFFIX],
            ):
                yield rule

        # Generate the cython-lib target for allowing cython_libraries
        # to depend on other cython_libraries and inherit their cpp_deps
        # All c++ options are consumed here
        for rule in self.gen_shared_lib(
            name,
            base_path,
            api_headers,
            itertools.chain(deps, external_deps),
            cpp_compiler_flags,
            cpp_deps,
            srcs,
            headers,
            cpp_external_deps,
        ):
            yield rule

    def get_allowed_args(self):
        return {
            'api',
            'cpp_compiler_flags',
            'cpp_deps',
            'cpp_external_deps',
            'deps',
            'external_deps',
            'flags',
            'gen_stub',
            'generate_cpp',
            'headers',
            'name',
            'package',
            'python_deps',
            'python_external_deps',
            'srcs',
        }

    def convert(self, base_path, name, **kwargs):
        """
        Entry point for converting cython_library rules
        """
        # in python3 this method becomes just.
        # yield from self.convert_rule(base_path, name, **kwargs)
        for rule in self.convert_rule(base_path, name, **kwargs):
            yield rule
