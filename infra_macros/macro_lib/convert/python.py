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
import operator
import pipes

with allow_unsafe_import():  # noqa: magic
    from distutils.version import LooseVersion
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
Rule = import_macro_lib('rule').Rule
target = import_macro_lib('fbcode_target')
build_info = import_macro_lib('build_info')
RootRuleTarget = target.RootRuleTarget
RuleTarget = target.RuleTarget
ThirdPartyRuleTarget = target.ThirdPartyRuleTarget
load("@fbcode_macros//build_defs:python_typing.bzl",
     "get_typing_config_target")


INTERPS = [
    ('interp', 'libfb.py.python_interp', '//libfb/py:python_interp'),
    ('ipython', 'libfb.py.ipython_interp', '//libfb/py:ipython_interp'),
    ('vs_debugger', 'libfb.py.vs_debugger', '//libfb/py:vs_debugger'),
]


GEN_SRCS_LINK = 'https://fburl.com/203312823'


MANIFEST_TEMPLATE = """\
import sys


class Manifest(object):

    def __init__(self):
        self._modules = None

    @property
    def modules(self):
        if self._modules is None:
            import os, sys
            modules = set()
            for root, dirs, files in os.walk(sys.path[0]):
                rel_root = os.path.relpath(root, sys.path[0])
                for name in files:
                    base, ext = os.path.splitext(name)
                    if ext in ('.py', '.pyc', '.pyo', '.so'):
                        modules.add(
                            os.path.join(rel_root, base).replace(os.sep, '.'))
            self._modules = sorted(modules)
        return self._modules

    fbmake = {{
        {fbmake}
    }}


sys.modules[__name__] = Manifest()
"""


