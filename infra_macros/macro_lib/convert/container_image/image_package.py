#!/usr/bin/env python2
'''
The `image_package` rule serializes an `image_layer` target into one or more
files, as described by the specified `format`.
'''
import collections
import os.path


# Hack to make internal Buck macros flake8-clean until we switch to buildozer.
def import_macro_lib(path):
    global _import_macro_lib__imported
    include_defs('{}/{}.py'.format(  # noqa: F821
        read_config('fbcode', 'macro_lib', '//macro_lib'), path  # noqa: F821
    ), '_import_macro_lib__imported')
    ret = _import_macro_lib__imported
    del _import_macro_lib__imported  # Keep the global namespace clean
    return ret


load(":image_utils.bzl", "image_utils")

base = import_macro_lib('convert/base')
Rule = import_macro_lib('rule').Rule


class ImagePackageConverter(base.Converter):

    def get_fbconfig_rule_type(self):
        return 'image_package'

    def convert(
        self,
        base_path,
        # Standard naming: <image_layer_name>.<package_format>.
        #
        # For supported formats, see `--format` here:
        #
        #     buck run :package-image -- --help
        #
        # If you are packaging an `image_layer` from a different TARGETS
        # file, then pass `layer =`, and specify whatever name you want.
        name=None,
        # If possible, do not set this. Prefer the standard naming convention.
        layer=None,
        visibility=None,
    ):
        local_layer_rule, format = os.path.splitext(name)
        assert format.startswith('.'), name
        format = format[1:]
        assert '\0' not in format and '/' not in format, repr(name)
        if layer is None:
            layer = ':' + local_layer_rule
        return [Rule('genrule', collections.OrderedDict(
            name=name,
            out=name,
            type=self.get_fbconfig_rule_type(),  # For queries
            bash=image_utils.wrap_bash_build_in_common_boilerplate(
                self_dependency=image_utils.BASE_DIR + ':image_package_macro',
                # We don't need to hold any subvolume lock because we trust
                # that (a) Buck will keep our input JSON alive, and (b) the
                # existence of the JSON will keep the refcount above 1,
                # preventing any concurrent image builds from
                # garbage-collecting the subvolumes.
                bash='''
                # NB: Using the `location` macro instead of `exe` would
                # cause failures to rebuild on changes to `package-image` in
                # `@mode/dev`, where the rule's "output" is just a symlink.
                # On the other hand, `exe` does not expand to a single file,
                # but rather to a shell snippet, so it's not always what one
                # wants either.
                $(exe {base_dir}:package-image) \
                  --subvolumes-dir "$subvolumes_dir" \
                  --subvolume-json $(query_outputs {layer}) \
                  --format {format} \
                  --output-path "$OUT"
                '''.format(
                    format=format,
                    base_dir=image_utils.BASE_DIR,
                    layer=layer,
                    # Future: When adding support for incremental outputs,
                    # use something like this to obtain all the ancestors,
                    # so that the packager can verify that the specified
                    # base for the incremental computation is indeed an
                    # ancestor:
                    #     --ancestor-jsons $(query_outputs "attrfilter( \
                    #       type, image_layer, deps({layer}))")
                    # This could replace `--subvolume-json`, though also
                    # specifying it would make `get_subvolume_on_disk_stack`
                    # more efficient.
                ),
                volume_min_free_bytes=0,  # We are not writing to the volume.
                log_description="{}(name={})".format(
                    self.get_fbconfig_rule_type(), name
                ),
            ),
            visibility=visibility,
        ))]
