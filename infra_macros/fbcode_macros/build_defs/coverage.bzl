load("@fbcode_macros//build_defs/config:read_configs.bzl", "read_boolean")
load("@fbcode_macros//build_defs/lib:shell.bzl", "shell")
load("@fbcode_macros//build_defs/lib:target_utils.bzl", "target_utils")
load("@fbcode_macros//build_defs:compiler.bzl", "compiler")
load("@fbcode_macros//build_defs:sanitizers.bzl", "sanitizers")

_SANITIZER_COVERAGE_FLAGS = ["-fsanitize-coverage=bb"]

# Add flags to enable LLVM's Source-based Code Coverage
_SOURCE_BASED_COVERAGE_FLAGS = [
    "-fprofile-instr-generate",
    "-fcoverage-mapping",
]

# Add flags to enable LLVM's Coverage Mapping.
_COVERAGE_MAPPING_LDFLAGS = [
    "-fprofile-instr-generate",
    "-fcoverage-mapping",
]

# Deps to add if no sanitizer is specified
_NO_SANITIZER_COVERAGE_BINARY_DEPS = [
    target_utils.ThirdPartyRuleTarget("llvm-fb", "clang_rt.profile"),
]

def _get_coverage():
    """
    Whether to gather coverage information or not
    """
    return read_boolean("fbcode", "coverage", False)

def _get_coverage_binary_deps():
    """ Returns RuleTarget objects for all dependencies required for coverage to work """
    if not _get_coverage():
        fail("Tried to get coverage dependencies, but config fbcode.coverage is false")

    compiler.require_global_compiler(
        "can only use coverage with build modes that use clang globally",
        "clang",
    )

    if sanitizers.get_sanitizer() == None:
        return _NO_SANITIZER_COVERAGE_BINARY_DEPS

    # all coverage deps are included in the santizer deps
    return []

def _get_coverage_flags(base_path):
    """
    Return compiler flags needed to support coverage builds.

    Args:
        base_path: The package to check
    """

    if _is_coverage_enabled(base_path):
        if sanitizers.get_sanitizer() != None:
            return _SANITIZER_COVERAGE_FLAGS
        else:
            return _SOURCE_BASED_COVERAGE_FLAGS
    return []

def _allowed_by_coverage_only(base_path):
    """
    Returns whether the `cxx.coverage_only` whitelists the given rule for
    coverage. `cxx.coverage_only` should be a list of path prefixes if set.

    Args:
        base_path: The package to check
    """

    prefixes = native.read_config("cxx", "coverage_only", None)

    # If not option was set, then always enable coverage.
    if prefixes == None:
        return True

    # Otherwise, the base path has to match one of the prefixes to enable
    # coverage.
    for prefix in shell.split(prefixes):
        if base_path.startswith(prefix):
            return True

    return False

def _is_coverage_enabled(base_path):
    """
    Return whether to build C/C++ code with coverage enabled.

    Args:
        base_path: The package to check
    """

    # Only use coverage if the global build mode coverage flag is set.
    if not _get_coverage():
        return False

    # Make sure the `cxx.coverage_only` option allows this rule.
    if not _allowed_by_coverage_only(base_path):
        return False

    # We use LLVM's coverage modes so that all coverage instrumentation
    # is inlined in the binaries and so work seamlessly with Buck's caching
    # (http://llvm.org/docs/CoverageMappingFormat.html).
    compiler.require_global_compiler(
        "can only use coverage with build modes that use clang globally",
        "clang",
    )

    return True

def _get_coverage_ldflags(base_path):
    """
    Return compiler flags needed to support coverage builds.

    Args:
        base_path: The package to check
    """

    if _is_coverage_enabled(base_path) and sanitizers.get_sanitizer() == None:
        return _COVERAGE_MAPPING_LDFLAGS
    return []

coverage = struct(
    get_coverage = _get_coverage,
    get_coverage_binary_deps = _get_coverage_binary_deps,
    get_coverage_flags = _get_coverage_flags,
    get_coverage_ldflags = _get_coverage_ldflags,
    is_coverage_enabled = _is_coverage_enabled,
)
