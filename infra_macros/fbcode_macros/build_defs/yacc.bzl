load("@fbsource//tools/build_defs:fb_native_wrapper.bzl", "fb_native")
load("@bazel_skylib//lib:shell.bzl", "shell")
load("@bazel_skylib//lib:paths.bzl", "paths")
load("@fbcode_macros//build_defs:custom_rule.bzl", "copy_genrule_output_file")
load("@fbcode_macros//build_defs:target_utils.bzl", "target_utils")

_YACC = target_utils.ThirdPartyToolRuleTarget("bison", "bison")

_YACC_FLAGS = [
    "-y",
    "-d",
]

YACC_EXTS = (
    ".yy",
)

_YACC_CMD = (
    "mkdir -p $OUT && " +
    '$(exe {yacc}) {args} -o "$OUT/"{base}.c $SRCS && ' +

    # Sanitize the header and source files of original source line-
    # markers and include guards.
    "sed -i" +
    r""" -e 's|'"$SRCS"'|'{src}'|g' """ +
    """ -e 's|YY_YY_.*_INCLUDED|YY_YY_{defn}_INCLUDED|g' """ +
    ' "$OUT/"{base}.c "$OUT/"{base}.h && ' +

    # Sanitize the source file of self-referencing line-markers.
    "sed -i" +
    """ -e 's|\\b'{base}'\.c\\b|'{base}'.cc|g' """ +
    r""" -e 's|'"$OUT/"{base}'\.cc\b|'{out_cc}'|g' """ +
    ' "$OUT/"{base}.c && ' +

    # Sanitize the header file of self-referencing line-markers.
    "sed -i" +
    r""" -e 's|'"$OUT/"{base}'\.h\b|'{out_h}'|g' "$OUT/"{base}.h && """ +
    'mv "$OUT/"{base}.c "$OUT/"{base}.cc'
)

_YACC_CMD_FOR_CPP = _YACC_CMD + " && " + (
    # Patch the header file to add include header file prefix
    # e.g.: thrifty.yy.h => thrift/compiler/thrifty.yy.h
    "sed -i" +
    r""" -e 's|#include "'{base}.h'"|#include "'{base_path}/{base}.h'"|g' """ +
    ' "$OUT/"{base}.cc && ' +

    # Sanitize the stack header file's line-markers.
    ("sed -i" +
     """ -e 's|#\(.*\)YY_YY_[A-Z0-9_]*_FBCODE_|#\\1YY_YY_FBCODE_|g' """ +
     r""" -e 's|#line \([0-9]*\) "/.*/fbcode/|#line \1 "fbcode/|g' """ +
     """ -e 's|\\\\file /.*/fbcode/|\\\\file fbcode/|g' """ +
     ' "$OUT/"{stack_header}')
)

def yacc(name, yacc_flags, yacc_src, platform, visibility):
    """
    Create rules to generate a C/C++ header and source from the given yacc file

    Args:
        name: The base name to use when generating rules (see Outputs)
        lex_flags: A list of flags to pass to flex
        lex_src: The lex source file to operate on
        platform: The platform to use to find the lex tool
        visibility: The visibility for this rule. Note this is not modified by global
                    rules.

    Returns:
        Tuple of ([relative target name for each generated header], relative target for the generated source file)
    """

    base_path = native.package_name()
    is_cpp = ("--skeleton=lalr1.cc" in yacc_flags)
    sanitized_name = name.replace("/", "-")
    genrule_name = "{}={}".format(sanitized_name, yacc_src)

    base = yacc_src
    header = base + ".h"
    source = base + ".cc"

    if is_cpp:
        stack_header = "stack.hh"
    else:
        stack_header = None

    commands = _YACC_CMD_FOR_CPP if is_cpp else _YACC_CMD

    # Cleaned up paths to use in generated source. Note that these
    # paths assume buck-out layout, which is not guaranteed to have
    # any particular layout. This is really only used for #line
    # changes, so it's not a huge deal.
    out_cc = paths.join("buck-out", "gen", base_path, base + ".cc", base + ".cc")
    out_h = paths.join("buck-out", "gen", base_path, base + ".h", base + ".h")

    cmd = commands.format(
        yacc = target_utils.target_to_label(_YACC, platform = platform),
        args = " ".join([
            shell.quote(f)
            for f in _YACC_FLAGS + list(yacc_flags)
        ]),
        src = shell.quote(paths.join(base_path, yacc_src)),
        out_cc = shell.quote(out_cc),
        out_h = shell.quote(out_h),
        defn = paths.join(base_path, header).upper().replace(".", "_").replace("/", "_"),
        base = shell.quote(base),
        base_path = base_path,
        stack_header = stack_header,
    )

    fb_native.genrule(
        name = genrule_name,
        out = base + ".d",
        srcs = [yacc_src],
        cmd = cmd,
    )

    header_targets = [
        ":" + copy_genrule_output_file(
            sanitized_name,
            ":" + genrule_name,
            header,
            visibility,
        ),
    ]
    if is_cpp:
        header_targets.append(
            ":" + copy_genrule_output_file(
                sanitized_name,
                ":" + genrule_name,
                stack_header,
                visibility,
            ),
        )

    source_target = ":" + copy_genrule_output_file(
        sanitized_name,
        ":" + genrule_name,
        source,
        visibility,
    )

    return (header_targets, source_target)
