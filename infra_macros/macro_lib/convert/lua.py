#!/usr/bin/env python2

# Copyright 2016-present, Facebook, Inc.
# All rights reserved.
#
# This source code is licensed under the BSD-style license found in the
# LICENSE file in the root directory of this source tree. An additional grant
# of patent rights can be found in the PATENTS file in the same directory.

from __future__ import absolute_import
from __future__ import division
from __future__ import print_function
from __future__ import unicode_literals

import collections
import os
import pipes

macro_root = read_config('fbcode', 'macro_lib', '//macro_lib')
include_defs("{}/convert/base.py".format(macro_root), "base")
RootRuleTarget = base.RootRuleTarget
include_defs("{}/rule.py".format(macro_root))


DEFAULT_CPP_MAIN = RootRuleTarget('tools/make_lar', 'lua_main')

INTERPRETERS = [
    DEFAULT_CPP_MAIN,
    RootRuleTarget('tools/make_lar', 'lua_main_no_fb'),
]

CPP_MAIN_SOURCE_TEMPLATE = """\
#include <stdlib.h>
#include <string.h>

#include <string>
#include <vector>

extern "C" int lua_main(int argc, char **argv);

static std::string join(const char *a, const char *b) {{
  std::string p;
  p += a;
  p += '/';
  p += b;
  return p;
}}

static std::string join(const std::string& a, const char * b) {{
  return join(a.c_str(), b);
}}

static std::string join(const std::string& a, const std::string& b) {{
  return join(a.c_str(), b.c_str());
}}

static std::string dirname(const std::string& a) {{
  return a.substr(0, a.rfind('/'));
}}

extern "C"
int run_starter(
    int argc,
    const char **argv,
    const char * /*main_module*/,
    const char *modules_dir,
    const char *py_modules_dir,
    const char *extension_suffix) {{

  if (modules_dir != NULL) {{

      std::string packagePath =
        join(modules_dir, "?.lua") + ';' +
        join(join(modules_dir, "?"), "init.lua");
      setenv("LUA_PATH", packagePath.c_str(), 1);

      std::string packageCPath =
        join(modules_dir, std::string("?.") + extension_suffix);
      setenv("LUA_CPATH", packageCPath.c_str(), 1);

  }}

  if (py_modules_dir != NULL) {{
      setenv("PYTHONPATH", py_modules_dir, 1);
      setenv("FB_LAR_INIT_PYTHON", "1", 1);
  }}

  std::vector<const char*> args;
  std::vector<std::string> argsStorage;
  args.push_back(argv[0]);
  args.insert(args.end(), {args});
  if ({run_file} != NULL) {{
    args.push_back("--");
    argsStorage.push_back(
      join(
        modules_dir == NULL ?
          dirname(std::string(argv[0])) :
          modules_dir,
        {run_file}));
    args.push_back(argsStorage.back().c_str());
  }}
  for (int i = 1; i < argc; i++) {{
    args.push_back(argv[i]);
  }}
  args.push_back(NULL);

  return lua_main(args.size() - 1, const_cast<char**>(args.data()));
}}
"""


def cpp_repr_str(s):
    return '"' + s + '"'


def cpp_repr_list(l):
    return '{' + ', '.join([cpp_repr(a) for a in l]) + '}'


def cpp_repr(a):
    if a is None:
        return 'NULL'
    elif isinstance(a, basestring):
        return cpp_repr_str(a)
    elif isinstance(a, (tuple, list)):
        return cpp_repr_list(a)
    else:
        raise Exception('unexpected type')


