#!/usr/bin/env python2
'''
DO NOT DEPEND ON THIS TARGET DIRECTLY, except through the `features=` field
of `image_feature` or `image_layer`.  A direct dependency will not work the
way you expect, and you will end up with incorrect behavior.

## Composing images using `image_feature`

When building regular binaries, one will often link multiple independent
libraries that know nothing about one another. Each of those libraries
may depend on other libraries, and so forth.

This ability to **compose** largely uncoupled pieces of functionality is
an essential tool of a software engineer.

`image_feature` is a way of bringing the same sort of compositionality to
building filesystem images.

A feature specifies a set of **items**, each of which describes some aspect
**of a desired end state** for the filesystem.  Examples:
 - A directory must exist.
 - A taraball must be extracted at this location.
 - An RPM must be installed, or must be **ABSENT** from the filesystem.
 - Other `image_feature` that must be installed.

Importantly, the specifications of an `image_feature` are not ordered. They
are not commands or instructions.  Rather, they are a declaration of what
should be true. You can think of a feature as a thunk or callback.

In order to convert the declaration into action, one makes an `image_layer`.
Read that target's docblock for more info, but in essence, that will:
 - specify the initial state of the filesystem (aka the parent layer)
 - verify that the features can be applied correctly -- that dependencies
   are satisfied, that no features provide duplicate paths, etc.
 - install the features in dependency order,
 - capture the resulting filesystem, ready to be used as another parent layer.
'''
import collections
import json

from pipes import quote


# Hack to make internal Buck macros flake8-clean until we switch to buildozer.
def import_macro_lib(path):
    global _import_macro_lib__imported
    include_defs('{}/{}.py'.format(  # noqa: F821
        read_config('fbcode', 'macro_lib', '//macro_lib'), path  # noqa: F821
    ), '_import_macro_lib__imported')
    ret = _import_macro_lib__imported
    del _import_macro_lib__imported  # Keep the global namespace clean
    return ret

load("@fbcode_macros//build_defs:target_utils.bzl", "target_utils")

base = import_macro_lib('convert/base')
Rule = import_macro_lib('rule').Rule
parse_target = target_utils.parse_target


# ## Why are `image_feature`s forbidden as dependencies?
#
# The long target suffix below exists to discourage people from directly
# depending on `image_feature`s.  They are not real targets, but rather a
# language feature to make it easy to compose independent features of
# container images.
#
# A normal Buck target is supposed to produce an output that completely
# encapsulates the outputs of all of its dependencies (think static
# linking), so in deciding whether to build a file or use a cached output,
# Buck will only consider direct dependencies, not transitive ones.
#
# In contrast, `image_feature` simply serializes its keyword arguments to
# JSON.  It does not consume the outputs of its dependencies -- it reads
# neither regular target outputs, nor the JSONs of the `image_feature`s, on
# which it depends.
#
# By violating Buck semantics, `image_features` creates two problems for
# targets that might depend on them:
#
# 1) Buck will build any target depending on an `image_feature` immediately
#    upon ensuring that its JSON output exists in the output tree.  It is
#    possible that the output tree lacks, or contains stale versions of, the
#    outputs of the targets, on which the `image_feature` itself depends.
#
# 2) If the output of a dependency of an `image_feature` changes, this will
#    cause the feature to rebuild.  However, the output of the `image_feature`
#    will remain unchanged, and so any target depending on the `image_feature`
#    will **NOT** get rebuilt.
#
# For these reasons, special logic is required to correctly depend on
# `image_feature` targets.  At the moment, we are not aware of any reason to
# have direct access to the `image_feature` JSON outputs in any case.  Most
# users will want to depend on build artifacts that are downstream of
# `image_feature`, like `image_layer`.
#
# Maintainers of this code: please change this string at will, **without**
# searching the codebase for people who might be referring to it.  They have
# seen this blob, and they have agreed to have their code broken without
# warning.  Do not incentivize hacky engineering practices by "being nice."
# (Caveat: don't change it daily to avoid forcing excessive rebuilds.)
DO_NOT_DEPEND_ON_FEATURES_SUFFIX = (
    '_IF_YOU_REFER_TO_THIS_RULE_YOUR_DEPENDENCIES_WILL_BE_BROKEN_'
    'SO_DO_NOT_DO_THIS_EVER_PLEASE_KTHXBAI'
)


class TargetTagger(object):
    '''

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

    '''

    def __init__(self, normalize_target):
        self.normalize_target = normalize_target
        self.targets = []

    def tag_target(self, target):
        target = self.normalize_target(target)
        self.targets.append(target)
        return {'__BUCK_TARGET': target}

    def tag_required_target_key(self, d, target_key):
        assert target_key in d, (
            '{} must contain the key {}'.format(d, target_key)
        )
        d[target_key] = self.tag_target(d[target_key])


