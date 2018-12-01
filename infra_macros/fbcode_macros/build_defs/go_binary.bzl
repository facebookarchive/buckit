load("@fbcode_macros//build_defs/lib:go_common.bzl", "go_common")
load("@fbsource//tools/build_defs:fb_native_wrapper.bzl", "fb_native")

def go_binary(
        name,
        srcs = None,
        gen_srcs = None,
        deps = None,
        go_external_deps = None,
        compiler_flags = None,
        linker_flags = None,
        external_linker_flags = None,
        resources = None,
        cgo = False,
        link_style = None,
        visibility = None,
        licenses = None):
    """
    A simple wrapper around buck's built in go_binary rule

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
        compiler_flags: Additional flags to pass to the go compiler. See https://buckbuild.com/rule/go_binary.html#compiler_flags
        linker_flags: The linker flags to use with go link. See https://buckbuild.com/rule/go_binary.html#linker_flags
        external_linker_flags: See https://buckbuild.com/rule/go_binary.html#external_linker_flags
        resources: See https://buckbuild.com/rule/go_binary.html#resources
        cgo: If true this rule has native code, and should depend on things like
             sanitizer/allocator code
        link_style: See https://buckbuild.com/rule/go_binary.html#link_style
        visibility: The visiibility for the rule. This may be modified by global settings.
        licenses: See https://buckbuild.com/rule/go_binary.html#licenses
    """

    rule_attributes = go_common.convert_go(
        name = name,
        is_binary = True,
        is_test = False,
        is_cgo = False,
        srcs = srcs,
        gen_srcs = gen_srcs,
        deps = deps,
        go_external_deps = go_external_deps,
        compiler_flags = compiler_flags,
        linker_flags = linker_flags,
        external_linker_flags = external_linker_flags,
        resources = resources,
        cgo = cgo,
        link_style = link_style,
        visibility = visibility,
        licenses = licenses,
    )
    fb_native.go_binary(**rule_attributes)
