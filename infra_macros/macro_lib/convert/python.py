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
build_info = import_macro_lib('build_info')
load("@fbcode_macros//build_defs:compiler.bzl", "compiler")
load("@fbcode_macros//build_defs:platform_utils.bzl", "platform_utils")
load("@fbcode_macros//build_defs:python_typing.bzl",
     "get_typing_config_target")
load("@fbcode_macros//build_defs:sanitizers.bzl", "sanitizers")
load("@fbcode_macros//build_defs:label_utils.bzl", "label_utils")
load("@fbcode_macros//build_defs:target_utils.bzl", "target_utils")
load("@fbcode_macros//build_defs:third_party.bzl", "third_party")


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
        self.__file__ = __file__
        self.__name__ = __name__

    @property
    def modules(self):
        if self._modules is None:
            import os, sys
            modules = set()
            for root, dirs, files in os.walk(sys.path[0]):
                rel_root = os.path.relpath(root, sys.path[0])
                if rel_root == '.':
                    package_prefix = ''
                else:
                    package_prefix = rel_root.replace(os.sep, '.') + '.'

                for name in files:
                    base, ext = os.path.splitext(name)
                    # Note that this loop includes all *.so files, regardless
                    # of whether they are actually python modules or just
                    # regular dynamic libraries
                    if ext in ('.py', '.pyc', '.pyo', '.so'):
                        if rel_root == "." and base == "__manifest__":
                            # The manifest generation logic for normal pars
                            # does not include the __manifest__ module itself
                            continue
                        modules.add(package_prefix + base)
                # Skip __pycache__ directories
                try:
                    dirs.remove("__pycache__")
                except ValueError:
                    pass
            self._modules = sorted(modules)
        return self._modules

    fbmake = {{
        {fbmake}
    }}


