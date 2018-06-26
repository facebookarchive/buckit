load("@bazel_skylib//lib:shell.bzl", "shell")
load("@fbcode_macros//build_defs:compiler.bzl", "compiler")
load("@fbcode_macros//build_defs/config:read_configs.bzl", "read_boolean")

def _enabled():
    enabled = read_boolean('cxx', 'modules', False)
    if enabled:
        compiler.require_global_compiler(
            "C/C++ modules are only supported when using clang globally",
            "clang")
    return enabled

def _get_module_name(cell, base_path, name):
    module_name = '_'.join([cell, base_path, name])

    # Sanitize input of chars that can't be used in a module map token.
    for c in '-/':
        module_name = module_name.replace(c, '_')

    return module_name

def _get_module_map(name, headers):
    lines = []
    lines.append('module {} {{'.format(name))
    for header, attrs in sorted(headers.items()):
        line = '  '
        for attr in sorted(attrs):
            line += attr + ' '
        line += 'header "{}"'.format(header)
        lines.append(line)
    lines.append('  export *')
    lines.append('}')
    return ''.join([line + '\n' for line in lines])

def _module_map_rule(name, module_name, headers):
    contents = _get_module_map(module_name, headers)
    native.genrule(
        name = name,
        out = 'module.modulemap',
        cmd = 'echo {} > "$OUT"'.format(shell.quote(contents)),
    )

modules = struct(
    enabled = _enabled,
    get_module_map = _get_module_map,
    get_module_name = _get_module_name,
    module_map_rule = _module_map_rule,
)
