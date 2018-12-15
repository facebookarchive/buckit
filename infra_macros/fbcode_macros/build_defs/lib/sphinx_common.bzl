"""Helper function for sphinx rules."""

load("@fbcode_macros//build_defs/lib:target_utils.bzl", "target_utils")
load("@fbcode_macros//build_defs:python_binary.bzl", "python_binary")
load("@fbsource//tools/build_defs:fb_native_wrapper.bzl", "fb_native")

FBSPHINX_WRAPPER = "//fbsphinx:buck"
SPHINXCONFIG_TGT = "//:.sphinxconfig"

def _genrule_srcs_rules(base_path, name, genrule_srcs):
    """
    A simple genrule wrapper for running some target which generates rst
    """
    if not genrule_srcs:
        return []

    rules = []

    for target, outdir in genrule_srcs.items():
        rule = target_utils.parse_target(target, default_base_path = base_path)
        if "/" in outdir:
            root, rest = outdir.split("/", 1)
        else:
            root = outdir
            rest = "."
        rule_name = name + "-genrule_srcs-" + rule.name
        fb_native.genrule(
            name = rule_name,
            out = root,
            bash = " ".join(
                (
                    "mkdir -p $OUT/{rest} &&",
                    "PYTHONWARNINGS=i $(exe {target})",
                    "$OUT/{rest}",
                ),
            ).format(target = target, rest = rest),
        )
        rules.append(rule_name)

    return rules

def _apidoc_rules(name, fbsphinx_buck_target, apidoc_modules):
    """
    A simple genrule wrapper for running sphinx-apidoc
    """
    if not apidoc_modules:
        return []

    rules = []

    for module, outdir in apidoc_modules.items():
        command = " ".join(
            (
                "mkdir -p $OUT &&",
                "PYTHONWARNINGS=i $(exe :{fbsphinx_buck_target})",
                "buck apidoc",
                module,
                "$OUT",
            ),
        ).format(fbsphinx_buck_target = fbsphinx_buck_target)
        rule_name = name + "-apidoc-" + module
        fb_native.genrule(
            name = rule_name,
            out = outdir,
            bash = command,
        )
        rules.append(rule_name)

    return rules

def _sphinx_rule(
        base_path,
        name,
        rule_type,
        builder,
        labels,
        apidoc_modules = None,
        config = None,
        genrule_srcs = None,
        python_binary_deps = (),
        python_library_deps = (),
        srcs = None):
    """
    Entry point for converting sphinx rules
    """
    python_deps = (
        tuple(python_library_deps) +
        tuple([_dep + "-library" for _dep in tuple(python_binary_deps)]) +
        (FBSPHINX_WRAPPER,)
    )
    fbsphinx_buck_target = "%s-fbsphinx-buck" % name
    python_binary(
        name = fbsphinx_buck_target,
        par_style = "xar",
        py_version = ">=3.6",
        main_module = "fbsphinx.bin.fbsphinx_buck",
        deps = python_deps,
    )

    additional_doc_rules = []

    additional_doc_rules.extend(
        _apidoc_rules(
            name,
            fbsphinx_buck_target,
            apidoc_modules,
        ),
    )

    additional_doc_rules.extend(
        _genrule_srcs_rules(base_path, name, genrule_srcs),
    )

    command = " ".join(
        (
            "echo {BUCK_NONCE} >/dev/null &&",
            "PYTHONWARNINGS=i $(exe :{fbsphinx_buck_target})",
            "buck run",
            "--target {target}",
            "--builder {builder}",
            "--sphinxconfig $(location {SPHINXCONFIG_TGT})",
            "--config '{config}'",
            "--generated-sources '{generated_sources}'",
            ".",  # source dir
            "$OUT",
        ),
    ).format(
        BUCK_NONCE = native.read_config("sphinx", "buck_nonce", ""),
        fbsphinx_buck_target = fbsphinx_buck_target,
        target = "//{}:{}".format(base_path, name),
        builder = builder,
        SPHINXCONFIG_TGT = SPHINXCONFIG_TGT,
        config = struct(config = (config or {})).to_json(),
        generated_sources = "[" + ",".join([
            "\"$(location :{})\"".format(rule)
            for rule in additional_doc_rules
        ]) + "]",
    )

    # fb_native rule adds extra labels that genrule fails to swallow
    native.genrule(
        name = name,
        type = rule_type,
        out = "builder=" + builder,
        bash = command,
        srcs = srcs,
        labels = labels,
    )

sphinx_common = struct(
    sphinx_rule = _sphinx_rule,
)
