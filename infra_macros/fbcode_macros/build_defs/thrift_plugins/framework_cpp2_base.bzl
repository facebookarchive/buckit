"""
Helper functions of the Thrift plugin Framework API for C++ target language.
"""

load("@fbsource//tools/build_defs:fb_native_wrapper.bzl", "fb_native")

def _invoke_codegen_rule_name(plugin, target_name, thrift_src):
    """Returns the name of the rule that invokes the plugin codegen binary."""
    return "{}-cpp2-{}-{}".format(target_name, plugin.name, thrift_src)

def _generate_invoke_codegen_rule(
        plugin,
        codegen_rule_name,
        target_name,
        thrift_src,
        target_base_path,
        include_target):
    """Generates a rule that invokes the plugin codegen binary. Returns the name
    of the generated rule.
    """
    rule_name = _invoke_codegen_rule_name(plugin, target_name, thrift_src)
    cmd = "$(exe {}) --target-base-path {} --out-path $OUT $SRCS --include-path $(location {})".format(
        codegen_rule_name,
        target_base_path,
        include_target,
    )

    fb_native.genrule(name = rule_name, out = ".", srcs = [thrift_src], cmd = cmd)

    return rule_name

def _copy_from_codegen_rule_name(plugin, target_name, thrift_src, file):
    """Returns the name of the rule of the copied out artifact."""
    return "{}={}".format(
        _invoke_codegen_rule_name(plugin, target_name, thrift_src),
        file,
    )

def _generate_copy_from_codegen_rule(plugin, target_name, thrift_src, file):
    """Generates a rule that copies a generated file from the plugin codegen output
    directory out into its own target. Returns the name of the generated rule.
    """
    invoke_codegen_rule_name = _invoke_codegen_rule_name(
        plugin,
        target_name,
        thrift_src,
    )
    plugin_path_prefix = "gen-cpp2-{}".format(plugin.name)
    rule_name = _copy_from_codegen_rule_name(plugin, target_name, thrift_src, file)

    cmd = " && ".join(
        [
            "mkdir `dirname $OUT`",
            "cp $(location :{})/{} $OUT".format(invoke_codegen_rule_name, file),
        ],
    )

    fb_native.genrule(
        name = rule_name,
        out = "{}/{}".format(plugin_path_prefix, file),
        cmd = cmd,
    )

    return rule_name

def _generate_rules(
        plugin,
        codegen_rule_name,
        expected_out_headers,
        expected_out_srcs,
        target_base_path,
        target_name,
        lang,
        thrift_srcs,
        compiler_args,
        include_target,
        deps,
        additional_target_deps = [],
        requires_transitive_plugin_build = True):
    """Generates the list of rules required to build Thrift C++ plugin.

    Three types of rules will be generated:

    1) For each Thrift file (module), a rule will be created that invokes the
    Thrift plugin's code generator to generate custom source/header files.

    2) For each generated source/header file, a rule will be created to copy
    the file out from the plugin codegen's output directory into its own rule.

    3) Finally, a single cpp_library will be created to encapsulate all the
    generated source and header files. This final cpp_library can then be
    consumed by plugin users.
    """

    # Will be needed later for arg parsing and include path on the codegen side
    _ignore = [compiler_args]

    if lang != "cpp2":
        return

    header_targets = []
    src_targets = []

    for thrift_src in thrift_srcs:
        # Rule that invokes the plugin codegen
        _generate_invoke_codegen_rule(
            plugin,
            codegen_rule_name,
            target_name,
            thrift_src,
            target_base_path,
            include_target,
        )

    # Rules that copy out the plugin-generated artifacts
    for thrift_src, headers in expected_out_headers.items():
        for header in headers:
            header_targets.append(
                _generate_copy_from_codegen_rule(
                    plugin,
                    target_name,
                    thrift_src,
                    header,
                ),
            )

    for thrift_src, srcs in expected_out_srcs.items():
        for src in srcs:
            src_targets.append(
                _generate_copy_from_codegen_rule(plugin, target_name, thrift_src, src),
            )

    generated_target_deps = additional_target_deps + [
        "//{}:{}-{}".format(target_base_path, target_name, lang),
    ]

    if requires_transitive_plugin_build:
        for dep in deps:
            generated_target_deps.append("{}-{}-{}".format(dep, lang, plugin.name))

    # Master rules that combine the generated artifacts for all .thrift
    # files into a single cpp_library.
    cpp_library(
        name = "{}-{}-{}".format(target_name, lang, plugin.name),
        srcs = [":{}".format(src) for src in src_targets],
        headers = [":{}".format(header) for header in header_targets],
        deps = generated_target_deps,
    )

framework_cpp2_base = struct(generate_rules = _generate_rules)
