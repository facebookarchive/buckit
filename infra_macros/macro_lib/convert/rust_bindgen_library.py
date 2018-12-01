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

import pipes

with allow_unsafe_import():
    import os.path

macro_root = read_config('fbcode', 'macro_lib', '//macro_lib')
include_defs("{}/convert/rust.py".format(macro_root), "rust")
include_defs("{}/rule.py".format(macro_root))
load("@fbcode_macros//build_defs:platform_utils.bzl", "platform_utils")
load("@fbsource//tools/build_defs:fb_native_wrapper.bzl", "fb_native")
load("@fbcode_macros//build_defs/lib:rust_common.bzl", "rust_common")
load("@fbcode_macros//build_defs/lib:merge_tree.bzl", "merge_tree")
load("@fbcode_macros//build_defs/lib:target_utils.bzl", "target_utils")
load("@fbcode_macros//build_defs/lib:src_and_dep_helpers.bzl", "src_and_dep_helpers")


FLAGFILTER = '''\
# Extract just -D, -I and -isystem options
flagfilter() {{
    while [ $# -gt 0 ]; do
        local f=$1
        shift
        case $f in
            -I?*|-D?*) echo "$f";;
            -I|-D) echo "$f$1"; shift;;
            -isystem) echo "$f $1"; shift;;
            -std=*) echo "$f";;
            -nostdinc) echo "$f";;
            -fno-canonical-system-headers) ;; # skip unknown
            -f*) echo "$f";;
        esac
    done
}}
'''

PPFLAGS = '''\

declare -a ppflags
ppflags=($(cxxppflags{deps}))

'''

CLANG_ARGS = '''\
    \$(flagfilter {base_clang_flags}) \
    {clang_flags} \
    --gcc-toolchain=third-party-buck/{platform}/tools/gcc/ \
    -x c++ \
    \$(flagfilter "${{ppflags[@]}}") \
    -I$(location {includes}) \
'''

PREPROC_TMPL = \
    FLAGFILTER + \
    PPFLAGS + \
    '''\
(
cd {fbcode} && \
FBPLATFORM={platform} \
$(cxx) \
    -o $OUT \
    -E \
    $SRCS \
''' + CLANG_ARGS + '''\
)
'''

BINDGEN_TMPL = \
    FLAGFILTER + \
    PPFLAGS + \
    '''\
(
TMPFILE=$TMP/bindgen.$$.stderr
trap "rm -f $TMPFILE" EXIT
cd {fbcode} && \
FBPLATFORM={platform} \
$(exe {bindgen}) \
    --output $OUT \
    {bindgen_flags} \
    {blacklist} \
    {opaque} \
    {wl_funcs} \
    {wl_types} \
    {wl_vars} \
    {generate} \
    $SRCS \
    -- \
''' + CLANG_ARGS + '''\
2> $TMPFILE || (e=$?; cat $TMPFILE 1>&2; exit $e)
)
'''


