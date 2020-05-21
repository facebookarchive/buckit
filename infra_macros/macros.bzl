# Copyright 2016-present, Facebook, Inc.
# All rights reserved.
#
# This source code is licensed under the BSD-style license found in the
# LICENSE file in the root directory of this source tree. An additional grant
# of patent rights can be found in the PATENTS file in the same directory.

load("@bazel_skylib//lib:new_sets.bzl", "sets")
load("@fbcode//tools/build/buck/infra_macros/macro_lib:constants.bzl", "BUCK_RULES", "BUCK_TO_FBCODE_MAP", "FBCODE_RULES")
load("@fbcode_macros//build_defs:cgo_library.bzl", "cgo_library")
load("@fbcode_macros//build_defs:cpp_benchmark.bzl", "cpp_benchmark")
load("@fbcode_macros//build_defs:cpp_binary.bzl", "cpp_binary")
load("@fbcode_macros//build_defs:cpp_java_extension.bzl", "cpp_java_extension")
load("@fbcode_macros//build_defs:cpp_library.bzl", "cpp_library")
load("@fbcode_macros//build_defs:cpp_library_external.bzl", "cpp_library_external")
load("@fbcode_macros//build_defs:cpp_library_external_custom.bzl", "cpp_library_external_custom")
load("@fbcode_macros//build_defs:cpp_lua_extension.bzl", "cpp_lua_extension")
load("@fbcode_macros//build_defs:cpp_lua_main_module.bzl", "cpp_lua_main_module")
load("@fbcode_macros//build_defs:cpp_module_external.bzl", "cpp_module_external")
load("@fbcode_macros//build_defs:cpp_node_extension.bzl", "cpp_node_extension")
load("@fbcode_macros//build_defs:cpp_precompiled_header.bzl", "cpp_precompiled_header")
load("@fbcode_macros//build_defs:cpp_python_extension.bzl", "cpp_python_extension")
load("@fbcode_macros//build_defs:cpp_unittest.bzl", "cpp_unittest")
load("@fbcode_macros//build_defs:custom_rule.bzl", "custom_rule")
load("@fbcode_macros//build_defs:cython_library.bzl", "cython_library")
load("@fbcode_macros//build_defs:d_binary.bzl", "d_binary")
load("@fbcode_macros//build_defs:d_library.bzl", "d_library")
load("@fbcode_macros//build_defs:d_library_external.bzl", "d_library_external")
load("@fbcode_macros//build_defs:discard.bzl", "discard")
load("@fbcode_macros//build_defs:go_binary.bzl", "go_binary")
load("@fbcode_macros//build_defs:go_bindgen_library.bzl", "go_bindgen_library")
load("@fbcode_macros//build_defs:go_library.bzl", "go_library")
load("@fbcode_macros//build_defs:go_unittest.bzl", "go_unittest")
load("@fbcode_macros//build_defs:haskell_binary.bzl", "haskell_binary")
load("@fbcode_macros//build_defs:haskell_external_library.bzl", "haskell_external_library")
load("@fbcode_macros//build_defs:haskell_ghci.bzl", "haskell_ghci")
load("@fbcode_macros//build_defs:haskell_haddock.bzl", "haskell_haddock")
load("@fbcode_macros//build_defs:haskell_library.bzl", "haskell_library")
load("@fbcode_macros//build_defs:haskell_unittest.bzl", "haskell_unittest")
load("@fbcode_macros//build_defs:js_executable.bzl", "js_executable")
load("@fbcode_macros//build_defs:js_node_module_external.bzl", "js_node_module_external")
load("@fbcode_macros//build_defs:js_npm_module.bzl", "js_npm_module")
load("@fbcode_macros//build_defs:lua_binary.bzl", "lua_binary")
load("@fbcode_macros//build_defs:lua_library.bzl", "lua_library")
load("@fbcode_macros//build_defs:lua_unittest.bzl", "lua_unittest")
load("@fbcode_macros//build_defs:ocaml_binary.bzl", "ocaml_binary")
load("@fbcode_macros//build_defs:ocaml_external_library.bzl", "ocaml_external_library")
load("@fbcode_macros//build_defs:ocaml_library.bzl", "ocaml_library")
load("@fbcode_macros//build_defs:prebuilt_jar.bzl", "prebuilt_jar")
load("@fbcode_macros//build_defs:python_binary.bzl", "python_binary")
load("@fbcode_macros//build_defs:python_library.bzl", "python_library")
load("@fbcode_macros//build_defs:python_unittest.bzl", "python_unittest")
load("@fbcode_macros//build_defs:python_wheel.bzl", "python_wheel")
load("@fbcode_macros//build_defs:python_wheel_default.bzl", "python_wheel_default")
load("@fbcode_macros//build_defs:rust_binary.bzl", "rust_binary")
load("@fbcode_macros//build_defs:rust_bindgen_library.bzl", "rust_bindgen_library")
load("@fbcode_macros//build_defs:rust_external_library.bzl", "rust_external_library")
load("@fbcode_macros//build_defs:rust_library.bzl", "rust_library")
load("@fbcode_macros//build_defs:rust_unittest.bzl", "rust_unittest")
load("@fbcode_macros//build_defs:scala_test.bzl", "scala_test")
load("@fbcode_macros//build_defs:sphinx_manpage.bzl", "sphinx_manpage")
load("@fbcode_macros//build_defs:sphinx_wiki.bzl", "sphinx_wiki")
load("@fbcode_macros//build_defs:swig_library.bzl", "swig_library")
load("@fbcode_macros//build_defs/lib:visibility.bzl", "get_visibility_for_base_path")

