load("@fbsource//tools/build_defs:fb_native_wrapper.bzl", "fb_native")
load("@fbcode_macros//build_defs:cpp_common.bzl", "cpp_common")
load("@fbcode_macros//build_defs:go_common.bzl", "go_common")

def cgo_library(
        name,
        srcs = None,
        go_srcs = None,
        gen_srcs = None,
        deps = None,
        exported_deps = None,
        go_external_deps = None,
        package_name = None,
        tests = None,
        go_compiler_flags = None,
        linker_flags = None,
        headers = None,
        preprocessor_flags = None,
        cgo_compiler_flags = None,
        linker_extra_outputs = None,
        link_style = None,
        visibility = None,
        licenses = None):
    """
    Args:
        name: The name of the rule
        srcs: A list of source files/targets
        go_srcs: See https://buckbuild.com/rule/cgo_library.html#go_srcs
        gen_srcs: Generated sources. These should be targets that can have a filename
                  inferred.
        deps: Dependencies for the rule
        exported_deps: Dependencies for the rule that should be re-exported
        go_external_deps: A list of dependencies on third party projects. These should
                          be strings that operate like includes in go. e.g.
                          "github.com/pkg/errors"
        package_name: The go package name. See https://buckbuild.com/rule/go_library.html#package_name
        tests: Tests associated with this library. See https://buckbuild.com/rule/go_library.html#tests
        go_compiler_flags: Additional flags to pass to the go compiler. See https://buckbuild.com/rule/go_library.html#go_compiler_flags
        linker_flags: The linker flags to use with go link. See https://buckbuild.com/rule/go_binary.html#linker_flags
        headers: See https://buckbuild.com/rule/cgo_library.html#headers
        preprocessor_flags: See https://buckbuild.com/rule/cgo_library.html#preprocessor_flags
        cgo_compiler_flags: See https://buckbuild.com/rule/cgo_library.html#cgo_compiler_flags
        linker_extra_outputs: See https://buckbuild.com/rule/cgo_library.html#preprocessor_flags
        link_style: See https://buckbuild.com/rule/go_binary.html#link_style
        visibility: The visiibility for the rule. This may be modified by global settings.
        licenses: See https://buckbuild.com/rule/go_binary.html#licenses


    """
    if link_style == None:
        link_style = cpp_common.get_link_style()

    rule_attributes = go_common.convert_go(
        name = name,
        is_binary = False,
        is_test = False,
        is_cgo = True,
        srcs = srcs,
        gen_srcs = gen_srcs,
        deps = deps,
        exported_deps = exported_deps,
        go_external_deps = go_external_deps,
        package_name = package_name,
        tests = tests,
        linker_flags = linker_flags,
        link_style = link_style,
        visibility = visibility,
        licenses = licenses,
    )
    fb_native.cgo_library(
        linker_extra_outputs = linker_extra_outputs,
        go_compiler_flags = go_compiler_flags,
        cgo_compiler_flags = cgo_compiler_flags,
        preprocessor_flags = preprocessor_flags,
        headers = headers,
        go_srcs = go_srcs,
        **rule_attributes
    )