class RustBindgenLibraryConverter(rust.RustConverter):
    def __init__(self, context):
        super(RustBindgenLibraryConverter, self).\
            __init__(context, 'rust_library')

    def get_fbconfig_rule_type(self):
        return 'rust_bindgen_library'

    def get_buck_rule_type(self):
        return 'rust_library'

    def get_exported_include_tree(self, name):
        return name + '-bindgen-includes'

    def get_allowed_args(self):
        return set([
            'name',
            'srcs',
            'cpp_deps',
            'deps',
            'external_deps',
            'src_includes',
            'header',
            'generate',
            'cxx_namespaces',
            'opaque_types',
            'blacklist_types',
            'whitelist_funcs',
            'whitelist_types',
            'whitelist_vars',
            'bindgen_flags',
            'clang_flags',
            'rustc_flags',
            'link_style',
            'linker_flags',
        ])

    def generate_bindgen_rule(
        self,
        base_path,
        name,
        header,
        cpp_deps,
        cxx_namespaces=False,
        blacklist_types=(),
        opaque_types=(),
        whitelist_funcs=(),
        whitelist_types=(),
        whitelist_vars=(),
        bindgen_flags=None,
        clang_flags=(),
        generate=(),
        src_includes=None,
        **kwargs
    ):
        src = 'lib.rs'
        gen_name = name + '-bindgen'

        # TODO(T27678070): The Rust bindgen rule should inherit it's platform
        # from top-level rules, not look it up via a PLATFORM file.  We should
        # cleanup all references to this in the code below.
        platform = platform_utils.get_platform_for_base_path(base_path)

        if generate:
            generate = '--generate ' + ','.join(generate)
        else:
            generate = ''

        base_bindgen_flags = [
            '--raw-line=#![allow(non_snake_case)]',
            '--raw-line=#![allow(non_camel_case_types)]',
            '--raw-line=#![allow(non_upper_case_globals)]',

            '--raw-line=#[link(name = "stdc++")] extern {}',
        ]

        # Include extra sources the user wants.
        # We need to make the include path absolute, because otherwise rustc
        # will interpret as relative to the source that's including it, which
        # is in the cxx_genrule build dir.
        for s in (src_includes or []):
            base_bindgen_flags.append(
                '--raw-line=include!(concat!(env!("RUSTC_BUILD_CONTAINER"), "{}"));'
                .format(os.path.join(base_path, s))
            )

        if cxx_namespaces:
            base_bindgen_flags.append('--enable-cxx-namespaces')
        bindgen_flags = base_bindgen_flags + (bindgen_flags or [])

        # rust-bindgen is clang-based, so we can't directly use the cxxppflags
        # in a gcc build. This means we need to fetch the appropriate flags
        # here, and also filter out inappropriate ones we get from the
        # $(cxxppflags) macro in the cxxgenrule.
        buck_platform = platform_utils.get_buck_platform_for_base_path(base_path)
        base_clang_flags = '%s %s' % (
            self._context.buck_ops.read_config('rust#' + buck_platform, 'bindgen_cxxppflags'),
            self._context.buck_ops.read_config('rust#' + buck_platform, 'bindgen_cxxflags'))
        base_clang_flags = base_clang_flags.split(' ')

        def formatter(fmt):
            return fmt.format(
                fbcode=os.path.join('$GEN_DIR', self.get_fbcode_dir_from_gen_dir()),
                bindgen=self.get_tool_target(
                    target_utils.ThirdPartyRuleTarget('rust-bindgen', 'bin/bindgen'),
                    platform),
                bindgen_flags=' '.join(map(pipes.quote, bindgen_flags)),
                base_clang_flags=' '.join(map(pipes.quote, base_clang_flags)),
                clang_flags=' '.join(map(pipes.quote, clang_flags)),
                blacklist=' '.join(['--blacklist-type ' + pipes.quote(ty)
                                    for ty in blacklist_types]),
                opaque=' '.join(['--opaque-type ' + pipes.quote(ty)
                                    for ty in opaque_types]),
                wl_types=' '.join(['--whitelist-type ' + pipes.quote(ty)
                                    for ty in whitelist_types]),
                wl_funcs=' '.join(['--whitelist-function ' + pipes.quote(fn)
                                    for fn in whitelist_funcs]),
                wl_vars=' '.join(['--whitelist-var ' + pipes.quote(v)
                                    for v in whitelist_vars]),
                generate=generate,
                deps=''.join(' ' + d for d in cpp_deps),
                includes=self.get_exported_include_tree(':' + name),
                platform=platform,
            )

        # Actual bindgen rule
        fb_native.cxx_genrule(
            name = gen_name,
            out = os.path.join(os.curdir, src),
            srcs = [header],
            visibility = [],
            bash = formatter(BINDGEN_TMPL),
        )

        # Rule to generate pre-processed output, to make debugging
        # bindgen problems easier.

        fb_native.cxx_genrule(
            name = name + '-preproc',
            out = os.path.join(os.curdir, name + '.i'),
            srcs = [header],
            bash = formatter(PREPROC_TMPL),
        )

        return ':{}'.format(gen_name)

    def convert(
            self,
            base_path,
            name,
            header,
            cpp_deps,
            deps=(),
            src_includes=None,
            visibility=None,
            **kwargs):
        rules = []

        # Setup the exported include tree to dependents.
        merge_tree(
            base_path,
            self.get_exported_include_tree(name),
            [header],
            [],
            visibility)

        genrule = self.generate_bindgen_rule(
            base_path,
            name,
            header,
            [src_and_dep_helpers.convert_build_target(base_path, d) for d in cpp_deps],
            src_includes=src_includes,
            **kwargs)

        # Use normal converter to make build+test rules
        rust_lib_attrs = rust_common.convert_rust(
            name,
            fbconfig_rule_type=self.get_fbconfig_rule_type(),
            srcs=[genrule] + (src_includes or []),
            deps=list(cpp_deps) + list(deps),
            crate_root=genrule,
            visibility=visibility,
            **kwargs)
        fb_native.rust_library(**rust_lib_attrs)

        return rules
