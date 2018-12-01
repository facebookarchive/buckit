load("@bazel_skylib//lib:shell.bzl", _shell = "shell")

def _split(s):
    """ Rudimentary implementation of shell string splitting similar to shlex.split """
    ret = []
    char = None
    delimiter = ""
    current_string = ""
    in_escape = False

    for char in s:
        if in_escape:
            # shlex.split only interprets backslash as an escape for '"' and '\' inside
            # of double quotes
            # https://github.com/python/cpython/blob/06e7608207daab9fb82d13ccf2d3664535442f11/Lib/shlex.py#L207
            if (delimiter == '"' and char not in '\\"') or delimiter == "'":
                current_string += "\\"
            current_string += char
            in_escape = False
        elif char == "\\":
            in_escape = True
        elif char.isspace():
            if not delimiter:
                if current_string:
                    ret.append(current_string)
                    current_string = ""
            else:
                current_string += char
        elif delimiter:
            if char != delimiter:
                current_string += char
            else:
                delimiter = ""
        elif char in '\'"':
            delimiter = char
        else:
            current_string += char

    if current_string:
        ret.append(current_string)

    if delimiter:
        fail("found one delimiter ({}) in `{}`, but not closing one".format(delimiter, s))
    if in_escape:
        fail("found one backslash in {}, but nothing following it".format(s))

    return ret

shell = struct(
    array_literal = _shell.array_literal,
    quote = _shell.quote,
    split = _split,
)
