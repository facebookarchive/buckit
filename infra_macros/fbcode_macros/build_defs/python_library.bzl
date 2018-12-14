load("@fbcode_macros//build_defs/lib:python_common.bzl", "python_common")
load("@fbcode_macros//build_defs/lib:visibility.bzl", "get_visibility")
load("@fbsource//tools/build_defs:fb_native_wrapper.bzl", "fb_native")

def python_library(
        name,
        base_module = None,
        cpp_deps = (),  # ctypes targets
        deps = (),
        external_deps = (),
        gen_srcs = (),
        py_flavor = "",
        resources = (),
        runtime_deps = (),
        srcs = (),
        tags = (),
        tests = (),
        typing = False,
        typing_options = "",
        version_subdirs = None,
        versioned_srcs = (),
        visibility = None,
        additional_coverage_targets = None,  # Deprecated. This property should only be set on binaries and tests
        allocator = None,  # Deprecated. This property should only be set on binaries and tests
        analyze_imports = None,  # Deprecated. This property should only be set on binaries and tests
        argcomplete = None,  # Deprecated. This property should only be set on binaries and tests
        args = None,  # Deprecated. This property should only be set on binaries and tests
        check_types = None,  # Deprecated. This property should only be set on binaries and tests
        check_types_options = None,  # Deprecated. This property should only be set on binaries and tests
        compile = None,  # Deprecated. This property should only be set on binaries and tests
        emails = None,  # Deprecated. This property should only be set on binaries and tests
        env = None,  # Deprecated. This property should only be set on binaries and tests
        helper_deps = None,  # Deprecated. This property should only be set on binaries and tests
        jemalloc_conf = None,  # Deprecated. This property should only be set on binaries and tests
        lib_dir = None,  # Deprecated. This property should only be set on binaries and tests
        main_module = None,  # Deprecated. This property should only be set on binaries and tests
        needed_coverage = None,  # Deprecated. This property should only be set on binaries and tests
        par_style = None,  # Deprecated. This property should only be set on binaries and tests
        preload_deps = None,  # Deprecated. This property should only be set on binaries and tests
        python = None,  # Deprecated. This property should only be set on binaries and tests
        py_version = None,  # Deprecated. This property should only be set on binaries and tests
        strict_tabs = None,  # Deprecated. This property should only be set on binaries and tests
        strip_libpar = None):  # Deprecated. This property should only be set on binaries and tests
    """
    Wrapper for python_library
    """

    visibility = get_visibility(visibility, name)
    library_attributes = python_common.convert_library(
        is_test = False,
        is_library = True,
        base_path = native.package_name(),
        name = name,
        base_module = base_module,
        check_types = False,
        cpp_deps = cpp_deps,
        deps = deps,
        external_deps = external_deps,
        gen_srcs = gen_srcs,
        py_flavor = py_flavor,
        resources = resources,
        runtime_deps = runtime_deps,
        srcs = srcs,
        tags = tags,
        tests = tests,
        typing = typing,
        typing_options = typing_options,
        version_subdirs = version_subdirs,
        versioned_srcs = versioned_srcs,
        visibility = visibility,
    )

    fb_native.python_library(**library_attributes)

    # Shut the linter up
    _ignore = (
        additional_coverage_targets,
        allocator,
        analyze_imports,
        argcomplete,
        args,
        check_types,
        check_types_options,
        compile,
        emails,
        env,
        helper_deps,
        jemalloc_conf,
        lib_dir,
        main_module,
        needed_coverage,
        par_style,
        preload_deps,
        python,
        py_version,
        strict_tabs,
        strip_libpar,
    )
