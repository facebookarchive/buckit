load("@fbcode_macros//build_defs/config:read_configs.bzl", "read_string")
load("@fbcode_macros//build_defs:global_compiler.bzl", "require_global_compiler")
load("@fbcode_macros//build_defs:target_utils.bzl", "target_utils")

# Maps sanitizer type to a shortname used in rules and tags/labels
_SANITIZERS = {
    "address": "asan",
    "address-undefined": "asan-ubsan",
    "efficiency-cache": "esan-cache",
    "thread": "tsan",
    "undefined": "ubsan",
    "address-undefined-dev": "asan-ubsan",
}

_ASAN_DEFAULT_OPTIONS = {
    "check_initialization_order": "1",
    "detect_invalid_pointer_pairs": "1",
    "detect_leaks": "1",
    "detect_odr_violation": "1",
    "detect_stack_use_after_return": "1",
    "print_scariness": "1",
    "print_suppressions": "0",
    "strict_init_order": "1",
}

_UBSAN_DEFAULT_OPTIONS = {
    "print_stacktrace": "1",
    "report_error_type": "1",
}

_LSAN_DEFAULT_SUPPRESSIONS = [
    "boost::python::",
    "CRYPTO_malloc",
    "CRYPTO_zalloc",
    "_d_run_main",
    "/lib/libpython",
    "libluajit-5.1.so.2",
    "/src/cpython",
]

_TSAN_DEFAULT_OPTIONS = {
    "detect_deadlocks": "1",
    "halt_on_error": "1",
    "second_deadlock_stack": "1",
    "symbolize": "0",
}

_ASAN_UBSAN_FLAGS = [
    "-fno-common",
    "-fsanitize=address",
    "-fsanitize-address-use-after-scope",
    "-fsanitize=nullability",
    "-fsanitize=undefined",
    "-fno-sanitize=alignment",
    "-fno-sanitize=function",
    "-fno-sanitize=null",
    "-fno-sanitize=object-size",
    "-fno-sanitize=unsigned-integer-overflow",
    "-fno-sanitize=vptr",
]

_UBSAN_FLAGS = [
    "-fsanitize=undefined",
    "-fno-sanitize=alignment",
    "-fno-sanitize=null",

    # Python extensions are loaded with RTLD_LOCAL which is
    # incompatible with vptr & function UBSAN checks.
    "-fsanitize-recover=function",
    "-fsanitize-recover=vptr",
]

_SANITIZER_FLAGS = {
    "address": _ASAN_UBSAN_FLAGS,
    "address-undefined": _ASAN_UBSAN_FLAGS + _UBSAN_FLAGS,
    "efficiency-cache": [
        "-fsanitize=efficiency-cache-frag",
    ],
    "undefined": _UBSAN_FLAGS,
    "address-undefined-dev": _ASAN_UBSAN_FLAGS,
    "thread": [
        "-fsanitize=thread",
    ],
}

_SANITIZER_COMMON_FLAGS = [
    "-fno-sanitize-recover=all",
    "-fno-omit-frame-pointer",

    # put function or data item into its own section
    # and use --gc-sections to remove unused code
    "-fdata-sections",
    "-ffunction-sections",
]

_FULL_SANITIZER_FLAGS = {k: _SANITIZER_COMMON_FLAGS + v for k, v in _SANITIZER_FLAGS.items()}

def _get_sanitizer():
    """
    The type of sanitizer to try to use. If not set, do not use it
    """

    # TODO(T25416171): ASAN currently isn't well supported on aarch64. so
    # disable it for now.  We do this by detecting the host platform, but
    # longer-term, we should implement ASAN purely via Buck's C/C++
    # platforms to do this correctly.
    if native.host_info().arch.is_aarch64:
        return None

    return read_string("fbcode", "sanitizer", None) or None

def _get_label():
    """
    Gets a label to use based on the sanitizer specified. Returns a string or None
    """
    sanitizer = _get_sanitizer()
    if sanitizer != None and sanitizer != "address-undefined-dev":
        return _SANITIZERS[sanitizer]
    return None

def _get_sanitizer_binary_deps():
    """
    Add additional dependencies needed to build with the given sanitizer.

    Returns:
        A list of tuples of package and rule name. Eventually this will return
        a label after migration is complete.
    """

    sanitizer = _get_sanitizer()
    if sanitizer == None:
        return []

    require_global_compiler(
        "can only use sanitizers with build modes that use clang globally",
        "clang",
    )

    return [
        target_utils.RootRuleTarget("tools/build/sanitizers", _SANITIZERS[sanitizer] + "-cpp"),
    ]

def _get_sanitizer_flags():
    """
    Return compiler/preprocessor flags needed to support sanitized builds.
    """

    sanitizer = _get_sanitizer()
    if sanitizer == None:
        fail("No sanitizer was specified")

    require_global_compiler(
        "can only use sanitizers with build modes that use clang globally",
        "clang",
    )
    if sanitizer not in _FULL_SANITIZER_FLAGS:
        fail("No flags are available for sanitizer " + sanitizer)

    return _FULL_SANITIZER_FLAGS[sanitizer]

def _get_short_name(long_name):
    """ Get a shortname for a sanitizer specified in fbcode.sanitizer config """
    return _SANITIZERS[long_name]

sanitizers = struct(
    ASAN_DEFAULT_OPTIONS = _ASAN_DEFAULT_OPTIONS,
    LSAN_DEFAULT_SUPPRESSIONS = _LSAN_DEFAULT_SUPPRESSIONS,
    TSAN_DEFAULT_OPTIONS = _TSAN_DEFAULT_OPTIONS,
    UBSAN_DEFAULT_OPTIONS = _UBSAN_DEFAULT_OPTIONS,
    get_label = _get_label,
    get_sanitizer = _get_sanitizer,
    get_sanitizer_binary_deps = _get_sanitizer_binary_deps,
    get_sanitizer_flags = _get_sanitizer_flags,
    get_short_name = _get_short_name,
)