class LuaConverter(base.Converter):

    def __init__(self, context, rule_type, buck_rule_type=None):
        super(LuaConverter, self).__init__(context)
        self._rule_type = rule_type
        self._buck_rule_type = buck_rule_type or rule_type

    def get_fbconfig_rule_type(self):
        return self._rule_type

    def get_buck_rule_type(self):
        return self._buck_rule_type

    def is_test(self):
        return self.get_fbconfig_rule_type() == 'lua_unittest'

    def get_base_module(self, base_path, base_module=None):
        if base_module is None:
            return os.path.join('fbcode', base_path)
        return base_module

    def get_module_name(self, name, explicit_name=None):
        if explicit_name is None:
            return name
        return explicit_name

    def get_module(self, base_path, name, base_module=None):
        base_module = self.get_base_module(base_path, base_module=base_module)
        if base_module:
            return base_module.replace(os.sep, '.') + '.' + name
        return name

    def convert_sources(self, base_path, srcs):
        if isinstance(srcs, dict):
            return self.convert_source_map(
                base_path,
                {v: k for k, v in srcs.iteritems()})
        else:
            return self.convert_source_list(base_path, srcs)

    def create_run_library(
            self,
            base_path,
            name,
            interactive=False,
            base_module=None,
            main_module=None):
        """
        Create the run file used by fbcode's custom Lua bootstrapper.
        """

        rules = []

        source_name = name + '-run-source'
        if interactive:
            source = ''
        else:
            source = (
                'require("fb.trepl.base").exec("{}")'.format(
                    self.get_module(
                        base_path,
                        main_module,
                        base_module=base_module)))
        source_attrs = collections.OrderedDict()
        source_attrs['name'] = source_name
        source_attrs['out'] = '_run.lua'
        source_attrs['cmd'] = (
            'echo -n {} > $OUT'.format(pipes.quote(source)))
        rules.append(Rule('genrule', source_attrs))

        attrs = collections.OrderedDict()
        attrs['name'] = name + '-run'
        attrs['srcs'] = [':' + source_name]
        attrs['base_module'] = ''
        attrs['deps'] = [
            self.convert_build_target(base_path, '@/fblualib/trepl:base'),
        ]
        rules.append(Rule('lua_library', attrs))

        return attrs['name'], source_attrs['out'], rules

    def create_cpp_main_library(
            self,
            base_path,
            name,
            base_module=None,
            interactive=False,
            cpp_main=None,
            cpp_main_args=(),
            run_file=None,
            allocator='malloc'):
        """
        Create the C/C++ main entry point.
        """

        rules = []

        args = []
        args.extend(cpp_main_args)
        if interactive:
            args.append('-i')

        cpp_main_source = (
            CPP_MAIN_SOURCE_TEMPLATE.format(
                args=cpp_repr(args),
                run_file=cpp_repr(run_file)))
        cpp_main_source_name = name + '-cpp-main-source'
        cpp_main_source_attrs = collections.OrderedDict()
        cpp_main_source_attrs['name'] = cpp_main_source_name
        cpp_main_source_attrs['out'] = name + '.cpp'
        cpp_main_source_attrs['cmd'] = (
            'echo -n {} > $OUT'.format(pipes.quote(cpp_main_source)))
        rules.append(Rule('genrule', cpp_main_source_attrs))

        cpp_main_name = name + '-cpp-main'
        cpp_main_attrs = collections.OrderedDict()
        cpp_main_attrs['name'] = name + '-cpp-main'
        cpp_main_attrs['compiler_flags'] = self.get_extra_cxxflags()
        cpp_main_attrs['linker_flags'] = self.get_extra_ldflags()
        cpp_main_attrs['exported_linker_flags'] = [
            # Since we statically link in sanitizer/allocators libs, make sure
            # we export all their symbols on the dynamic symbols table.
            # Normally, the linker would take care of this for us, but we link
            # the cpp main binary with only it's minimal deps (rather than all
            # C/C++ deps for the Lua binary), so it may incorrectly decide to
            # not export some needed symbols.
            '-Wl,--export-dynamic',
        ]
        cpp_main_attrs['force_static'] = True
        cpp_main_attrs['srcs'] = [':' + cpp_main_source_name]

        # Set the dependencies that linked into the C/C++ starter binary.
        out_deps = []

        # If a user-specified `cpp_main` is given, use that.  Otherwise,
        # fallback to the default.
        if cpp_main is not None:
            out_deps.append(self.normalize_dep(cpp_main, base_path=base_path))
        else:
            out_deps.append(DEFAULT_CPP_MAIN)

        # Add in binary-specific link deps.
        out_deps.extend(self.get_binary_link_deps(allocator=allocator))

        # Set the deps attr.
        cpp_main_attrs['deps'], cpp_main_attrs['platform_deps'] = (
            self.format_all_deps(out_deps))

        rules.append(Rule('cxx_library', cpp_main_attrs))

        return (':' + cpp_main_name, rules)

    def convert_library(
            self,
            base_path,
            name=None,
            base_module=None,
            srcs=(),
            deps=(),
            external_deps=()):
        """
        Buckify a library rule.
        """

        attributes = collections.OrderedDict()

        attributes['name'] = name

        attributes['srcs'] = self.convert_sources(base_path, srcs)

        attributes['base_module'] = self.get_base_module(
            base_path, base_module=base_module)

        # If this is a tp2 project, verify that we just have a single inlined
        # build.  When this stops being true, we'll need to add versioned src
        # support to lua rules (e.g. D4312362).
        if self.is_tp2(base_path):
            project_builds = self.get_tp2_project_builds(base_path)
            if (len(project_builds) != 1 or
                    project_builds.values()[0].subdir != ''):
                raise TypeError(
                    'lua_library(): expected to find a single inlined build '
                    'for tp2 project "{}"'
                    .format(self.get_tp2_project_name(base_path)))

        dependencies = []
        if self.is_tp2(base_path):
            dependencies.append(
                self.get_tp2_project_target(
                    self.get_tp2_project_name(base_path)))
        for target in deps:
            dependencies.append(self.normalize_dep(target, base_path))
        for target in external_deps:
            dependencies.append(self.normalize_external_dep(target))
        if dependencies:
            platform = (
                self.get_tp2_platform(base_path)
                if self.is_tp2(base_path) else None)
            attributes['deps'], attributes['platform_deps'] = (
                self.format_all_deps(dependencies, platform=platform))

        return [Rule('lua_library', attributes)]

    def convert_binary(
            self,
            base_path,
            name=None,
            main_module=None,
            base_module=None,
            interactive=None,
            cpp_main=None,
            cpp_main_args=(),
            embed_deps=None,
            srcs=(),
            deps=(),
            external_deps=(),
            allocator='malloc'):
        """
        Buckify a binary rule.
        """

        platform = self.get_platform(base_path)

        attributes = collections.OrderedDict()
        attributes['name'] = name

        rules = []
        dependencies = []

        # If we see any `srcs`, spin them off into a library rule and add that
        # as a dep.
        if srcs:
            lib_name = name + '-library'
            rules.extend(
                self.convert_library(
                    base_path,
                    lib_name,
                    base_module=base_module,
                    srcs=srcs,
                    deps=deps,
                    external_deps=external_deps))
            dependencies.append(RootRuleTarget(base_path, lib_name))
            deps = []
            external_deps = []

        # Parse out the `cpp_main` parameter.
        if cpp_main is None:
            cpp_main_dep = DEFAULT_CPP_MAIN
        else:
            cpp_main_dep = self.normalize_dep(cpp_main, base_path)

        # Default main_module = name
        if (main_module is None and
                interactive is None and
                cpp_main_dep in INTERPRETERS):
            main_module = name

        # If a main module is specified, create a run file for it.
        run_file = None
        if main_module is not None or interactive:
            lib, run_file, extra_rules = (
                self.create_run_library(
                    base_path,
                    name,
                    interactive=interactive,
                    main_module=main_module,
                    base_module=base_module))
            rules.extend(extra_rules)
            dependencies.append(RootRuleTarget(base_path, lib))

        # Generate the native starter library.
        cpp_main_lib, extra_rules = (
            self.create_cpp_main_library(
                base_path,
                name,
                base_module=base_module,
                interactive=interactive,
                cpp_main=cpp_main,
                cpp_main_args=cpp_main_args,
                run_file=run_file,
                allocator=allocator))
        rules.extend(extra_rules)
        attributes['native_starter_library'] = cpp_main_lib

        # We always use a dummy main module, since we pass in the actual main
        # module via the run file.
        attributes['main_module'] = 'dummy'

        # We currently always use py2.
        attributes['python_platform'] = self.get_py2_platform(platform)

        # Set platform.
        attributes['platform'] = platform

        # Tests depend on FB lua test lib.
        if self.is_test():
            dependencies.append(RootRuleTarget('fblualib/luaunit', 'luaunit'))

        # Add in `dep` and `external_deps` parameters to the dependency list.
        for target in deps:
            dependencies.append(self.normalize_dep(target, base_path))
        for target in external_deps:
            dependencies.append(self.normalize_external_dep(target))

        if dependencies:
            attributes['deps'], attributes['platform_deps'] = (
                self.format_all_deps(dependencies))

        return [Rule('lua_binary', attributes)] + rules

    def convert_unittest(
            self,
            base_path,
            name=None,
            tags=(),
            type='lua',
            **kwargs):
        """
        Buckify a unittest rule.
        """

        rules = []

        # Generate the test binary rule and fixup the name.
        binary_name = name + '-binary'
        binary_rules = (
            self.convert_binary(
                base_path,
                name=name,
                **kwargs))
        binary_rules[0].attributes['name'] = binary_name
        binary_rules[0].attributes['package_style'] = 'inplace'
        rules.extend(binary_rules)

        # Create a `sh_test` rule to wrap the test binary and set it's tags so
        # that testpilot knows it's a lua test.
        attributes = collections.OrderedDict()
        attributes['name'] = name
        attributes['test'] = ':' + binary_name
        attributes['labels'] = (
            self.convert_labels('lua', 'custom-type-' + type, *tags))
        rules.append(Rule('sh_test', attributes))

        return rules

    def convert(self, *args, **kwargs):
        rtype = self.get_fbconfig_rule_type()
        if rtype == 'lua_library':
            return self.convert_library(*args, **kwargs)
        elif rtype == 'lua_binary':
            return self.convert_binary(*args, **kwargs)
        elif rtype == 'lua_unittest':
            return self.convert_unittest(*args, **kwargs)
        else:
            raise Exception('unexpected type: ' + rtype)
