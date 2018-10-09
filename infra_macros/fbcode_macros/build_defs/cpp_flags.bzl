# The languages which general compiler flag apply to.
_COMPILER_LANGS = (
    "asm",
    "assembler",
    "c_cpp_output",
    "cuda_cpp_output",
    "cxx_cpp_output",
)

cpp_flags = struct(
    COMPILER_LANGS = _COMPILER_LANGS,
)