class PythonConverter(base.Converter):

    RULE_TYPE_MAP = {
        'python_library': 'python_library',
        'python_binary': 'python_binary',
        'python_unittest': 'python_test',
    }

    def __init__(self, context, rule_type):
        super(PythonConverter, self).__init__(context)
        self._rule_type = rule_type

    def get_fbconfig_rule_type(self):
        return self._rule_type

    def get_buck_rule_type(self):
        return self.RULE_TYPE_MAP[self._rule_type]

    def is_binary(self):
        return self.get_fbconfig_rule_type() == 'python_binary'

    def is_test(self):
        return self.get_fbconfig_rule_type() == 'python_unittest'

    def is_library(self):
        return self.get_fbconfig_rule_type() == 'python_library'

    def parse_srcs(self, base_path, param, srcs):  # type: (str, str, Union[List[str], Dict[str, str]]) -> Dict[str, Union[str, RuleTarget]]
        """
        Parse the given Python input sources.
        """

        # Parse sources in dict form.
        if isinstance(srcs, dict):
            out_srcs = (
                self.parse_source_map(
                    base_path,
                    {v: k for k, v in srcs.items()}))

        # Parse sources in list form.
        else:

            out_srcs = {}

            # Format sources into a dict of logical name of value.
            for src in self.parse_source_list(base_path, srcs):

                # Path names are the same as path values.
                if not isinstance(src, RuleTarget):
                    out_srcs[src] = src
                    continue

                # If the source comes from a `custom_rule`/`genrule`, and the
                # user used the `=` notation which encodes the sources "name",
                # we can extract and use that.
                if '=' in src.name:
                    name = src.name.rsplit('=', 1)[1]
                    out_srcs[name] = src
                    continue

                # Otherwise, we don't have a good way of deducing the name.
                # This actually looks to be pretty rare, so just throw a useful
                # error prompting the user to use the `=` notation above, or
                # switch to an explicit `dict`.
                raise ValueError(
                    'parameter `{}`: cannot infer a "name" to use for '
                    '`{}`. If this is an output from a `custom_rule`, '
                    'consider using the `<rule-name>=<out>` notation instead. '
                    'Otherwise, please specify this parameter as `dict` '
                    'mapping sources to explicit "names" (see {} for details).'
                    .format(param, self.get_dep_target(src), GEN_SRCS_LINK))

        return out_srcs

    def parse_gen_srcs(self, base_path, srcs):  # type: (str, Union[List[str], Dict[str, str]]) -> Dict[str, Union[str, RuleTarget]]
        """
        Parse the given sources as input to the `gen_srcs` parameter.
        """

        out_srcs = self.parse_srcs(base_path, 'gen_srcs', srcs)

        # Do a final pass to verify that all sources in `gen_srcs` are rule
        # references.
        for src in out_srcs.itervalues():
            if not isinstance(src, RuleTarget):
                raise ValueError(
                    'parameter `gen_srcs`: `{}` must be a reference to rule '
                    'that generates a source (e.g. `//foo:bar`, `:bar`) '
                    ' (see {} for details).'
                    .format(src, GEN_SRCS_LINK))

        return out_srcs

    def parse_constraint(self, constraint):
        """
        Parse the given constraint into callable which tests a `LooseVersion`
        object.
        """

        if constraint is None:
            return lambda other: True

        # complex Constraints are silly, we only have py2 and py3
        if constraint in (2, '2'):
            constraint = self.get_py2_version()
            op = operator.eq
        elif constraint in (3, '3'):
            constraint = self.get_py3_version()
            op = operator.eq
        elif constraint.startswith('<='):
            constraint = constraint[2:].lstrip()
            op = operator.le
        elif constraint.startswith('>='):
            constraint = constraint[2:].lstrip()
            op = operator.ge
        elif constraint.startswith('<'):
            constraint = constraint[1:].lstrip()
            op = operator.lt
        elif constraint.startswith('='):
            constraint = constraint[1:].lstrip()
            op = operator.eq
        elif constraint.startswith('>'):
            constraint = constraint[1:].lstrip()
            op = operator.gt
        else:
            op = operator.eq

        return lambda other: op(other, LooseVersion(constraint))

    def matches_py2(self, constraint):
        matches = self.parse_constraint(constraint)
        return matches(LooseVersion(self.get_py2_version()))

    def matches_py3(self, constraint):
        matches = self.parse_constraint(constraint)
        return matches(LooseVersion(self.get_py3_version()))

    def matches_pypy(self, constraint):
        return str(constraint).startswith('pypy')

    def get_python_version(self, constraint):
        if self.matches_py3(constraint):
            return self.get_py3_version()
        if self.matches_py2(constraint):
            return self.get_py2_version()
        if self.matches_pypy(constraint):
            return self.get_pypy_version()
        raise ValueError('invalid python constraint: {!r}'.format(constraint))

    def get_interpreter(self, platform, python_version):
        return '/usr/local/fbcode/{}/bin/python{}'.format(
            platform,
            python_version[:3])

    def get_version_universe(self, python_version):
        return super(PythonConverter, self).get_version_universe(
            [('python', python_version)])

    def convert_needed_coverage_spec(self, base_path, spec):
        if len(spec) != 2:
            raise ValueError(
                'parameter `needed_coverage`: `{}` must have exactly 2 '
                'elements, a ratio and a target.'
                .format(spec))

        ratio, target = spec
        if '=' not in target:
            return (
                ratio,
                self.convert_build_target(base_path, target))
        target, path = target.rsplit('=', 1)
        return (ratio, self.convert_build_target(base_path, target), path)

    def get_python_build_info(
            self,
            base_path,
            name,
            main_module,
            platform,
            python_version):
        """
        Return the build info attributes to install for python rules.
        """

        py_build_info = collections.OrderedDict()

        py_build_info['main_module'] = main_module

        interp = self.get_interpreter(platform, python_version)
        py_build_info['python_home'] = os.path.dirname(os.path.dirname(interp))
        py_build_info['python_command'] = pipes.quote(interp)

        # Include the standard build info, converting the keys to the names we
        # use for python.
        key_mappings = {
            'package_name': 'package',
            'package_version': 'version',
            'rule': 'build_rule',
            'rule_type': 'build_rule_type',
        }
        build_info = (
            self.get_build_info(
                base_path,
                name,
                self.get_fbconfig_rule_type(),
                platform))
        for key, val in build_info.iteritems():
            py_build_info[key_mappings.get(key, key)] = val

        return py_build_info

    def generate_manifest(
            self,
            base_path,
            name,
            main_module,
            platform,
            python_version,
            visibility):
        """
        Build the rules that create the `__manifest__` module.
        """

        rules = []

        build_info = (
            self.get_python_build_info(
                base_path,
                name,
                main_module,
                platform,
                python_version))
        manifest = MANIFEST_TEMPLATE.format(
            fbmake='\n        '.join(
                '{!r}: {!r},'.format(k, v) for k, v in build_info.iteritems()))

        manifest_name = name + '-manifest'
        manifest_attrs = collections.OrderedDict()
        manifest_attrs['name'] = manifest_name
        if visibility is not None:
            manifest_attrs['visibility'] = visibility
        manifest_attrs['out'] = name + '-__manifest__.py'
        manifest_attrs['cmd'] = (
            'echo -n {} > $OUT'.format(pipes.quote(manifest)))
        rules.append(Rule('genrule', manifest_attrs))

        manifest_lib_name = name + '-manifest-lib'
        manifest_lib_attrs = collections.OrderedDict()
        manifest_lib_attrs['name'] = manifest_lib_name
        if visibility is not None:
            manifest_lib_attrs['visibility'] = visibility
        manifest_lib_attrs['base_module'] = ''
        manifest_lib_attrs['srcs'] = {'__manifest__.py': ':' + manifest_name}
        rules.append(Rule('python_library', manifest_lib_attrs))

        return manifest_lib_name, rules

    def get_par_build_args(
            self,
            base_path,
            name,
            rule_type,
            platform,
            argcomplete=None,
            strict_tabs=None,
            compile=None,
            par_style=None,
            strip_libpar=None,
            needed_coverage=None,
            python=None):
        """
        Return the arguments we need to pass to the PAR builder wrapper.
        """

        build_args = []

        if self._context.config.get_use_custom_par_args():
            # Arguments that we wanted directly threaded into `make_par`.
            passthrough_args = []
            if argcomplete is True:
                passthrough_args.append('--argcomplete')
            if strict_tabs is False:
                passthrough_args.append('--no-strict-tabs')
            if compile is False:
                passthrough_args.append('--no-compile')
                passthrough_args.append('--store-source')
            elif compile == 'with-source':
                passthrough_args.append('--store-source')
            elif compile is not True and compile is not None:
                raise Exception(
                    'Invalid value {} for `compile`, must be True, False, '
                    '"with-source", or None (default)'.format(compile)
                )
            if par_style is not None:
                passthrough_args.append('--par-style=' + par_style)
            if needed_coverage is not None or self._context.coverage:
                passthrough_args.append('--store-source')
            if self._context.mode.startswith('opt'):
                passthrough_args.append('--optimize')

            # Add arguments to populate build info.
            assert build_info.get_build_info_mode(base_path, name) != 'none'
            info = (
                build_info.get_explicit_build_info(
                    base_path,
                    name,
                    rule_type,
                    platform))
            passthrough_args.append(
                '--build-info-build-mode=' + info.build_mode)
            passthrough_args.append('--build-info-build-tool=buck')
            if info.package_name is not None:
                passthrough_args.append(
                    '--build-info-package-name=' + info.package_name)
            if info.package_release is not None:
                passthrough_args.append(
                    '--build-info-package-release=' + info.package_release)
            if info.package_version is not None:
                passthrough_args.append(
                    '--build-info-package-version=' + info.package_version)
            passthrough_args.append('--build-info-platform=' + info.platform)
            passthrough_args.append('--build-info-rule-name=' + info.rule)
            passthrough_args.append('--build-info-rule-type=' + info.rule_type)

            build_args.extend(['--passthrough=' + a for a in passthrough_args])

            # Arguments for stripping libomnibus. dbg builds should never strip.
            if not self._context.mode.startswith('dbg'):
                if strip_libpar is True:
                    build_args.append('--omnibus-debug-info=strip')
                elif strip_libpar == 'extract':
                    build_args.append('--omnibus-debug-info=extract')
                else:
                    build_args.append('--omnibus-debug-info=separate')

            # Set an explicit python interpreter.
            if python is not None:
                build_args.append('--python-override=' + python)

        return build_args

    def format_sources(self, src_map):
        """
        The `platform_srcs` parameter for Python rules matches against the
        python platform, which has the format `py<py-vers>-<platform>`.  So
        drop the `^` anchor from the platform regex so we match these properly.
        """

        srcs, plat_srcs = self.format_source_map(src_map)
        return srcs, [(p[1:], s) for p, s in plat_srcs]

    def should_generate_interp_rules(self, helper_deps):
        """
        Return whether we should generate the interp helpers.
        """
        # We can only work in @mode/dev
        if not self._context.mode.startswith('dev'):
            return False

        # Our current implementation of the interp helpers is costly when using
        # omnibus linking, only generate these if explicitly set via config or TARGETS
        try:
            config_setting = self.read_bool('python', 'helpers', None)
        except KeyError:
            config_setting = None

        if config_setting is None:
            # No CLI option is set, respect the TARGETS file option.
            return helper_deps

        return config_setting


    def convert_interp_rules(
            self,
            name,
            platform,
            python_version,
            python_platform,
            deps,
            platform_deps,
            preload_deps,
            visibility):
        """
        Generate rules to build intepreter helpers.
        """

        rules = []

        for interp, interp_main_module, interp_dep in INTERPS:
            attrs = collections.OrderedDict()
            attrs['name'] = name + '-' + interp
            if visibility is not None:
                attrs['visibility'] = visibility
            attrs['main_module'] = interp_main_module
            attrs['cxx_platform'] = platform
            attrs['platform'] = python_platform
            attrs['version_universe'] = (
                self.get_version_universe(python_version))
            attrs['deps'] = [interp_dep] + deps
            attrs['platform_deps'] = platform_deps
            attrs['preload_deps'] = preload_deps
            attrs['package_style'] = 'inplace'
            rules.append(Rule('python_binary', attrs))

        return rules

    # TODO(T23173403): move this to `base.py` and make available for other
    # languages.
    def get_jemalloc_malloc_conf_dep(self, base_path, name, malloc_conf, deps, visibility):
        """
        Build a rule which wraps the JEMalloc allocator and links default
        configuration via the `jemalloc_conf` variable.
        """

        rules = []

        attrs = collections.OrderedDict()
        attrs['name'] = '__{}_jemalloc_conf_src__'.format(name)
        if visibility is not None:
            attrs['visibility'] = visibility
        attrs['out'] = 'jemalloc_conf.c'
        attrs['cmd'] = (
            'echo \'const char* malloc_conf = "{}";\' > "$OUT"'
            .format(','.join(['{}:{}'.format(k, v)
                              for k, v in sorted(malloc_conf.items())])))
        src_rule = Rule('genrule', attrs)
        rules.append(src_rule)

        attrs = collections.OrderedDict()
        attrs['name'] = '__{}_jemalloc_conf_lib__'.format(name)
        if visibility is not None:
            attrs['visibility'] = visibility
        attrs['srcs'] = [':{}'.format(src_rule.attributes['name'])]
        attrs['deps'], attrs['platform_deps'] = self.format_all_deps(deps)
        lib_rule = Rule('cxx_library', attrs)
        rules.append(lib_rule)

        return RootRuleTarget(base_path, lib_rule.attributes['name']), rules

    def get_preload_deps(self, base_path, name, allocator, jemalloc_conf=None, visibility=None):
        """
        Add C/C++ deps which need to preloaded by Python binaries.
        """

        deps = []
        rules = []

        sanitizer = self.get_sanitizer()

        # If we're using sanitizers, add the dep on the sanitizer-specific
        # support library.
        if sanitizer is not None:
            sanitizer = base.SANITIZERS[sanitizer]
            deps.append(
                RootRuleTarget(
                    'tools/build/sanitizers',
                    '{}-py'.format(sanitizer)))
        # Generate sanitizer configuration even if sanitizers are not used
        d, r = self.create_sanitizer_configuration(base_path, name)
        deps.extend(d)
        rules.extend(r)

        # If we're using an allocator, and not a sanitizer, add the allocator-
        # specific deps.
        if allocator is not None and sanitizer is None:
            allocator_deps = self.get_allocator_deps(allocator)
            if allocator.startswith('jemalloc') and jemalloc_conf is not None:
                conf_dep, conf_rules = (
                    self.get_jemalloc_malloc_conf_dep(
                        base_path,
                        name,
                        jemalloc_conf,
                        allocator_deps,
                        visibility))
                allocator_deps = [conf_dep]
                rules.extend(conf_rules)
            deps.extend(allocator_deps)

        return deps, rules

    def get_ldflags(self, base_path, name, strip_libpar=True):
        """
        Return ldflags to use when linking omnibus libraries in python binaries.
        """

        # We override stripping for python binaries unless we're in debug mode
        # (which doesn't get stripped by default).  If either `strip_libpar`
        # is set or any level of stripping is enabled via config, we do full
        # stripping.
        strip_mode = self.get_strip_mode(base_path, name)
        if (not self._context.mode.startswith('dbg') and
                (strip_mode != 'none' or strip_libpar is True)):
            strip_mode = 'full'

        return super(PythonConverter, self).get_ldflags(
            base_path,
            name,
            self.get_fbconfig_rule_type(),
            strip_mode=strip_mode)

    def get_package_style(self):
        return self.read_choice(
            'python',
            'package_style',
            ['inplace', 'standalone'],
            'standalone')

    def gen_associated_targets(self, name, targets, visibility):
        """
        Associated Targets are buck rules that need to be built, when This
        target is built, but are not a code dependency. Which is why we
        wrap them in a cxx_library so they could never be a code dependency
        """
        attrs = collections.OrderedDict()
        attrs['name'] = name + '-build_also'
        if visibility is not None:
            attrs['visibility'] = visibility
        attrs['deps'] = targets
        return Rule('cxx_library', attrs)

    def create_library(
        self,
        base_path,
        name,
        base_module=None,
        srcs=(),
        versioned_srcs=(),
        gen_srcs=(),
        deps=[],
        tests=[],
        external_deps=[],
        visibility=None,
        cpp_deps=(),
    ):
        attributes = collections.OrderedDict()
        attributes['name'] = name

        # Normalize all the sources from the various parameters.
        parsed_srcs = {}  # type: Dict[str, Union[str, RuleTarget]]
        parsed_srcs.update(self.parse_srcs(base_path, 'srcs', srcs))
        parsed_srcs.update(self.parse_gen_srcs(base_path, gen_srcs))

        # Contains a mapping of platform name to sources to use for that
        # platform.
        all_versioned_srcs = []

        # If we're TP project, install all sources via the `versioned_srcs`
        # parameter.
        if self.is_tp2(base_path):

            def match_py(pv, py_vers):
                return (pv[:3] == py_vers  # matches major-minor version
                        or pv == py_vers)  # matches full name (e.g., pypy)

            # TP2 projects have multiple "pre-built" source dirs, so we install
            # them via the `versioned_srcs` parameter along with the versions
            # of deps that was used to build them, so that Buck can select the
            # correct one based on version resolution.
            project_builds = self.get_tp2_project_builds(base_path)
            for build in project_builds.values():
                build_srcs = [parsed_srcs]
                if versioned_srcs:
                    py_vers = build.versions['python']
                    build_srcs.extend(
                        [self.parse_srcs(base_path, 'versioned_srcs', vs)
                         for pv, vs in versioned_srcs if match_py(pv, py_vers)])

                vsrc = {}
                for build_src in build_srcs:
                    for name, src in build_src.items():
                        if isinstance(src, RuleTarget):
                            vsrc[name] = src
                        else:
                            vsrc[name] = os.path.join(build.subdir, src)
                all_versioned_srcs.append((build.project_deps, vsrc))

            # Reset `srcs`, since we're using `versioned_srcs`.
            parsed_srcs = {}

        # If we're an fbcode project, then keep the regular sources parameter
        # and only use the `versioned_srcs` parameter for the input parameter
        # of the same name.
        else:
            py2_srcs = {}
            py3_srcs = {}
            pypy_srcs = {}
            for constraint, vsrcs in versioned_srcs:
                vsrcs = self.parse_srcs(base_path, 'versioned_srcs', vsrcs)
                if self.matches_py2(constraint):
                    py2_srcs.update(vsrcs)
                if self.matches_py3(constraint):
                    py3_srcs.update(vsrcs)
                if self.matches_pypy(constraint):
                    pypy_srcs.update(vsrcs)
            if py2_srcs or py3_srcs or pypy_srcs:
                py = self.get_tp2_project_target('python')
                py2 = self.get_py2_version()
                py3 = self.get_py3_version()
                pypy = self.get_pypy_version()
                platforms = (
                    self.get_platforms()
                    if not self.is_tp2(base_path)
                    else [self.get_tp2_platform(base_path)])
                all_versioned_srcs.append(
                    ({self.get_dep_target(py, platform=p): py2
                      for p in platforms},
                     py2_srcs))
                all_versioned_srcs.append(
                    ({self.get_dep_target(py, platform=p): py3
                      for p in platforms},
                     py3_srcs))
                if pypy is not None:
                    if not pypy_srcs:
                        pypy_srcs = py3_srcs
                    all_versioned_srcs.append(
                        ({self.get_dep_target(py, platform=p): pypy
                          for p in platforms},
                         pypy_srcs))

        if base_module is not None:
            attributes['base_module'] = base_module

        if parsed_srcs:
            # Need to split the srcs into srcs & resources as Buck
            # expects all test srcs to be python modules.
            if self.is_test():
                attributes['srcs'], attributes['platform_srcs'] = (
                    self.format_sources(
                        {k: v
                         for k, v in parsed_srcs.iteritems()
                         if k.endswith('.py')}))
                attributes['resources'], attributes['platform_resources'] = (
                    self.format_sources(
                        {k: v
                         for k, v in parsed_srcs.iteritems()
                         if not k.endswith('.py')}))
            else:
                attributes['srcs'], attributes['platform_srcs'] = (
                    self.format_sources(parsed_srcs))

        # Emit platform-specific sources.  We split them between the
        # `platform_srcs` and `platform_resources` parameter based on their
        # extension, so that directories with only resources don't end up
        # creating stray `__init__.py` files for in-place binaries.
        if all_versioned_srcs:
            out_versioned_srcs = []
            out_versioned_resources = []
            for vcollection, ver_srcs in all_versioned_srcs:
                out_srcs = collections.OrderedDict()
                out_resources = collections.OrderedDict()
                for dst, src in (
                        self.without_platforms(
                            self.format_sources(ver_srcs))).items():
                    if dst.endswith('.py') or dst.endswith('.so'):
                        out_srcs[dst] = src
                    else:
                        out_resources[dst] = src
                out_versioned_srcs.append((vcollection, out_srcs))
                out_versioned_resources.append((vcollection, out_resources))
            if out_versioned_srcs:
                attributes['versioned_srcs'] = out_versioned_srcs
            if out_versioned_resources:
                attributes['versioned_resources'] = out_versioned_resources

        dependencies = []
        if self.is_tp2(base_path):
            dependencies.append(self.get_tp2_project_dep(base_path))
        for target in deps:
            dependencies.append(
                self.convert_build_target(base_path, target))
        if cpp_deps:
            dependencies.extend(cpp_deps)
        if dependencies:
            attributes['deps'] = dependencies

        attributes['tests'] = tests

        if visibility is not None:
            attributes['visibility'] = visibility

        if external_deps:
            attributes['platform_deps'] = (
                self.format_platform_deps(
                    # We support the auxiliary versions hack for neteng/Django.
                    self.convert_auxiliary_deps(
                        self.to_platform_param(
                            [
                                self.normalize_external_dep(
                                    dep,
                                    lang_suffix='-py',
                                    parse_version=True)
                                for dep in external_deps
                            ]))))

        if self.is_test():
            attributes['labels'] = ['unittest-library']

        return Rule('python_library', attributes)

    def create_binary(
        self,
        base_path,
        name,
        library,
        tests=[],
        py_version=None,
        main_module=None,
        rule_type=None,
        strip_libpar=True,
        tags=(),
        lib_dir=None,
        par_style=None,
        emails=None,
        needed_coverage=None,
        argcomplete=None,
        strict_tabs=None,
        compile=None,
        args=None,
        env=None,
        python=None,
        allocator=None,
        check_types=False,
        preload_deps=(),
        jemalloc_conf=None,
        typing_options='',
        helper_deps=False,
        visibility=None,
    ):
        rules = []
        dependencies = []
        platform_deps = []
        out_preload_deps = []
        platform = self.get_platform(base_path)
        python_version = self.get_python_version(py_version)
        python_platform = self.get_python_platform(platform, python_version)

        if allocator is None:
            # Default gcc-5 platforms to jemalloc (as per S146810).
            if self.get_tool_version(platform, 'gcc') >= LooseVersion('5'):
                allocator = 'jemalloc'
            else:
                allocator = 'malloc'

        attributes = collections.OrderedDict()
        attributes['name'] = name
        if visibility is not None:
            attributes['visibility'] = visibility

        if not rule_type:
            rule_type = self.get_buck_rule_type()

        # If this is a test, we need to merge the library rule into this
        # one and inherit its deps.
        if self.is_test():
            for param in ('versioned_srcs', 'srcs', 'resources', 'base_module'):
                val = library.attributes.get(param)
                if val is not None:
                    attributes[param] = val
            dependencies.extend(library.attributes.get('deps', []))
            platform_deps.extend(library.attributes.get('platform_deps', []))

            # Add the "coverage" library as a dependency for all python tests.
            platform_deps.extend(
                self.format_platform_deps(
                    self.to_platform_param(
                        [ThirdPartyRuleTarget('coverage', 'coverage-py')])))

        # Otherwise, this is a binary, so just the library portion as a dep.
        else:
            dependencies.append(':' + library.attributes['name'])

        # Sanitize the main module, so that it's a proper module reference.
        if main_module is not None:
            main_module = main_module.replace('/', '.')
            if main_module.endswith('.py'):
                main_module = main_module[:-3]
            attributes['main_module'] = main_module
        elif self.is_test():
            main_module = '__fb_test_main__'
            attributes['main_module'] = main_module

        # Add in the PAR build args.
        if self.get_package_style() == 'standalone':
            build_args = (
                self.get_par_build_args(
                    base_path,
                    name,
                    rule_type,
                    platform,
                    argcomplete=argcomplete,
                    strict_tabs=strict_tabs,
                    compile=compile,
                    par_style=par_style,
                    strip_libpar=strip_libpar,
                    needed_coverage=needed_coverage,
                    python=python))
            if build_args:
                attributes['build_args'] = build_args

        # Add any special preload deps.
        default_preload_deps, default_preload_rules = (
            self.get_preload_deps(base_path, name, allocator, jemalloc_conf, visibility))
        out_preload_deps.extend(self.format_deps(default_preload_deps))
        rules.extend(default_preload_rules)

        # Add user-provided preloaded deps.
        for dep in preload_deps:
            out_preload_deps.append(self.convert_build_target(base_path, dep))

        # Add the C/C++ build info lib to preload deps.
        cxx_build_info, cxx_build_info_rules = (
            self.create_cxx_build_info_rule(
                base_path,
                name,
                self.get_fbconfig_rule_type(),
                platform,
                static=False,
                visibility=visibility))
        out_preload_deps.append(self.get_dep_target(cxx_build_info))
        rules.extend(cxx_build_info_rules)

        # Provide a standard set of backport deps to all binaries
        platform_deps.extend(
            self.format_platform_deps(
                self.to_platform_param(
                    [ThirdPartyRuleTarget('typing', 'typing-py'),
                     ThirdPartyRuleTarget('python-future', 'python-future-py')])))

        # Add in a specialized manifest when building inplace binaries.
        #
        # TODO(#11765906):  We shouldn't need to create this manifest rule for
        # standalone binaries.  However, since target determinator runs in dev
        # mode, we sometimes pass these manifest targets in the explicit target
        # list into `opt` builds, which then fails with a missing build target
        # error.  So, for now, just always generate the manifest library, but
        # only use it when building inplace binaries.
        manifest_name, manifest_rules = (
            self.generate_manifest(
                base_path,
                name,
                main_module,
                platform,
                python_version,
                visibility))
        rules.extend(manifest_rules)
        if self.get_package_style() == 'inplace':
            dependencies.append(':' + manifest_name)

        attributes['cxx_platform'] = platform
        attributes['platform'] = python_platform
        attributes['version_universe'] = (
            self.get_version_universe(python_version))
        attributes['linker_flags'] = (
            self.get_ldflags(base_path, name, strip_libpar=strip_libpar))

        if self.is_test():
            attributes['labels'] = (
                self.convert_labels(platform, 'python', *tags))

        attributes['tests'] = tests

        if args:
            attributes['args'] = self.convert_args_with_macros(base_path, args)

        if env:
            attributes['env'] = self.convert_env_with_macros(base_path, env)

        if emails:
            attributes['contacts'] = emails

        if out_preload_deps:
            attributes['preload_deps'] = out_preload_deps

        if needed_coverage:
            attributes['needed_coverage'] = [
                self.convert_needed_coverage_spec(base_path, s)
                for s in needed_coverage
            ]

        # Generate the interpreter helpers, and add them to our deps. Note that
        # we must do this last, so that the interp rules get the same deps as
        # the main binary which we've built up to this point.
        if self.should_generate_interp_rules(helper_deps):
            interp_deps = list(dependencies)
            if self.is_test():
                rules.extend(self.gen_test_modules(base_path, library, visibility))
                interp_deps.append(
                    ':{}-testmodules-lib'.format(library.attributes['name'])
                )
            interp_rules = (
                self.convert_interp_rules(
                    name,
                    platform,
                    python_version,
                    python_platform,
                    interp_deps,
                    platform_deps,
                    out_preload_deps,
                    visibility))
            rules.extend(interp_rules)
            dependencies.extend(
                ':' + r.attributes['name'] for r in interp_rules)
        if check_types:
            if not (self.matches_py3(python_version)
                    or self.matches_pypy(python_version)):
                raise ValueError(
                    'parameter `check_types` is only supported on Python 3.'
                )
            rules.extend(
                self.create_typecheck(
                    name,
                    main_module,
                    platform,
                    python_platform,
                    library,
                    dependencies,
                    platform_deps,
                    out_preload_deps,
                    typing_options,
                    visibility
                ),
            )
            attributes['tests'] = (
                list(attributes['tests']) + [':{}-typecheck'.format(name)]
            )

        if self.is_test():
            if not dependencies:
                dependencies = []
            dependencies.append('//python:fbtestmain')

        if dependencies:
            attributes['deps'] = dependencies

        if platform_deps:
            attributes['platform_deps'] = platform_deps

        if (
            self.read_bool('fbcode', 'monkeytype', False) and
            (self.matches_py3(python_version)
                or self.matches_pypy(python_version))
        ):
            rules.extend(
                self.create_monkeytype_rules(rule_type, attributes, library)
            )

        return [Rule(rule_type, attributes)] + rules

    def convert(
        self,
        base_path,
        name=None,
        py_version=None,
        base_module=None,
        main_module=None,
        strip_libpar=True,
        srcs=(),
        versioned_srcs=(),
        tags=(),
        gen_srcs=(),
        deps=[],
        tests=[],
        lib_dir=None,
        par_style=None,
        emails=None,
        external_deps=[],
        needed_coverage=None,
        output_subdir=None,
        argcomplete=None,
        strict_tabs=None,
        compile=None,
        args=None,
        env=None,
        python=None,
        allocator=None,
        check_types=False,
        preload_deps=(),
        visibility=None,
        jemalloc_conf=None,
        typing=False,
        typing_options='',
        check_types_options='',
        runtime_deps=(),
        cpp_deps=(),  # ctypes targets
        helper_deps=False,
    ):
        # for binary we need a separate library
        if self.is_library():
            library_name = name
        else:
            library_name = name + '-library'

        if get_typing_config_target():
            yield self.gen_typing_config(
                library_name,
                base_module if base_module is not None else base_path,
                srcs,
                [self.convert_build_target(base_path, dep) for dep in deps],
                typing,
                typing_options,
                visibility,
            )

        if runtime_deps:
            rule = self.gen_associated_targets(library_name, runtime_deps, visibility)
            deps = list(deps) + [rule.target_name]
            yield rule

        library = self.create_library(
            base_path,
            library_name,
            base_module=base_module,
            srcs=srcs,
            versioned_srcs=versioned_srcs,
            gen_srcs=gen_srcs,
            deps=deps,
            tests=tests,
            external_deps=external_deps,
            visibility=visibility,
            cpp_deps=cpp_deps,
        )

        # People use -library of unittests
        yield library

        if self.is_library():
            # If we are a library then we are done now
            return

        # For binary rules, create a separate library containing the sources.
        # This will be added as a dep for python binaries and merged in for
        # python tests.
        if isinstance(py_version, list) and len(py_version) == 1:
            py_version = py_version[0]

        if not isinstance(py_version, list):
            versions = {py_version: name}
        else:
            versions = {}
            for py_ver in py_version:
                python_version = self.get_python_version(py_ver)
                new_name = name + '-' + python_version
                versions[py_ver] = new_name
        py_tests = []
        rule_names = set()
        for py_ver, py_name in sorted(versions.items()):
            rules = self.create_binary(
                base_path,
                py_name,
                library,
                tests=tests,
                py_version=py_ver,
                main_module=main_module,
                strip_libpar=strip_libpar,
                tags=tags,
                lib_dir=lib_dir,
                par_style=par_style,
                emails=emails,
                needed_coverage=needed_coverage,
                argcomplete=argcomplete,
                strict_tabs=strict_tabs,
                compile=compile,
                args=args,
                env=env,
                python=python,
                allocator=allocator,
                check_types=check_types,
                preload_deps=preload_deps,
                jemalloc_conf=jemalloc_conf,
                typing_options=check_types_options,
                helper_deps=helper_deps,
                visibility=visibility,
            )
            if self.is_test():
                py_tests.append(':' + py_name)
            for rule in rules:
                if rule.target_name not in rule_names:
                    yield rule
                    rule_names.add(rule.target_name)

        # Create a genrule to wrap all the tests for easy running
        if len(py_tests) > 1:
            attrs = collections.OrderedDict()
            attrs['name'] = name
            if visibility is not None:
                attrs['visibility'] = visibility
            attrs['out'] = os.curdir
            attrs['tests'] = py_tests
            # With this we are telling buck we depend on the test targets
            cmds = []
            for test in py_tests:
                cmds.append('echo $(location {})'.format(test))
            attrs['cmd'] = ' && '.join(cmds)
            yield Rule('genrule', attrs)

    def create_typecheck(
        self,
        name,
        main_module,
        platform,
        python_platform,
        library,
        deps,
        platform_deps,
        preload_deps,
        typing_options,
        visibility,
    ):

        typing_config = get_typing_config_target()

        typecheck_deps = deps[:]
        if ':python_typecheck-library' not in typecheck_deps:
            # Buck doesn't like duplicate dependencies.
            typecheck_deps.append('//libfb/py:python_typecheck-library')

        if not typing_config:
            typecheck_deps.append('//python/typeshed_internal:global_mypy_ini')

        attrs = collections.OrderedDict((
            ('name', name + '-typecheck'),
            ('main_module', 'python_typecheck'),
            ('cxx_platform', platform),
            ('platform', python_platform),
            ('deps', typecheck_deps),
            ('platform_deps', platform_deps),
            ('preload_deps', preload_deps),
            ('package_style', 'inplace'),
            # TODO(ambv): labels here shouldn't be hard-coded.
            ('labels', ['buck', 'python']),
            ('version_universe',
             self.get_version_universe(self.get_py3_version())),
        ))
        if visibility is not None:
            attrs['visibility'] = visibility

        if library.target_name not in typecheck_deps:
            # If the passed library is not a dependency, add its sources here.
            # This enables python_unittest targets to be type-checked, too.
            for param in ('versioned_srcs', 'srcs', 'resources', 'base_module'):
                val = library.attributes.get(param)
                if val is not None:
                    attrs[param] = val

        if main_module != '__fb_test_main__':
            # Tests are properly enumerated from passed sources (see above).
            # For binary targets, we need this subtle hack to let
            # python_typecheck know where to start type checking the program.
            attrs['env'] = {"PYTHON_TYPECHECK_ENTRY_POINT": main_module}

        if typing_config:
            conf = collections.OrderedDict()
            conf['name'] = name + '-typing=mypy.ini'
            if visibility is not None:
                conf['visibility'] = visibility
            conf['out'] = os.curdir
            cmd = '$(exe {}) gather '.format(typing_config)
            if typing_options:
                cmd += '--options="{}" '.format(typing_options)
            cmd += '$(location {}-typing) $OUT'.format(library.target_name)
            conf['cmd'] = cmd
            conf['out'] = 'mypy.ini'
            gen_rule = Rule('genrule', conf)
            yield gen_rule
            conf = collections.OrderedDict()
            conf['name'] = name + '-mypy_ini'
            if visibility is not None:
                conf['visibility'] = visibility
            conf['base_module'] = ''
            conf['srcs'] = [gen_rule.target_name]
            mypy_ini = Rule('python_library', conf)
            yield mypy_ini
            typecheck_deps.append(mypy_ini.target_name)

        yield Rule('python_test', attrs)

    def create_monkeytype_rules(
        self,
        rule_type,
        attributes,
        library,
    ):
        rules = []
        name = attributes['name']
        visibility = attributes['visibility']
        lib_main_module_attrs_name = None
        if 'main_module' in attributes:
            # we need to preserve the original main_module, so we inject a
            # library with a module for it that the main wrapper picks up
            main_module_attrs = collections.OrderedDict()
            main_module_attrs['name'] = name + '-monkeytype_main_module'
            if visibility is not None:
                main_module_attrs['visibility'] = visibility
            main_module_attrs['out'] = name + '-__monkeytype_main_module__.py'
            main_module_attrs['cmd'] = (
                'echo {} > $OUT'.format(pipes.quote(
                    "#!/usr/bin/env python3\n\n"
                    "def monkeytype_main_module() -> str:\n"
                    "    return '{}'\n".format(
                        attributes['main_module']
                    )
                ))
            )
            rules.append(Rule('genrule', main_module_attrs))
            lib_main_module_attrs_name = name + '-monkeytype_main_module-lib'
            lib_main_module_attrs = collections.OrderedDict()
            lib_main_module_attrs['name'] = lib_main_module_attrs_name
            if visibility is not None:
                lib_main_module_attrs['visibility'] = visibility
            lib_main_module_attrs['base_module'] = ''
            lib_main_module_attrs['deps'] = ['//python:fbtestmain', ':' + name]
            lib_main_module_attrs['srcs'] = {
                '__monkeytype_main_module__.py': ':' + main_module_attrs['name']
            }
            rules.append(Rule('python_library', lib_main_module_attrs))

        # Create a variant of the target that is running with monkeytype
        wrapper_attrs = attributes.copy()
        wrapper_attrs['name'] = name + '-monkeytype'
        if visibility is not None:
            wrapper_attrs['visibility'] = visibility
        if 'deps' in wrapper_attrs:
            wrapper_deps = list(wrapper_attrs['deps'])
        else:
            wrapper_deps = []
        if ':' + library.attributes['name'] not in wrapper_deps:
            wrapper_deps.append(':' + library.attributes['name'])
        stub_gen_deps = list(wrapper_deps)

        if '//python/monkeytype:main_wrapper' not in wrapper_deps:
            wrapper_deps.append('//python/monkeytype/tools:main_wrapper')
        if lib_main_module_attrs_name is not None:
            wrapper_deps.append(':' + lib_main_module_attrs_name)
        wrapper_attrs['deps'] = wrapper_deps
        wrapper_attrs['base_module'] = ''
        wrapper_attrs['main_module'] = 'python.monkeytype.tools.main_wrapper'
        rules.append(Rule(rule_type, wrapper_attrs))

        if '//python/monkeytype/tools:stubs_lib' not in wrapper_deps:
            stub_gen_deps.append('//python/monkeytype/tools:stubs_lib')

        # And create a target that can be used for stub creation
        stub_gen_attrs = collections.OrderedDict((
            ('name', attributes['name'] + '-monkeytype-gen-stubs'),
            ('visibility', visibility),
            ('main_module', 'python.monkeytype.tools.get_stub'),
            ('cxx_platform', attributes['cxx_platform']),
            ('platform', attributes['platform']),
            ('deps', stub_gen_deps),
            ('platform_deps', attributes['platform_deps']),
            ('preload_deps', attributes['preload_deps']),
            ('package_style', 'inplace'),
            ('version_universe', attributes['version_universe']),
        ))
        rules.append(Rule('python_binary', stub_gen_attrs))
        return rules

    def gen_test_modules(self, base_path, library, visibility):
        lines = ['TEST_MODULES = [']
        for src in sorted(library.attributes.get('srcs') or ()):
            lines.append(
                '    "{}",'.format(
                    self.file_to_python_module(
                        src,
                        library.attributes.get('base_module') or base_path,
                    )
                )
            )
        lines.append(']')

        name = library.attributes['name']
        gen_attrs = collections.OrderedDict()
        gen_attrs['name'] = name + '-testmodules'
        if visibility is not None:
            gen_attrs['visibility'] = visibility
        gen_attrs['out'] = name + '-__test_modules__.py'
        gen_attrs['cmd'] = ' && '.join(
            'echo {} >> $OUT'.format(pipes.quote(line))
            for line in lines
        )
        yield Rule('genrule', gen_attrs)

        lib_attrs = collections.OrderedDict()
        lib_attrs['name'] = name + '-testmodules-lib'
        if visibility is not None:
            lib_attrs['visibility'] = visibility
        lib_attrs['base_module'] = ''
        lib_attrs['deps'] = ['//python:fbtestmain', ':' + name]
        lib_attrs['srcs'] = {'__test_modules__.py': ':' + gen_attrs['name']}
        yield Rule('python_library', lib_attrs)

    def file_to_python_module(self, src, base_module):
        """Python implementation of Buck's toModuleName().

        Original in com.facebook.buck.python.PythonUtil.toModuleName.
        """
        src = os.path.join(base_module, src)
        src, ext = os.path.splitext(src)
        return src.replace('/', '.')  # sic, not os.sep
