load("@bazel_skylib//lib:types.bzl", "types")

def _image_source_impl(
        # Buck target outputting file or directory, conflicts with `layer`.
        #
        # Internal note: If `source` is a struct, it is interpreted as an
        # already-constructed `image.source`.  Implementers of rules that
        # accept `image.source` should always call `image.source(input_src)`
        # to get easy input validation, and to accept `"//target:path"` to
        # mean `image.source("//target:path")`.
        source = None,
        # `image.layer` target, conflicts w/ `source`
        layer = None,
        # Relative path within `soure` or `layer`.
        path = None):
    if bool(source) + bool(layer) != 1:
        fail("Exactly one of `source`, `layer` must be set")
    return struct(source = source, layer = layer, path = path)

# `_image_source_impl` documents the function signature.  It is intentional
# that arguments besides `source` are keyword-only.
def image_source(source = None, **kwargs):
    if source == None or types.is_string(source):
        return _image_source_impl(source = source, **kwargs)
    if kwargs:
        fail("Got struct source {} with other args".format(source))
    return _image_source_impl(**source._asdict())
