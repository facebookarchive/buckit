load("@fbcode_macros//build_defs:go_common.bzl", "go_common")
load("@fbsource//tools/build_defs:fb_native_wrapper.bzl", "fb_native")

def go_library(
        name,
        srcs = None,
        gen_srcs = None,
        deps = None,
        exported_deps = None,
        go_external_deps = None,
        package_name = None,
        tests = None,
        compiler_flags = None,
        resources = None,
        visibility = None,
        licenses = None):
    """
    A simple wrapper around buck's native go_library

    Args:
        name: The name of the rule
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
        resources: See https://buckbuild.com/rule/go_library.html#resources
        visibility: The visiibility for the rule. This may be modified by global settings.
        licenses: See https://buckbuild.com/rule/go_library.html#licenses

    """
    rule_attributes = go_common.convert_go(
        name = name,
        is_binary = False,
        is_test = False,
        is_cgo = False,
        srcs = srcs,
        gen_srcs = gen_srcs,
        deps = deps,
        exported_deps = exported_deps,
        go_external_deps = go_external_deps,
        package_name = package_name,
        tests = tests,
        compiler_flags = compiler_flags,
        resources = resources,
        visibility = visibility,
        licenses = licenses,
    )
    fb_native.go_library(**rule_attributes)
