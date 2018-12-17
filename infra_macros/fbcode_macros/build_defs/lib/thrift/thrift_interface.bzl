"""
Common methods used to implement a 'language' in the thrift_library macro
"""

load("@fbcode_macros//build_defs:config.bzl", "config")
load("@fbsource//tools/build_defs:buckconfig.bzl", "read_bool")

_THRIFT_FLAGS = (
    "--allow-64bit-consts",
)

def _default_get_compiler():
    return config.get_thrift_compiler()

def _default_get_compiler_command(compiler, compiler_args, includes, additional_compiler):
    cmd = []
    cmd.append("$(exe {})".format(compiler))
    cmd.extend(compiler_args)
    cmd.append("-I")
    cmd.append(
        "$(location {})".format(includes),
    )
    if read_bool("thrift", "use_templates", True):
        cmd.append("--templates")
        cmd.append("$(location {})".format(config.get_thrift_templates()))
    cmd.append("-o")
    cmd.append('"$OUT"')

    # TODO(T17324385): Work around an issue where dep chains of binaries
    # (e.g. one binary which delegates to another when it runs), aren't
    # added to the rule key when run in `genrule`s.  So, we need to
    # explicitly add these deps to the `genrule` using `$(exe ...)`.
    # However, since the implemenetation of `--python-compiler` in thrift
    # requires a single file path, and since `$(exe ...)` actually expands
    # to a list of args, we ues `$(query_outputs ...)` here and just append
    # `$(exe ...)` to the end of the command below, in a comment.
    if additional_compiler:
        cmd.append("--python-compiler")
        cmd.append('$(query_outputs "{}")'.format(additional_compiler))
    cmd.append('"$SRCS"')

    # TODO(T17324385): Followup mentioned in above comment.
    if additional_compiler:
        cmd.append("# $(exe {})".format(additional_compiler))

    return " ".join(cmd)

def _default_get_extra_includes(**_kwargs):
    return []

def _default_get_postprocess_command(base_path, thrift_src, out_dir, **_kwargs):
    _ignore = base_path
    _ignore = thrift_src
    _ignore = out_dir
    return None

def _default_get_additional_compiler():
    return None

def _format_options(options):
    """
    Format a thrift option dict into a compiler-ready string.
    """

    option_list = []

    for option, val in options.items():
        if val != None:
            option_list.append("{}={}".format(option, val))
        else:
            option_list.append(option)

    return ",".join(option_list)

def _default_get_compiler_args(compiler_lang, flags, options, **_kwargs):
    args = []
    args.append("--gen")
    args.append("{}:{}".format(compiler_lang, _format_options(options)))
    args.extend(_THRIFT_FLAGS)
    args.extend(flags)
    return args

def _default_get_options(base_path, parsed_options):
    _ignore = base_path
    return parsed_options

def _make(
        get_lang,
        get_names,
        get_generated_sources,
        get_language_rule,
        get_compiler = _default_get_compiler,
        get_compiler_lang = None,
        get_extra_includes = _default_get_extra_includes,
        get_postprocess_command = _default_get_postprocess_command,
        get_additional_compiler = _default_get_additional_compiler,
        get_compiler_args = _default_get_compiler_args,
        get_compiler_command = _default_get_compiler_command,
        get_options = _default_get_options):
    """
    Factory method to create a class like object for instantiating rules for a given language

    Args:
        get_lang: Return the name that should be used in build files to use
                  this converter. e.g. cpp2
                  () -> str
        get_names: Return a sequence of all other names that can also reference this
                   converter. This is mostly used for aliasing languages in
                   thrift_library
                   () -> Iterable[str]
        get_generated_sources: Return a dict of all generated thrift sources, mapping
                               the logical language-specific name to the path of the
                               generated source relative to the thrift compiler output
                               directory.
                               (base_path, name, thrift_src, services, options, **kwargs) -> Mapping[str, str]
        get_compiler: Return which thrift compiler to use. This should be a buck label
                      () -> str
        get_compiler_lang: Return the language to pass to the thrift compiler
                           () -> str
        get_extra_includes: Return any additional files that should be included in the
                            exported thrift compiler include tree.
                            (**kwargs) -> Sequence[str]
        get_postprocess_command: Return an additional command to run after the compiler
                                 has completed. Useful for adding language-specific
                                 error checking.
                                 (base_path, thrift_src, out_dir, **kwargs) -> Optional[str]
        get_additional_compiler: Target of additional compiler that should be provided
                                 to the thrift1 compiler (or None)
        get_compiler_args: Return args to pass into the compiler when generating sources
                           (compiler_lang, flags, options, **kwargs) -> Sequence[str]
        get_compiler_command: Return the command to use to invoke the thrift compiler
                              (compiler, compiler_args, includes, additional_compiler) -> str
        get_options: Apply any conversions to parsed language-specific thrift options.
                     (base_path, parsed_options) -> Sequence[str]

    Returns:
        Struct for use by thrift_library with all helper methods configured as
        the members.
    """
    get_compiler_lang = get_compiler_lang or get_lang
    return struct(
        get_lang = get_lang,
        get_names = get_names,
        get_generated_sources = get_generated_sources,
        get_language_rule = get_language_rule,
        get_compiler = get_compiler,
        get_compiler_lang = get_compiler_lang,
        get_extra_includes = get_extra_includes,
        get_postprocess_command = get_postprocess_command,
        get_additional_compiler = get_additional_compiler,
        get_compiler_args = get_compiler_args,
        get_compiler_command = get_compiler_command,
        get_options = get_options,
    )

thrift_interface = struct(
    default_get_additional_compiler = _default_get_additional_compiler,
    default_get_compiler = _default_get_compiler,
    default_get_compiler_args = _default_get_compiler_args,
    default_get_compiler_command = _default_get_compiler_command,
    default_get_extra_includes = _default_get_extra_includes,
    default_get_options = _default_get_options,
    default_get_postprocess_command = _default_get_postprocess_command,
    make = _make,
)
