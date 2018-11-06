load("@fbcode_macros//build_defs:allocator_targets.bzl", "allocator_targets")
load("@fbcode_macros//build_defs:target_utils.bzl", "target_utils")

_ALLOCATOR_DEPS = {
    allocator: [target_utils.parse_target(rdep) for rdep in targets]
    for allocator, targets in allocator_targets.items()
}

_ALLOCATOR_NAMES = allocator_targets.keys()

def _get_allocator_names():
    return _ALLOCATOR_NAMES

def _get_default_allocator():
    """
    Which allocator to use when not specified explicitly

    Returns:
        The allocator from fbcode.allocators that should be used by default
    """
    return native.read_config("fbcode", "default_allocator", "malloc")

def _get_allocators():
    """ Returns a list of buck labels used for varous allocators """
    return allocator_targets

def _get_allocator_deps(allocator):
    """ Return the a list of `RuleTarget` that must be depended on to use `allocator` """
    return _ALLOCATOR_DEPS[allocator]

def _normalize_allocator(allocator):
    """
    Normalizes allocator parameters for various rules

    Args:
        allocator: One of None, or a short name for an allocator in get_allocator_names()

    Returns:
        The original allocator, or if `allocator` is None, the default allocator
    """
    if allocator == None:
        return _get_default_allocator()
    else:
        return allocator

allocators = struct(
    get_allocator_deps = _get_allocator_deps,
    get_allocator_names = _get_allocator_names,
    get_allocators = _get_allocators,
    get_default_allocator = _get_default_allocator,
    normalize_allocator = _normalize_allocator,
)
