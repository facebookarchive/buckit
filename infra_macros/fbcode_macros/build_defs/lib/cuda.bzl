load("@bazel_skylib//lib:new_sets.bzl", "sets")
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

_BANNED_CUDA_FLAGS = sets.make([
    "-DUSE_CUDNN=1",
    "-DUSE_CUDNN",
    "-DCAFFE2_USE_CUDNN",
    "-DUSE_CUDA",
    "-DUSE_CUDA_FUSER_FBCODE=1",
])

_BANNED_CUDA_TARGETS = sets.make([
    ("caffe2/aten", "ATen-cu"),
    ("caffe2/caffe2", "caffe2_cu"),
    ("caffe2/caffe2", "caffe2_gpu"),
    ("caffe2/torch/lib/c10d", "c10d"),
    ("caffe2/torch/lib/THD", "THD"),
    ("gloo", "gloo-cuda"),
])

_CUDA_SRCS_BLACKLIST = [
    ("caffe2/caffe2/", "cudnn.cc"),
    ("caffe2/caffe2/", "gpu.cc"),
    ("caffe2/caffe2/contrib/nervana/", "gpu.cc"),
    ("caffe2/caffe2/operators/", "cudnn.cc"),
    ("caffe2/caffe2/fb/operators/scale_gradient_op_gpu.cc", ""),
    ("caffe2/caffe2/fb/predictor/PooledPredictor.cpp", ""),
    ("caffe2/caffe2/fb/predictor/PredictorGPU.cpp", ""),
    ("caffe2/:generate-code=THCUNN.cpp", ""),
    ("caffe2/torch/csrc/jit/fusers/cuda/", ".cpp"),
    ("caffe2/torch/csrc/cuda/", ".cpp"),
    ("caffe2/torch/csrc/distributed/c10d/ddp.cpp", ""),
]

def _filter_cuda_flags(flags):
    return [f for f in flags if not sets.contains(_BANNED_CUDA_FLAGS, f)]

def _filter_cuda_flags_dict(flags_dict):
    if flags_dict == None:
        return None
    return {
        compiler: _filter_cuda_flags(flags)
        for compiler, flags in flags_dict.items()
    }

def _is_banned_src(src):
    for banned_src in _CUDA_SRCS_BLACKLIST:
        if src.startswith(banned_src[0]) and src.endswith(banned_src[1]):
            return True
    return False

def _strip_cuda_properties(
        base_path,
        name,
        compiler_flags,
        preprocessor_flags,
        propagated_pp_flags,
        nvcc_flags,
        arch_compiler_flags,
        arch_preprocessor_flags,
        srcs):
    """
    Strips cuda related sources and flags
    """
    if sets.contains(_BANNED_CUDA_TARGETS, (base_path, name)):
        print("Warning: no CUDA on platform007: rule {}:{} ignoring all srcs: {}"
            .format(base_path, name, srcs))
        srcs = []

    cuda_srcs = []
    new_srcs = []
    for s in srcs:
        if _is_cuda_src(s) or _is_banned_src(paths.join(base_path, s)):
            cuda_srcs.append(s)
        else:
            new_srcs.append(s)

    return struct(
        srcs = new_srcs,
        arch_compiler_flags = _filter_cuda_flags_dict(arch_compiler_flags),
        arch_preprocessor_flags = _filter_cuda_flags_dict(arch_preprocessor_flags),
        compiler_flags = _filter_cuda_flags(compiler_flags),
        cuda_srcs = cuda_srcs,
        nvcc_flags = _filter_cuda_flags(nvcc_flags),
        preprocessor_flags = _filter_cuda_flags(preprocessor_flags),
        propagated_pp_flags = _filter_cuda_flags(propagated_pp_flags),
    )

cuda = struct(
    has_cuda_srcs = _has_cuda_srcs,
    is_cuda_src = _is_cuda_src,
    strip_cuda_properties = _strip_cuda_properties,
)