sys.modules[__name__] = Manifest()
"""


DEFAULT_MAJOR_VERSION = '3'
VERSION_CONSTRAINT_SHORTCUTS = {
    2   : '2',
    '2' : '2',
    3   : '3',
    '3' : '3',
}


class PythonVersionConstraint(object):
    """An abstraction for Python version constraints.

    This class implements the semantics of the `py_version` and `versioned_srcs`
    parameters of the 'python_xxx' rule types.

    """

    # Bit masks for partial matching:
    MAJOR = 1
    MINOR = 2
    PATCHLEVEL = 4
    FLAVOR = 8

    def __init__(self, vcstring):
        self.op = None
        self.version = None
        # By default, we allow constraints to place restrictions on flavor, e.g.
        # constraints such as ">flavor.3" should work as expected:
        self.flags = PythonVersionConstraint.FLAVOR
        if vcstring:
            self.parse(vcstring)
        else:
            # No explicit constraint specified, in which case we fallback to a
            # partial match for DEFAULT_MAJOR_VERSION:
            self.version = PythonVersion(DEFAULT_MAJOR_VERSION)
            self.flags |= PythonVersionConstraint.MAJOR

    def enable_flag(self, mask):
        self.flags |= mask

    def disable_flag(self, mask):
        self.flags &= ~mask

    def parse(self, vcstring):
        """
        Parse the given `vcstring` into callable which tests a `LooseVersion`
        object.
        """

        # Constraint shortcuts allow the user to restrict to a particular major
        # version:
        if vcstring in VERSION_CONSTRAINT_SHORTCUTS:
            vstring = VERSION_CONSTRAINT_SHORTCUTS[vcstring]
            self.flags = PythonVersionConstraint.MAJOR
        elif vcstring.startswith('<='):
            vstring = vcstring[2:].lstrip()
            self.op = operator.le
        elif vcstring.startswith('>='):
            vstring = vcstring[2:].lstrip()
            self.op = operator.ge
        elif vcstring.startswith('<'):
            vstring = vcstring[1:].lstrip()
            self.op = operator.lt
        elif vcstring.startswith('='):
            vstring = vcstring[1:].lstrip()
            self.op = operator.eq
        elif vcstring.startswith('>'):
            vstring = vcstring[1:].lstrip()
            self.op = operator.gt
        else:
            vstring = vcstring

        # We parse the version substring using `PythonVersion` so that flavored
        # versions can be properly handled:
        self.version = PythonVersion(vstring)

    def matches(self, version, flags=0):
        """
        True if this constraint can be satisfied by the given `version`.
        """

        # A trivial constraint matches everything:
        if self.version is None:
            return True

        # Combine explicit and implicit flags:
        flags |= self.flags
        # First make sure flavors are compatible:
        if flags & PythonVersionConstraint.FLAVOR and \
           not version.supports(self.version.flavor):
            return False

        # Then perform version number matching...
        # Operator matching takes precedence:
        if self.op:
            return self.op(version, self.version)
        # followed by partial matching:
        elif flags ^ PythonVersionConstraint.FLAVOR:
            return ((not flags & PythonVersionConstraint.MAJOR or
                     version.major == self.version.major) and
                    (not flags & PythonVersionConstraint.MINOR or
                     version.minor == self.version.minor) and
                    (not flags & PythonVersionConstraint.PATCHLEVEL or
                     version.patchlevel == self.version.patchlevel))
        # and finally default to simple equality matching:
        else:
            return self.version == version


class PythonVersion(LooseVersion):
    """An abstraction of tp2/python version strings that supports flavor prefixes.

    See `get_python_platforms_config()` in `tools/build/buck/gen_modes.py` for
    the format of flavored version strings.

    """

    def __init__(self, vstring):
        LooseVersion.__init__(self, vstring)
        if not self.version:
            raise ValueError('{} is not a valid Python version string!'
                             .format(vstring))

        self.flavor = ""
        if isinstance(self.version[0], basestring):
            self.flavor = self.version[0]
            self.version = self.version[1:]

        if not self.version or not isinstance(self.version[0], int):
            raise ValueError("{} is not a valid Python version string!"
                             .format(vstring))

    @property
    def major(self):
        return self.version[0]

    @property
    def minor(self):
        return self.version[1] if len(self.version) > 1 else None

    @property
    def patchlevel(self):
        return self.version[2] if len(self.version) > 2 else None

    def supports(self, flavor):
        """
        True if this version supports the given `flavor`.
        """
        return self.flavor.endswith(flavor)

    def satisfies(self, constraint, flags=0):
        """
        True if this version can satisfy `constraint`.
        """
        if not isinstance(constraint, PythonVersionConstraint):
            constraint = PythonVersionConstraint(constraint)
        return constraint.matches(self, flags)


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
                if not target_utils.is_rule_target(src):
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
                    .format(param, target_utils.target_to_label(src), GEN_SRCS_LINK))

        return out_srcs

    def parse_gen_srcs(self, base_path, srcs):  # type: (str, Union[List[str], Dict[str, str]]) -> Dict[str, Union[str, RuleTarget]]
        """
        Parse the given sources as input to the `gen_srcs` parameter.
        """

        out_srcs = self.parse_srcs(base_path, 'gen_srcs', srcs)

        # Do a final pass to verify that all sources in `gen_srcs` are rule
        # references.
        for src in out_srcs.itervalues():
            if not target_utils.is_rule_target(src):
                raise ValueError(
                    'parameter `gen_srcs`: `{}` must be a reference to rule '
                    'that generates a source (e.g. `//foo:bar`, `:bar`) '
                    ' (see {} for details).'
                    .format(src, GEN_SRCS_LINK))

        return out_srcs

    def matches_major(self, constraint, version):
        """
        True if `constraint` can be satisfied by a Python version that is of
        major `version` on some active platform.
        """

        return any(pv.major == version and pv.satisfies(constraint)
                   for pv in self.get_all_versions())

    def get_all_versions(self, platform=None):
        """
        Returns a list of `PythonVersion` instances corresponding to the active
        Python versions for the given `platform`. If `platform` is not
        specified, then return versions for all platforms.
        """

        confs = [third_party.get_third_party_config_for_platform(p)['build']['projects']['python']
                 for p in self.get_platforms()
                 if platform is None or p == platform]
        versions = set(version_str
                       for pyconf in confs
                       # pyconf is a list of pairs:
                       # (ORIGINAL_TP2_VERSION, ACTUAL_VERSION)
                       for _, version_str in pyconf)
        return list(PythonVersion(vstr) for vstr in versions)

    def get_default_version(self, platform, constraint, flavor=""):
        """
        Returns a `PythonVersion` instance corresponding to the first Python
        version that satisfies `constraint` and `flavor` for the given
        `platform`.
        """

        pyconf = third_party.get_third_party_config_for_platform(platform)['build']['projects']['python']
        for _, version_str in pyconf:
            version = PythonVersion(version_str)
            if version.satisfies(constraint) and version.supports(flavor):
                return version
        return None

    def platform_has_version(self, platform, version):
        """
        True if the Python `version` is configured for `platform`.
        """
        pyconf = third_party.get_third_party_config_for_platform(platform)['build']['projects']['python']
        for _, version_str in pyconf:
            if version_str == version.vstring:
                return True
        return False

    def get_interpreter(self, platform):
        return self.read_string('python#' + platform, 'interpreter')

    def get_version_universe(self, python_version):
        return super(PythonConverter, self).get_version_universe(
            [('python', python_version.vstring)])

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
            python_platform):
        """
        Return the build info attributes to install for python rules.
        """

        py_build_info = collections.OrderedDict()

        py_build_info['main_module'] = main_module
        py_build_info['par_style'] = 'live'

        interp = self.get_interpreter(python_platform)
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
            python_platform,
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
                python_platform))
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
                    platform,
                    compiler.get_compiler_for_current_buildfile()))
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
            base_path,
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
            attrs['cxx_platform'] = platform_utils.get_buck_platform_for_base_path(base_path)
            attrs['platform'] = python_platform
            attrs['version_universe'] = self.get_version_universe(python_version)
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
        buck_platform = platform_utils.get_buck_platform_for_base_path(base_path)
        attrs['default_platform'] = buck_platform
        attrs['defaults'] = {'platform': buck_platform}
        lib_rule = Rule('cxx_library', attrs)
        rules.append(lib_rule)

        return target_utils.RootRuleTarget(base_path, lib_rule.attributes['name']), rules

    def get_preload_deps(self, base_path, name, allocator, jemalloc_conf=None, visibility=None):
        """
        Add C/C++ deps which need to preloaded by Python binaries.
        """

        deps = []
        rules = []

        sanitizer = sanitizers.get_sanitizer()

        # If we're using sanitizers, add the dep on the sanitizer-specific
        # support library.
        if sanitizer is not None:
            sanitizer = sanitizers.get_short_name(sanitizer)
            deps.append(
                target_utils.RootRuleTarget(
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

    def gen_associated_targets(self, base_path, name, targets, visibility):
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
        buck_platform = platform_utils.get_buck_platform_for_base_path(base_path)
        attrs['default_platform'] = buck_platform
        attrs['defaults'] = {'platform': buck_platform}
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
        py_flavor="",
    ):
        attributes = collections.OrderedDict()
        attributes['name'] = name

        # Normalize all the sources from the various parameters.
        parsed_srcs = {}  # type: Dict[str, Union[str, RuleTarget]]
        parsed_srcs.update(self.parse_srcs(base_path, 'srcs', srcs))
        parsed_srcs.update(self.parse_gen_srcs(base_path, gen_srcs))

        # Parse the version constraints and normalize all source paths in
        # `versioned_srcs`:
        parsed_versioned_srcs = tuple((PythonVersionConstraint(pvc),
                                       self.parse_srcs(base_path,
                                                       'versioned_srcs',
                                                       vs))
                                      for pvc, vs in versioned_srcs)

        # Contains a mapping of platform name to sources to use for that
        # platform.
        all_versioned_srcs = []

        # If we're TP project, install all sources via the `versioned_srcs`
        # parameter. `py_flavor` is ignored since flavored Pythons are only
        # intended for use by internal projects.
        if self.is_tp2(base_path):

            # TP2 projects have multiple "pre-built" source dirs, so we install
            # them via the `versioned_srcs` parameter along with the versions
            # of deps that was used to build them, so that Buck can select the
            # correct one based on version resolution.
            project_builds = self.get_tp2_project_builds(base_path)
            for build in project_builds.values():
                build_srcs = [parsed_srcs]
                if parsed_versioned_srcs:
                    py_vers = PythonVersion(build.versions['python'])
                    build_srcs.extend(
                        dict(vs) for vc, vs in parsed_versioned_srcs
                        if vc.matches(py_vers,
                                      (PythonVersionConstraint.MAJOR |
                                       PythonVersionConstraint.MINOR)))

                vsrc = {}
                for build_src in build_srcs:
                    for name, src in build_src.items():
                        if target_utils.is_rule_target(src):
                            vsrc[name] = src
                        else:
                            vsrc[name] = os.path.join(build.subdir, src)

                all_versioned_srcs.append((build.project_deps, vsrc))

            # Reset `srcs`, since we're using `versioned_srcs`.
            parsed_srcs = {}

        # If we're an fbcode project, and `py_flavor` is not specified, then
        # keep the regular sources parameter and only use the `versioned_srcs`
        # parameter for the input parameter of the same name; if `py_flavor` is
        # specified, then we have to install all sources via `versioned_srcs`
        else:
            pytarget = self.get_tp2_project_target('python')
            platforms = self.get_platforms()

            # Iterate over all potential Python versions and collect srcs for
            # each version:
            for pyversion in self.get_all_versions():
                if not pyversion.supports(py_flavor):
                    continue

                ver_srcs = {}
                if py_flavor:
                    ver_srcs.update(parsed_srcs)

                for constraint, pvsrcs in parsed_versioned_srcs:
                    if pyversion.satisfies(constraint):
                        ver_srcs.update(pvsrcs)
                if ver_srcs:
                    all_versioned_srcs.append(
                        ({target_utils.target_to_label(pytarget, platform=p) :
                          pyversion.vstring
                          for p in platforms
                          if self.platform_has_version(p, pyversion)},
                         ver_srcs))

            if py_flavor:
                parsed_srcs = {}

        if base_module is not None:
            attributes['base_module'] = base_module

        if parsed_srcs:
            # Need to split the srcs into srcs & resources as Buck
            # expects all test srcs to be python modules.
            if self.is_test():
                attributes['srcs'], attributes['platform_srcs'] = (
                    self.format_source_map(
                        {k: v
                         for k, v in parsed_srcs.iteritems()
                         if k.endswith('.py')}))
                attributes['resources'], attributes['platform_resources'] = (
                    self.format_source_map(
                        {k: v
                         for k, v in parsed_srcs.iteritems()
                         if not k.endswith('.py')}))
            else:
                attributes['srcs'], attributes['platform_srcs'] = (
                    self.format_source_map(parsed_srcs))

        # Emit platform-specific sources.  We split them between the
        # `platform_srcs` and `platform_resources` parameter based on their
        # extension, so that directories with only resources don't end up
        # creating stray `__init__.py` files for in-place binaries.
        out_versioned_srcs = []
        out_versioned_resources = []
        for vcollection, ver_srcs in all_versioned_srcs:
            out_srcs = collections.OrderedDict()
            out_resources = collections.OrderedDict()
            for dst, src in (
                    self.without_platforms(
                        self.format_source_map(ver_srcs))).items():
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
                    [self.normalize_external_dep(
                         dep,
                         lang_suffix='-py',
                         parse_version=True)
                     for dep in external_deps],
                    # We support the auxiliary versions hack for neteng/Django.
                    deprecated_auxiliary_deps=True))

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
        py_flavor="",
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
        analyze_imports=False,
    ):
        if self.is_test() and par_style is None:
            par_style = "xar"
        rules = []
        dependencies = []
        platform_deps = []
        out_preload_deps = []
        platform = self.get_platform(base_path)
        python_version = self.get_default_version(platform=platform,
                                                  constraint=py_version,
                                                  flavor=py_flavor)
        if python_version is None:
            raise ValueError("Unable to find Python version matching constraint"
                             " '{}' and flavor '{}' on '{}'."
                             .format(py_version, py_flavor, platform))

        python_platform = self.get_python_platform(platform,
                                                   major_version=python_version.major,
                                                   flavor=py_flavor)

        if allocator is None:
            allocator = self.get_allocator(allocator)

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
                    [target_utils.ThirdPartyRuleTarget('coverage', 'coverage-py')]))

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
        out_preload_deps.append(target_utils.target_to_label(cxx_build_info))
        rules.extend(cxx_build_info_rules)

        # Provide a standard set of backport deps to all binaries
        platform_deps.extend(
            self.format_platform_deps(
                [target_utils.ThirdPartyRuleTarget('typing', 'typing-py'),
                 target_utils.ThirdPartyRuleTarget('python-future', 'python-future-py')]))

        # Provide a hook for the nuclide debugger in @mode/dev builds, so
        # that one can have `PYTHONBREAKPOINT=nuclide.set_trace` in their
        # environment (eg .bashrc) and then simply write `breakpoint()`
        # to launch a debugger with no fuss
        if self.get_package_style() == "inplace":
            dependencies.append("//nuclide:debugger-hook")

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
                python_platform,
                visibility))
        rules.extend(manifest_rules)
        if self.get_package_style() == 'inplace':
            dependencies.append(':' + manifest_name)

        attributes['cxx_platform'] = platform_utils.get_buck_platform_for_base_path(base_path)
        attributes['platform'] = python_platform
        attributes['version_universe'] = self.get_version_universe(python_version)
        attributes['linker_flags'] = (
            self.get_ldflags(base_path, name, strip_libpar=strip_libpar))

        attributes['labels'] = list(tags)
        if self.is_test():
            attributes['labels'].extend(label_utils.convert_labels(platform, 'python'))

        attributes['tests'] = tests

        if args:
            attributes['args'] = (
                self.convert_args_with_macros(
                    base_path,
                    args,
                    platform=platform))

        if env:
            attributes['env'] = (
                self.convert_env_with_macros(
                    base_path,
                    env,
                    platform=platform))

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
                    base_path,
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
            if python_version.major != 3:
                raise ValueError(
                    'parameter `check_types` is only supported on Python 3.'
                )
            rules.extend(
                self.create_typecheck(
                    base_path,
                    name,
                    main_module,
                    platform,
                    python_platform,
                    python_version,
                    library,
                    dependencies,
                    platform_deps,
                    out_preload_deps,
                    typing_options,
                    visibility,
                    emails,
                ),
            )
            attributes['tests'] = (
                list(attributes['tests']) + [':{}-typecheck'.format(name)]
            )
        if analyze_imports:
            rules.extend(
                self.create_analyze_imports(
                    base_path,
                    name,
                    main_module,
                    platform,
                    python_platform,
                    library,
                    dependencies,
                    platform_deps,
                    preload_deps,
                    typing_options,
                    visibility
                )
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
            python_version.major == 3
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
        py_flavor="",
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
        analyze_imports=False,
    ):
        # for binary we need a separate library
        if self.is_library():
            library_name = name
        else:
            library_name = name + '-library'

        if self.is_library() and check_types:
            raise ValueError(
                'parameter `check_types` is not supported for libraries, did you mean to specify `typing`?'
            )

        if get_typing_config_target():
            yield self.gen_typing_config(
                library_name,
                base_module if base_module is not None else base_path,
                srcs,
                [self.convert_build_target(base_path, dep) for dep in deps],
                typing or (check_types and not self.is_library()),
                typing_options,
                visibility,
            )

        if runtime_deps:
            rule = self.gen_associated_targets(base_path, library_name, runtime_deps, visibility)
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
            py_flavor=py_flavor,
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
            platform = self.get_platform(base_path)
            for py_ver in py_version:
                python_version = self.get_default_version(platform, py_ver)
                new_name = name + '-' + python_version.vstring
                versions[py_ver] = new_name
        py_tests = []
        rule_names = set()
        for py_ver, py_name in sorted(versions.items()):
            # Turn off check types for py2 targets when py3 is in versions
            # so we can have the py3 parts type check without a separate target
            if (
                check_types
                and self.matches_major(py_ver, version=2)
                and any(self.matches_major(v, version=3) for v in versions)
            ):
                _check_types = False
                print(
                    base_path + ':' + py_name,
                    'will not be typechecked because its the python 2 part',
                )
            else:
                _check_types = check_types

            rules = self.create_binary(
                base_path,
                py_name,
                library,
                tests=tests,
                py_version=py_ver,
                py_flavor=py_flavor,
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
                check_types=_check_types,
                preload_deps=preload_deps,
                jemalloc_conf=jemalloc_conf,
                typing_options=check_types_options,
                helper_deps=helper_deps,
                visibility=visibility,
                analyze_imports=analyze_imports,
            )
            if self.is_test():
                py_tests.append(rules[0])
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
            # We are propogating tests from sub targets to this target
            gen_tests = set()
            for r in py_tests:
                gen_tests.add(r.target_name)
                if 'tests' in r.attributes:
                    gen_tests.update(r.attributes['tests'])
            attrs['tests'] = sorted(list(gen_tests))
            # With this we are telling buck we depend on the test targets
            cmds = []
            for test in py_tests:
                cmds.append('echo $(location {})'.format(test.target_name))
            attrs['cmd'] = ' && '.join(cmds)
            yield Rule('genrule', attrs)

    def create_analyze_imports(
        self,
        base_path,
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
        generate_imports_deps = deps[:]
        if ':generate_par_imports' not in generate_imports_deps:
            generate_imports_deps.append('//libfb/py:generate_par_imports')

        if ':parutil' not in generate_imports_deps:
            generate_imports_deps.append('//libfb/py:parutil')

        import_attrs = collections.OrderedDict((
            ('name', name + '-generate-imports'),
            ('main_module', 'libfb.py.generate_par_imports'),
            ('cxx_platform', platform_utils.get_buck_platform_for_base_path(base_path)),
            ('platform', python_platform),
            ('deps', generate_imports_deps),
            ('platform_deps', platform_deps),
            ('preload_deps', preload_deps),
            # TODO(ambv): labels here shouldn't be hard-coded.
            ('labels', ['buck', 'python']),
            ('version_universe',
             self.get_version_universe(self.get_py3_version(platform))),
        ))
        if visibility is not None:
            import_attrs['visibility'] = visibility
        generate_par = Rule('python_binary', import_attrs)
        yield generate_par

        rule_attrs = collections.OrderedDict((
            ('name', "{}-gen-rule".format(name)),
            ('srcs', ["//" + base_path + ":" + name + "-generate-imports"]),
            ('out', '{}-imports_file.py'.format(name)),
            ('cmd', '$(exe {}) >"$OUT"'.format(generate_par.target_name)),
        ))
        gen_rule = Rule('genrule', rule_attrs)
        yield gen_rule

        lib_attrs = collections.OrderedDict((
            ('name', name + '-analyze-lib'),
            ('srcs', {'imports_file.py': '//' + base_path + ':' + rule_attrs['name']}),
            ('base_module', ''),
            ('deps', [gen_rule.target_name])
        ))
        lib_rule = Rule('python_library', lib_attrs)
        yield lib_rule

        analyze_deps = deps[:]
        analyze_deps.append('//' + base_path + ':' + lib_attrs['name'])

        if ':analyze_par_imports' not in analyze_deps:
            analyze_deps.append('//libfb/py:analyze_par_imports')

        analyze_attrs = collections.OrderedDict((
            ('name', name + '-analyze-imports'),
            ('main_module', 'libfb.py.analyze_par_imports'),
            ('cxx_platform', platform_utils.get_buck_platform_for_base_path(base_path)),
            ('platform', python_platform),
            ('deps', analyze_deps),
            ('platform_deps', platform_deps),
            ('preload_deps', preload_deps),
            # TODO(ambv): labels here shouldn't be hard-coded.
            ('labels', ['buck', 'python']),
            ('version_universe',
             self.get_version_universe(self.get_py3_version(platform))),
        ))

        if visibility is not None:
            analyze_attrs['visibility'] = visibility
        yield Rule('python_binary', analyze_attrs)

    def create_typecheck(
        self,
        base_path,
        name,
        main_module,
        platform,
        python_platform,
        python_version,
        library,
        deps,
        platform_deps,
        preload_deps,
        typing_options,
        visibility,
        emails,
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
            ('cxx_platform', platform_utils.get_buck_platform_for_base_path(base_path)),
            ('platform', python_platform),
            ('deps', typecheck_deps),
            ('platform_deps', platform_deps),
            ('preload_deps', preload_deps),
            ('package_style', 'inplace'),
            # TODO(ambv): labels here shouldn't be hard-coded.
            ('labels', ['buck', 'python']),
            ('version_universe', self.get_version_universe(python_version)),
            ('contacts', emails),
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

        if main_module not in {'__fb_test_main__', 'libfb.py.testslide.unittest'}:
            # Tests are properly enumerated from passed sources (see above).
            # For binary targets, we need this subtle hack to let
            # python_typecheck know where to start type checking the program.
            attrs['env'] = {"PYTHON_TYPECHECK_ENTRY_POINT": main_module}

        typing_options_list = [
            option.strip() for option in typing_options.split(',')
        ] if typing_options else []
        use_pyre = typing_options and 'pyre' in typing_options_list

        if use_pyre:
            typing_options_list.remove('pyre')
            typing_options = ','.join(typing_options_list)
            if 'env' in attrs.keys():
                attrs['env']["PYRE_ENABLED"] = "1"
            else:
                attrs['env'] = {"PYRE_ENABLED": "1"}

        if typing_config:
            conf = collections.OrderedDict()
            if visibility is not None:
                conf['visibility'] = visibility
            conf['out'] = os.curdir
            cmd = '$(exe {}) gather '.format(typing_config)
            if use_pyre:
                conf['name'] = name + "-typing=pyre.json"
                conf['out'] = 'pyre.json'
                cmd += '--pyre=True '
            else:
                conf['name'] = name + '-typing=mypy.ini'
                conf['out'] = 'mypy.ini'
            if typing_options:
                cmd += '--options="{}" '.format(typing_options)
            cmd += '$(location {}-typing) $OUT'.format(library.target_name)
            conf['cmd'] = cmd
            gen_rule = Rule('genrule', conf)
            yield gen_rule

            conf = collections.OrderedDict()
            if use_pyre:
                conf['name'] = name + '-pyre_json'
            else:
                conf['name'] = name + '-mypy_ini'
            if visibility is not None:
                conf['visibility'] = visibility
            conf['base_module'] = ''
            conf['srcs'] = [gen_rule.target_name]
            configuration = Rule('python_library', conf)
            yield configuration
            typecheck_deps.append(configuration.target_name)

        yield Rule('python_test', attrs)

    def create_monkeytype_rules(
        self,
        rule_type,
        attributes,
        library,
    ):
        rules = []
        name = attributes['name']
        visibility = attributes.get('visibility', None)
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
