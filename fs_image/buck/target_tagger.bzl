"""
Our continuous integration system might run different build steps in
different sandboxes, so the intermediate outputs of `image_feature`s
must be cacheable by Buck.  In particular, they must not contain
absolute paths to targets.

However, to build a dependent `image_layer`, we will need to invoke the
image compiler with the absolute paths of the outputs that will comprise
the image.

Therefore, we need to (a) record all the targets, for which the image
compiler will need absolute paths, and (b) resolve them only in the
build step that invokes the compiler.

This tagging scheme makes it possible to find ALL such targets in the
output of `image_feature` by simply traversing the JSON structure.  This
seems more flexible and less messy than maintaining a look-aside list of
targets whose paths the `image_layer` converter would need to resolve.
"""

load(
    "@fbcode_macros//build_defs/lib:target_utils.bzl",
    "target_utils",
)
load(":image_source.bzl", "image_source")

_TargetTaggerInfo = provider(fields = ["targets"])

def new_target_tagger():
    return _TargetTaggerInfo(targets = {})

def normalize_target(target):
    parsed = target_utils.parse_target(
        target,
        # $(query_targets ...) omits the current repo/cell name
        default_repo = "",
        default_base_path = native.package_name(),
    )
    return target_utils.to_label(
        repo = parsed.repo,
        path = parsed.base_path,
        name = parsed.name,
    )

def tag_target(target_tagger, target):
    target = normalize_target(target)
    target_tagger.targets[target] = 1  # Use a dict, since a target may recur
    return {"__BUCK_TARGET": target}

def tag_required_target_key(tagger, d, target_key):
    if target_key not in d:
        fail(
            "{} must contain the key {}".format(d, target_key),
        )
    d[target_key] = tag_target(tagger, d[target_key])

def image_source_as_target_tagged_dict(target_tagger, user_source):
    src = image_source(user_source)._asdict()
    tag_required_target_key(
        target_tagger,
        src,
        "layer" if src["layer"] else "source",
    )
    return src

def target_tagger_to_feature(target_tagger, items, extra_deps):
    return struct(
        items = items,
        deps = target_tagger.targets.keys() + extra_deps,
    )