__all__ = []

_CONVERTER_MAP = {
    "cgo_library": cgo_library,
    "cpp_benchmark": cpp_benchmark,
    "cpp_binary": cpp_binary,
    "cpp_binary_external": discard,
    "cpp_java_extension": cpp_java_extension,
    "cpp_library": cpp_library,
    "cpp_library_external": cpp_library_external,
    "cpp_library_external_custom": cpp_library_external_custom,
    "cpp_lua_extension": cpp_lua_extension,
    "cpp_lua_main_module": cpp_lua_main_module,
    "cpp_module_external": cpp_module_external,
    "cpp_node_extension": cpp_node_extension,
    "cpp_precompiled_header": cpp_precompiled_header,
    "cpp_python_extension": cpp_python_extension,
    "cpp_unittest": cpp_unittest,
    "custom_rule": custom_rule,
    "cython_library": cython_library,
    "d_binary": d_binary,
    "d_library": d_library,
    "d_library_external": d_library_external,
    "go_binary": go_binary,
    "go_bindgen_library": go_bindgen_library,
    "go_library": go_library,
    "go_unittest": go_unittest,
    "haskell_binary": haskell_binary,
    "haskell_external_library": haskell_external_library,
    "haskell_ghci": haskell_ghci,
    "haskell_haddock": haskell_haddock,
    "haskell_library": haskell_library,
    "haskell_unittest": haskell_unittest,
    "js_executable": js_executable,
    "js_node_module_external": js_node_module_external,
    "js_npm_module": js_npm_module,
    "lua_binary": lua_binary,
    "lua_library": lua_library,
    "lua_unittest": lua_unittest,
    "ocaml_binary": ocaml_binary,
    "ocaml_external_library": ocaml_external_library,
    "ocaml_library": ocaml_library,
    "prebuilt_jar": prebuilt_jar,
    "python_binary": python_binary,
    "python_library": python_library,
    "python_unittest": python_unittest,
    "python_wheel": python_wheel,
    "python_wheel_default": python_wheel_default,
    "rust_binary": rust_binary,
    "rust_bindgen_library": rust_bindgen_library,
    "rust_external_library": rust_external_library,
    "rust_library": rust_library,
    "rust_unittest": rust_unittest,
    "scala_test": scala_test,
    "sphinx_manpage": sphinx_manpage,
    "sphinx_wiki": sphinx_wiki,
    "swig_library": swig_library,
}

def rule_handler(rule_type, **kwargs):
    """
    Callback that fires when a TARGETS rule is evaluated, converting it into
    one or more Buck rules.
    """

    attributes = kwargs

    base_path = get_base_path()

    # Set default visibility
    attributes["visibility"] = get_visibility_for_base_path(
        attributes.get("visibility"),
        attributes.get("name"),
        base_path,
    )

    # Convert the fbconfig/fbmake rule into one or more Buck rules.
    converter = _CONVERTER_MAP.get(rule_type)

    if converter == None:
        name = "{0}:{1}".format(base_path, attributes["name"])
        fail("unknown rule type %s for %s" % (rule_type, name))

    converter(**attributes)

# Helper rule to throw an error when accessing raw Buck rules.
def invalid_buck_rule(rule_type, *args, **kwargs):
    fail(("{}(): unsupported access to raw Buck rules! " +
          "Please use {} instead. " +
          "See https://fburl.com/fbcode-targets for all available rules")
        .format(rule_type, BUCK_TO_FBCODE_MAP.get(rule_type, "supported fbcode rules")))

# Helper rule to ignore a Buck rule if requested by buck config.
def ignored_buck_rule(rule_type, *args, **kwargs):
    pass

__all__.append("install_converted_rules")

def install_converted_rules(globals):
    # @lint-ignore BUCKRESTRICTEDSYNTAX FBCODEBZLFORMAT
    import functools
    # Prevent direct access to raw BUCK UI, as it doesn"t go through our
    # wrappers.
    for rule_type in BUCK_RULES:
        globals[rule_type] = functools.partial(invalid_buck_rule, rule_type)

    all_rule_types = FBCODE_RULES + \
                     ["buck_" + r for r in BUCK_RULES]
    for rule_type in all_rule_types:
        globals[rule_type] = functools.partial(rule_handler, rule_type)

    # If fbcode.enabled_rule_types is specified, then all rule types that aren't
    # whitelisted should be redirected to a handler that"s a no-op. For example,
    # only a small set of rules are supported for folks building on laptop.
    enabled_rule_types = native.read_config("fbcode", "enabled_rule_types", None)
    if enabled_rule_types != None:
        enabled_rule_types = [r.strip() for r in enabled_rule_types.split(",")]
        for rule_type in sets.make(all_rule_types).difference(sets.make(enabled_rule_types)):
            globals[rule_type] = functools.partial(ignored_buck_rule, rule_type)