class ImageFeatureConverter(base.Converter):
    'Does not make a layer, simply records what needs to be done. A thunk.'

    def get_fbconfig_rule_type(self):
        return 'image_feature'

    def _normalize_make_dirs(self, make_dirs):
        if make_dirs is None:
            return []

        normalized = []
        for d in make_dirs:
            if isinstance(d, basestring):
                d = {'into_dir': '/', 'path_to_make': d}
            elif isinstance(d, tuple):
                assert len(d) == 2, (
                    'make_dirs tuples must have the form: '
                    '(working_dir, dirs_to_create)'
                )
                d = {'into_dir': d[0], 'path_to_make': d[1]}
            normalized.append(d)
        return normalized

    def _normalize_copy_deps(self, target_tagger, copy_deps):
        if copy_deps is None:
            return []

        normalized = []
        for d in copy_deps:
            if isinstance(d, tuple):
                assert len(d) == 2, (
                    'copy_deps tuples must have the form: '
                    '(target_to_copy, destination_dir_or_path)'
                )
                d = {'source': d[0], 'dest': d[1]}
            target_tagger.tag_required_target_key(d, 'source')
            normalized.append(d)
        return normalized

    def _normalize_tarballs(self, target_tagger, tarballs):
        if tarballs is None:
            return []

        normalized = []
        for t in tarballs:
            if isinstance(t, tuple):
                assert len(t) == 2, (
                    'tarballs tuples must have the form: '
                    '(tarball_target, destination_dir)'
                )
                t = {'tarball': t[0], 'into_dir': t[1]}
            target_tagger.tag_required_target_key(t, 'tarball')
            normalized.append(t)
        return normalized

    def convert(
        self,
        base_path,
        name=None,
        # An iterable of directories to make in the image --
        #  - `into_dir` is a image-absolute path, inside which
        #    we should create more directories. It must be created by
        #    another `image_feature` item.
        #  - `path_to_make` is a path relative to `into_dir`, which will be
        #    created.
        # Order is not significant, the image compiler will sort the actions
        # automatically.  Supported formats for the items:
        #  - string: 'image_absolute/path/to/make'
        #  - tuple: ('into/image_absolute/dir', 'path/to/make')
        #  - dict: {'into_dir': '...', 'path_to_make': '...'}
        make_dirs=None,
        # An iterable of targets to copy into the image --
        #  - `source` is the Buck target to copy,
        #  - `dest` is an image-absolute path. We follow the `rsync`
        #     convention -- if `dest` ends with a slash, the copy will be at
        #     `dest/output filename of source`.  Otherwise, `dest` is a full
        #     path, including a new filename for the target's output.  The
        #     directory of `dest` must get created by another
        #     `image_feature` item.
        # Order is not signficant, the image compiler will sort the actions
        # automatically.  Supported item formats:
        #  - tuple: ('//target/to/copy', 'image_absolute/dir')
        #  - dict: {'source': '//target/to/copy', 'dest': 'image_absolute/dir'}
        copy_deps=None,
        # An iterable of tarballs to extract inside the image --
        #  - `tarball` is a Buck target that outputs a tarball. You may
        #    want to look at `export_file`, `buck_genrule`, or `custom_rule`.
        #  - `dest` is an image-absolute path to a directory that gets
        #    created by another `image_feature` item.
        # Order is not signficant, the image compiler will sort the actions
        # automatically.  Supported item formats:
        #  - tuple: ('//target/tarball/to_extract', 'image_absolute/dir')
        #  - dict: {'tarball': '//toextract', 'into_dir': 'image_absolute/dir'}
        tarballs=None,
        # Iterable of `image_feature` targets that are included by this one.
        # Order is not significant.
        features=None,
        visibility=None,
    ):

        def normalize_target(target):
            parsed = parse_target(
                target,
                # $(query_targets ...) omits the current repo/cell name
                default_repo='',
                default_base_path=base_path,
            )
            return target_utils.to_label(
                repo=parsed.repo,
                path=parsed.base_path,
                name=parsed.name,
            )

        # (1) Normalizes & annotates Buck target names so that they can be
        #     automatically enumerated from our JSON output.
        # (2) Builds a list of targets so that this converter can tell Buck
        #     that the `image_feature` depends on it.
        target_tagger = TargetTagger(normalize_target)
        out_dict = {
            # Omit the ugly suffix here since this is meant only for
            # humans to read while debugging.
            'target': normalize_target(':' + name),
            'make_dirs': self._normalize_make_dirs(make_dirs),
            'copy_files':
                self._normalize_copy_deps(target_tagger, copy_deps),
            'tarballs': self._normalize_tarballs(target_tagger, tarballs),
            'features': [
                target_tagger.tag_target(f + DO_NOT_DEPEND_ON_FEATURES_SUFFIX)
                    for f in features
            ] if features else [],
        }

        # Serialize the arguments and defer our computation until
        # build-time.  This allows us to automatically infer what is
        # provided by RPMs & TARs, and makes the implementation easier.
        #
        # Caveat: if the serialization exceeds the kernel's MAX_ARG_STRLEN,
        # this will fail (128KB on the Linux system I checked).
        #
        # TODO: Print friendlier error messages on user error.
        return [Rule('genrule', collections.OrderedDict(
            # The constant declaration explains the reason for the name change.
            name=name + DO_NOT_DEPEND_ON_FEATURES_SUFFIX,
            out=name + '.json',
            type=self.get_fbconfig_rule_type(),  # For queries
            cmd='echo {deps} > /dev/null; echo {out} > "$OUT"'.format(
                # We need to tell Buck that we depend on these targets, so
                # that `image_layer` can use `deps()` to discover its
                # transitive dependencies.
                #
                # This is a little hacky, because we are forcing these
                # targets to be built or fetched from cache even though we
                # don't actually use them until a later build step --- which
                # might be on a different host.
                #
                # Future: Talk with the Buck team to see if we can eliminate
                # this inefficiency.
                deps=' '.join(
                    '$(location {})'.format(t)
                        for t in sorted(target_tagger.targets)
                ),
                out=quote(json.dumps(out_dict, sort_keys=True)),
            ),
            visibility=visibility,
        ))]
