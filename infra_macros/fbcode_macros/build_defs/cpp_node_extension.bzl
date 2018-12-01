load("@bazel_skylib//lib:paths.bzl", "paths")
load("@fbcode_macros//build_defs:cpp_common.bzl", "cpp_common")
load("@fbcode_macros//build_defs:target_utils.bzl", "target_utils")
load("@fbcode_macros//build_defs:visibility.bzl", "get_visibility")
load("@fbsource//tools/build_defs:fb_native_wrapper.bzl", "fb_native")

_NODE_SPECIFIC_DEPS = [
    target_utils.ThirdPartyRuleTarget("node", "node-headers"),
]

def cpp_node_extension(
        name,
        arch_compiler_flags = None,  # {}
        arch_preprocessor_flags = None,  # {}
        auto_headers = None,
        compiler_flags = (),
        compiler_specific_flags = None,  # {}
        deps = (),
        external_deps = (),
        global_symbols = (),
        header_namespace = None,
        headers = None,
        known_warnings = (),  # True or list
        lex_args = (),
        linker_flags = (),
        modules = None,
        nodefaultlibs = False,
        nvcc_flags = (),
        precompiled_header = cpp_common.ABSENT_PARAM,
        preprocessor_flags = (),
        py3_sensitive_deps = (),
        shared_system_deps = None,
        srcs = (),
        supports_coverage = None,
        system_include_paths = None,
        visibility = None,
        yacc_args = (),
        additional_coverage_targets = (),
        autodeps_keep = None,  # Ignore; used only by autodeps tooling.
        tags = ()):
    visibility = get_visibility(visibility, name)

    # Delegate to the main conversion function, making sure that we build
    # the extension into a statically linked monolithic DSO.
    attrs = cpp_common.convert_cpp(
        name = name + "-extension",
        cpp_rule_type = "cpp_node_extension",
        buck_rule_type = "cxx_binary",
        is_library = False,
        is_buck_binary = True,
        is_test = False,
        is_deployable = False,
        dlopen_enabled = True,
        visibility = visibility,
        overridden_link_style = "static_pic",
        rule_specific_deps = _NODE_SPECIFIC_DEPS,
        arch_compiler_flags = arch_compiler_flags or {},
        arch_preprocessor_flags = arch_preprocessor_flags or {},
        auto_headers = auto_headers,
        compiler_flags = compiler_flags,
        compiler_specific_flags = compiler_specific_flags or {},
        deps = deps,
        external_deps = external_deps,
        global_symbols = global_symbols,
        header_namespace = header_namespace,
        headers = headers,
        known_warnings = known_warnings,  # True or list
        lex_args = lex_args,
        linker_flags = linker_flags,
        modules = modules,
        nodefaultlibs = nodefaultlibs,
        nvcc_flags = nvcc_flags,
        precompiled_header = precompiled_header,
        preprocessor_flags = preprocessor_flags,
        py3_sensitive_deps = py3_sensitive_deps,
        shared_system_deps = shared_system_deps,
        srcs = srcs,
        supports_coverage = supports_coverage,
        system_include_paths = system_include_paths,
        yacc_args = yacc_args,
        additional_coverage_targets = additional_coverage_targets,
        autodeps_keep = autodeps_keep,  # Ignore; used only by autodeps tooling.
        tags = tags,
    )
    fb_native.cxx_binary(**attrs)

    # This is a bit weird, but `prebuilt_cxx_library` rules can only
    # accepted generated libraries that reside in a directory.  So use
    # a genrule to copy the library into a lib dir using it's soname.
    dest = paths.join("node_modules", name, name + ".node")
    fb_native.genrule(
        name = name,
        visibility = visibility,
        out = name + "-modules",
        cmd = "mkdir -p $OUT/{} && cp $(location :{}-extension) $OUT/{}".format(
            paths.dirname(dest),
            name,
            dest,
        ),
    )
