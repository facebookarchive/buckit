load("@bazel_skylib//lib:collections.bzl", "collections")
load("@fbcode_macros//build_defs/lib:python_common.bzl", "python_common")
load("@fbcode_macros//build_defs/lib:visibility.bzl", "get_visibility")
load("@fbsource//tools/build_defs:fb_native_wrapper.bzl", "fb_native")

def python_unittest(
        name,
        py_version = None,
        py_flavor = "",
        base_module = None,
        main_module = None,
        strip_libpar = True,
        srcs = (),
        versioned_srcs = (),
        tags = (),
        gen_srcs = (),
        deps = (),
        tests = (),
        par_style = None,
        emails = None,
        external_deps = (),
        needed_coverage = None,
        argcomplete = None,
        strict_tabs = None,
        compile = None,
        args = None,
        env = None,
        python = None,
        allocator = None,
        check_types = False,
        preload_deps = (),
        visibility = None,
        resources = (),
        jemalloc_conf = None,
        typing = False,
        typing_options = "",
        check_types_options = "",
        runtime_deps = (),
        cpp_deps = (),  # ctypes targets
        helper_deps = False,
        analyze_imports = False,
        additional_coverage_targets = (),
        version_subdirs = None):
    visibility = get_visibility(visibility, name)

    all_attributes = python_common.convert_binary(
        is_test = True,
        fbconfig_rule_type = "python_unittest",
        buck_rule_type = "python_test",
        base_path = native.package_name(),
        name = name,
        py_version = py_version,
        py_flavor = py_flavor,
        base_module = base_module,
        main_module = main_module,
        strip_libpar = strip_libpar,
        srcs = srcs,
        versioned_srcs = versioned_srcs,
        tags = tags,
        gen_srcs = gen_srcs,
        deps = deps,
        tests = tests,
        par_style = par_style,
        emails = emails,
        external_deps = external_deps,
        needed_coverage = needed_coverage,
        argcomplete = argcomplete,
        strict_tabs = strict_tabs,
        compile = compile,
        args = args,
        env = env,
        python = python,
        allocator = allocator,
        check_types = check_types,
        preload_deps = preload_deps,
        visibility = visibility,
        resources = resources,
        jemalloc_conf = jemalloc_conf,
        typing = typing,
        typing_options = typing_options,
        check_types_options = check_types_options,
        runtime_deps = runtime_deps,
        cpp_deps = cpp_deps,
        helper_deps = helper_deps,
        analyze_imports = analyze_imports,
        additional_coverage_targets = additional_coverage_targets,
        version_subdirs = version_subdirs,
    )

    py_tests = []
    for attributes in all_attributes:
        fb_native.python_test(**attributes)
        py_tests.append(
            (":" + attributes["name"], attributes.get("tests")),
        )

    # TODO: This should probably just be test_suite? This rule really doesn't
    #       make sense....
    # Create a genrule to wrap all the tests for easy running if a test was created
    # for multiple python versions (they'll have different names)
    if len(py_tests) > 1:
        # We are propogating tests from sub targets to this target
        gen_tests = []
        for test_target, tests_attribute in py_tests:
            gen_tests.append(test_target)
            if tests_attribute:
                gen_tests.extend(tests_attribute)
        gen_tests = collections.uniq(gen_tests)

        cmd = " && ".join([
            "echo $(location {})".format(test_target)
            for test_target in gen_tests
        ] + ["touch $OUT"])

        fb_native.genrule(
            name = name,
            visibility = visibility,
            out = "unused",
            tests = gen_tests,
            cmd = cmd,
        )
