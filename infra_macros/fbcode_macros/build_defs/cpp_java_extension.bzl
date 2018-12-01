load("@fbcode_macros//build_defs/lib:cpp_common.bzl", "cpp_common")
load("@fbcode_macros//build_defs/lib:visibility.bzl", "get_visibility")
load("@fbcode_macros//build_defs:config.bzl", "config")
load("@fbcode_macros//build_defs:platform_utils.bzl", "platform_utils")
load("@fbsource//tools/build_defs:fb_native_wrapper.bzl", "fb_native")

def cpp_java_extension(
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
        tags = (),
        lib_name = None):
    base_path = native.package_name()
    visibility = get_visibility(visibility, name)

    # If we're not building in `dev` mode, then build extensions as
    # monolithic statically linked C/C++ shared libs.  We do this by
    # overriding some parameters to generate the extension as a dlopen-
    # enabled C/C++ binary, which also requires us generating the rule
    # under a different name, so we can use the user-facing name to
    # wrap the C/C++ binary in a prebuilt C/C++ library.
    dlopen_enabled = None

    if not config.get_build_mode().startswith("dev"):
        real_name = name
        name = name + "-extension"
        soname = "lib{}.so".format(
            lib_name or paths.join(base_path, name).replace("/", "_"),
        )
        dlopen_enabled = {"soname": soname}
        lib_name = None

        # If we're building the monolithic extension, then setup additional
        # rules to wrap the extension in a prebuilt C/C++ library consumable
        # by Java dependents.

        # Wrap the extension in a `prebuilt_cxx_library` rule
        # using the user-facing name.  This is what Java library
        # dependents will depend on.
        platform = platform_utils.get_buck_platform_for_base_path(base_path)
        fb_native.prebuilt_cxx_library(
            name = real_name,
            visibility = visibility,
            soname = soname,
            shared_lib = ":{}#{}".format(name, platform),
        )

    # Delegate to the main conversion function, using potentially altered
    # parameters from above.
    if config.get_build_mode().startswith("dev"):
        buck_rule_type = "cxx_library"
        is_buck_binary = False
        native_rule = fb_native.cxx_library
    else:
        buck_rule_type = "cxx_binary"
        is_buck_binary = True
        native_rule = fb_native.cxx_binary

    attrs = cpp_common.convert_cpp(
        name,
        cpp_rule_type = "cpp_java_extension",
        buck_rule_type = buck_rule_type,
        is_library = False,
        is_buck_binary = is_buck_binary,
        is_test = False,
        is_deployable = False,
        dlopen_enabled = dlopen_enabled,
        lib_name = lib_name,
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
        visibility = visibility,
        yacc_args = yacc_args,
        additional_coverage_targets = additional_coverage_targets,
        autodeps_keep = autodeps_keep,  # Ignore; used only by autodeps tooling.
        tags = tags,
    )
    native_rule(**attrs)
