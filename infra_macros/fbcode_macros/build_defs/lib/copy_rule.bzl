load("@fbsource//tools/build_defs:fb_native_wrapper.bzl", "fb_native")

def copy_rule(src, name, out = None, propagate_versions = False, visibility = None, labels = None):
    """
    Copies the given source into out destination.

    In case out is not provided, name is used as the name of the output.

    Args:
        src: The path or target of identifying the input that should be copied.
        name: The name of the rule.
        out: An optional name of the output that is produced. In case it's not
              provided, a name is used instead.
        propagate_versions: whether this rule needs to be part of the versioned
              sub-tree of it's consumer.
        visibility: If provided a list of visibility patterns for this rule.
        labels: An optional list of labels (tags) that should be associated with
              the produced target.
    """

    if out == None:
        out = name

    attrs = {}
    attrs["name"] = name
    if labels != None:
        attrs["labels"] = labels
    if visibility != None:
        attrs["visibility"] = visibility
    attrs["out"] = out
    attrs["cmd"] = " && ".join([
        "mkdir -p `dirname $OUT`",
        "cp {src} $OUT".format(src = src),
    ])

    # If this rule needs to be part of the versioned sub-tree of it's
    # consumer, use a `cxx_genrule` which propagates versions (e.g. this
    # is useful for cases like `hsc2hs` which should use a dep tree which
    # is part of the same version sub-tree as the top-level binary).
    if propagate_versions:
        fb_native.cxx_genrule(**attrs)
    else:
        fb_native.genrule(**attrs)
