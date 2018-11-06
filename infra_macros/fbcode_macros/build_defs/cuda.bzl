load("@bazel_skylib//lib:paths.bzl", "paths")

def _is_cuda_src(src):
    """
    Return whether this `srcs` entry is a CUDA source file.

    Args:
        src: A string representing a label or source path

    Returns:
        True if ends in .cu, else False
    """

    # If this is a generated rule reference, then extract the source
    # name.
    if "=" in src:
        src = src.rsplit("=", 1)[1]

    # Assume generated sources without explicit extensions are non-CUDA
    if src.startswith(("@", ":", "//")):
        return False

    # If the source extension is `.cu` it's cuda.
    _, ext = paths.split_extension(src)
    return ext == ".cu"

def _has_cuda_srcs(srcs):
    """ Return whether any src in `srcs` looks like a CUDA file """

    for src in srcs:
        if _is_cuda_src(src):
            return True
    return False

def _has_cuda_dep(dependencies):
    """
    Returns whether there is any dependency on CUDA tp2.

    Args:
        dependencies: A list of `RuleTarget` structs

    Returns:
        True if any dependency is in the 'cuda' directory, else False
    """

    for dep in dependencies:
        if dep.repo != None and dep.base_path == "cuda":
            return True

    return False

cuda = struct(
    has_cuda_dep = _has_cuda_dep,
    has_cuda_srcs = _has_cuda_srcs,
    is_cuda_src = _is_cuda_src,
)
