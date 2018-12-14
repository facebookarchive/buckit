load("@bazel_skylib//lib:paths.bzl", "paths")
load("@bazel_skylib//lib:types.bzl", "types")
load("@fbcode_macros//build_defs/lib:cpp_common.bzl", "cpp_common")
load("@fbcode_macros//build_defs/lib:src_and_dep_helpers.bzl", "src_and_dep_helpers")
load("@fbcode_macros//build_defs/lib:visibility.bzl", "get_visibility")
load("@fbcode_macros//build_defs:platform_utils.bzl", "platform_utils")
load("@fbsource//tools/build_defs:fb_native_wrapper.bzl", "fb_native")

_VENDOR_PATH = "third-party-source/go"

def _convert_go(
        name,
        is_binary,
        is_test,
        is_cgo,
        srcs = None,
        gen_srcs = None,
        deps = None,
        exported_deps = None,
        go_external_deps = None,
        package_name = None,
        tests = None,
        compiler_flags = None,
        linker_flags = None,
        external_linker_flags = None,
        resources = None,
        cgo = False,
        link_style = None,
        visibility = None,
        licenses = None):
    """
    Common entry point for generating go rules.

    Args:
        name: The name of the rule
        is_binary: Whether the rule will be a binary rule (e.g. native.go_binary)
        is_test: Whether the rule is a test rule (e.g. native.go_test)
        is_cgo: Whether the rule is a cgo_library
        srcs: A list of source files/targets
        gen_srcs: Generated sources. These should be targets that can have a filename
                  inferred.
        deps: Dependencies for the rule
        exported_deps: Dependencies for the rule that should be re-exported
        go_external_deps: A list of dependencies on third party projects. These should
                          be strings that operate like includes in go. e.g.
                          "github.com/pkg/errors"
        package_name: The go package name. See https://buckbuild.com/rule/go_library.html#package_name
        tests: Tests associated with this library. See https://buckbuild.com/rule/go_library.html#tests
        compiler_flags: Additional flags to pass to the go compiler. See https://buckbuild.com/rule/go_library.html#compiler_flags
        linker_flags: The linker flags to use with go link. See https://buckbuild.com/rule/go_binary.html#linker_flags
        external_linker_flags: See https://buckbuild.com/rule/go_binary.html#external_linker_flags
        resources: See https://buckbuild.com/rule/go_binary.html#resources
        cgo: If true and is_test/is_binary is true, this rule has native code, and
             should depend on things like sanitizer/allocator code

        link_style: See https://buckbuild.com/rule/go_binary.html#link_style
        visibility: The visiibility for the rule. This may be modified by global settings.
        licenses: See https://buckbuild.com/rule/go_binary.html#licenses

    Returns:
        Returns a dictionary of attributes suitable to feed into a buck native rule.
    """

    visibility = get_visibility(visibility, name)
    base_path = native.package_name()

    srcs = srcs or []
    gen_srcs = gen_srcs or []
    deps = deps or []
    go_external_deps = go_external_deps or []
    compiler_flags = compiler_flags or []
    linker_flags = linker_flags or []
    external_linker_flags = external_linker_flags or []
    resources = resources or []

    # cgo attributes

    attributes = {
        "name": name,
        "srcs": src_and_dep_helpers.convert_source_list(base_path, srcs + gen_srcs),
        "visibility": visibility,
    }
    if tests != None:
        attributes["tests"] = [
            src_and_dep_helpers.convert_build_target(base_path, test)
            for test in tests
        ]

    if package_name:
        attributes["package_name"] = package_name

    if resources:
        attributes["resources"] = resources

    if is_binary:
        attributes["platform"] = platform_utils.get_buck_platform_for_base_path(base_path)

    dependencies = []
    for target in deps:
        dependencies.append(src_and_dep_helpers.convert_build_target(base_path, target))

    if is_binary or (is_cgo and linker_flags):
        attributes["linker_flags"] = linker_flags

    if is_binary or (is_cgo and external_linker_flags):
        attributes["external_linker_flags"] = external_linker_flags

    if (is_binary or is_test) and cgo:
        if link_style == None:
            link_style = cpp_common.get_link_style()

        attributes["linker_flags"] = linker_flags
        d = cpp_common.get_binary_link_deps(
            base_path,
            name,
            attributes["linker_flags"] if "linker_flags" in attributes else [],
        )

        formatted_deps = src_and_dep_helpers.format_deps(
            d,
            fbcode_platform = platform_utils.get_platform_for_base_path(
                base_path,
            ),
        )

        fb_native.genrule(
            name = "gen-asan-lib",
            cmd = 'echo \'package asan\nimport "C"\' > $OUT',
            out = "asan.go",
        )

        fb_native.cgo_library(
            name = "cgo-asan-lib",
            package_name = "asan",
            srcs = [":gen-asan-lib"],
            deps = formatted_deps,
            link_style = link_style,
        )

        dependencies.append(":cgo-asan-lib")

    if is_test:
        # add benchmark rule to targets
        fb_native.command_alias(
            name = name + "-bench",
            exe = ":" + name,
            args = [
                "-test.bench=.",
                "-test.benchmem",
            ],
        )

    for ext_dep in go_external_deps:
        # We used to allow a version hash to be specified for a dep inside
        # a tuple.  If it exists just ignore it.
        if types.is_tuple(ext_dep):
            (ext_dep, _) = ext_dep
        dependencies.append("//{}/{}:{}".format(
            _VENDOR_PATH,
            ext_dep,
            paths.basename(ext_dep),
        ))
    attributes["deps"] = dependencies
    if compiler_flags:
        attributes["compiler_flags"] = compiler_flags

    if exported_deps:
        exported_deps = [
            src_and_dep_helpers.convert_build_target(base_path, d)
            for d in exported_deps
        ]
        attributes["exported_deps"] = exported_deps

    if link_style:
        attributes["link_style"] = link_style

    if is_test:
        attributes["coverage_mode"] = "set"

    if licenses:
        attributes["licenses"] = licenses

    return attributes

go_common = struct(
    convert_go = _convert_go,
)
