"""
Various helper methods for constructing java_* rules
"""

_DEPS_TO_PROCESSORS = {
    "//third-party-java/org.immutables:value": "org.immutables.processor.ProxyProcessor",
    "//third-party-java/org.openjdk.jmh:jmh-generator-annprocess": "org.openjdk.jmh.generators.BenchmarkProcessor",
    "//third-party-java/org.projectlombok:lombok": "lombok.launch.AnnotationProcessorHider$AnnotationProcessor",
    "//third-party-java/0-DONT-USE/org.projectlombok.1.16.10:lombok": "lombok.launch.AnnotationProcessorHider$AnnotationProcessor",
}

def _get_extra_annotation_processors_and_deps(*dep_lists):
    """
    Gets any additional annotation processors and dependencies that are needed to make those processors work

    Args:
        *dep_lists: A list of the various types of dependencies to examine for
                   presence of annotation processors. e.g. exported_deps and
                   deps might be passed in.

    Returns:
        A tuple of two elements
        - A list of annotation processors to add to the annotation_processors
          attribute.
        - A list of lists of found dependencies to needed to utilize the
          specified annotation processors. These should be added to the
          `annotation_processor_deps` property of a rule.
    """

    annotation_processors = []
    annotation_processor_deps = []

    for dep, processor in _DEPS_TO_PROCESSORS.items():
        for deps in dep_lists:
            if dep in deps:
                annotation_processors.append(processor)
                annotation_processor_deps.append(dep)
                break

    return (annotation_processors, annotation_processor_deps)

def _duplicate_finder(name, buck_target, exclude_regexes, visibility):
    """
    Creates a genrule that will run a utility to see if duplicate classes exist in a jar

    Args:
        name: The name of the genrule to create
        buck_target: The full buck target that should be inspected by the
                     duplicate finder
        exclude_regexes: A list of regexes that should be ignored by the duplicate
                         class finder. Single quotes are not allowed.
        visibility: The visibility of this rule.
    """
    regex_args = []
    for regex in exclude_regexes:
        if "'" in regex:
            fail("single quote not allowed in duplicate_finder regexes. Got " + regex)
        regex_args.append("'%s'" % regex)

    # TODO(T22498401): java-swift Constants causes duplicate classes
    regex_args.append("'.*.Constants.class'")

    # TODO(T22498405): logging impl libraries cause duplicate classes
    regex_args.append("'org/apache/log4j/.*'")

    # Java 9 may include module-info.class in a module
    regex_args.append("'module-info\\.class'")

    # This class is in both jasper-runtime and jasper-compiler, but they
    # are identical and the duplication is harmless.
    regex_args.append("'org/apache/jasper/compiler/Localizer\\.class'")

    # Those classes are in both powermock-api-mockito-common and
    # powermock-api-mockito2, and the latter depends on the former. They
    # are identical and the duplication is harmless.
    regex_args.append("'org/powermock/api/mockito/expectation/With(out)?ExpectedArguments\\.class'")

    # These classes are in both jline v2 and hawtjni.  Releases of jline v3
    # do not have these classes, but v2 and v3 are incompatible, so we can't
    # remap v2 to v3.
    # These classes are identical between jline v2 and hawtjni, and harmless.
    regex_args.append("'org/fusesource/hawtjni/runtime/Library\\.class'")
    regex_args.append("'org/fusesource/hawtjni/runtime/PointerMath\\.class'")
    regex_args.append("'org/fusesource/hawtjni/runtime/JNIEnv\\.class'")
    regex_args.append("'org/fusesource/hawtjni/runtime/Callback\\.class'")

    native.genrule(
        name = name,
        visibility = visibility,
        out = "success.txt",
        cmd = (
            "$(exe //tools/build/buck/java/duplicate_finder:main) " +
            "--output-file $OUT " +
            "--classpath \"$(classpath {})\" " +
            "--link-to-docs https://fburl.com/duplicate_finder " +
            " ".join(regex_args)
        ).format(buck_target),
        type = "duplicate_finder",
    )

def _maven_publisher_rules(
        pom_properties_name,
        pom_xml_name,
        sources_jar_name,
        srcs,
        resources_root,
        buck_target,
        group_id,
        artifact_id,
        version_prefix,
        visibility):
    """
    Creates the rules for maven_publisher to work.

    This creates a set of rules that create a:
        pom.properties file
        pom.xml file
        source jar

    The version information is controlled by maven_publisher.idl_import_version

    Args:
        pom_properties_name: The name to use for the genrule to create pom.properties
        pom_xml_name: The name to use for the genrule that creates pom.xml
        sources_jar_name: The name to use for the genrule that creates a source jar
        srcs: A list of srcs to use for creating a source jar
        resources_root: The directory to stick pom.properties into. This is
                        necessary because the pom tooling expects a directory
                        called META-INF to exist, and we have to munge things
                        under the hood
        buck_target: The target for the original rule. Used to gather classpath
                     information and other details.
        group_id: The group id for the artifact
        artifact_id: The artifact id for the artifact
        version_prefix: If provided, the version number to use in the artifact.
                        Must be in the form of \d+\.\d+, or None
        visibility: The visibility to use on various genrules that are created
    """
    out_dir = "{}/META-INF/maven/{}/{}".format(resources_root, group_id, artifact_id)
    is_idl_import = (group_id == "com.facebook.thrift")
    skip_flag = "--skip-circular-dependency-check" if is_idl_import else ""
    if is_idl_import:
        version = native.read_config("maven_publisher", "idl_import_version", "1.0-SNAPSHOT")
    else:
        suffix = native.read_config("maven_publisher", "version_suffix")
        if version_prefix == None:
            version = suffix or "0.0-SNAPSHOT"
        else:
            if not _is_valid_version_prefix(version_prefix):
                fail("version prefix must match " + pattern)
            version = version_prefix + "-" + (suffix or "SNAPSHOT")
    properties = [
        "groupId=" + group_id,
        "artifactId=" + artifact_id,
        "version=" + version,
    ]

    native.genrule(
        name = pom_properties_name,
        visibility = visibility,
        out = out_dir + "/pom.properties",
        cmd = "mkdir -p \"\\$(dirname $OUT)\" && cat > $OUT <<'EOF'\n{}\nEOF".format("\n".join(properties)),
        type = "maven_publisher_properties",
    )

    native.genrule(
        name = pom_xml_name,
        visibility = visibility,
        out = "pom.xml",
        cmd = (
            "$(exe //tools/build/buck/java/maven_publisher:pom_creator) " +
            "--pom-properties $(location :{}) " +
            "--output-file $OUT " +
            "--classpath $(classpath {}) " +
            "--link-to-docs https://fburl.com/maven_publisher " +
            "{}"
        ).format(pom_properties_name, buck_target, skip_flag).strip(),
        type = "maven_publisher_xml",
    )

    _package_sources(
        sources_jar_name,
        "sources.jar",
        srcs,
        "maven_publisher_sources",
        visibility,
    )

def _package_sources(name, out, srcs, rule_type, visibility):
    """
    Creates a genrule that generates a source jar from `srcs`

    Args:
        name: The name of the new genrule
        out: The name of the jar to create in the genrule
        srcs: A list of srcs to make available to the source-jar generator
        rule_type: The `type` attribute to pass to the genrule
        visibility: The visibility of the genrule
    """
    native.genrule(
        name = name,
        visibility = visibility,
        out = out,
        srcs = srcs,
        cmd = (
            "$(exe //tools/build/buck/java/maven_publisher:sources_jar_creator) " +
            "--output-file $OUT --src-dir $SRCDIR"
        ),
        type = rule_type,
    )

def _get_maven_publisher_labels_and_create_rules(
        name,
        srcs,
        resources_root,
        maven_coords,
        maven_publisher_enabled,
        maven_publisher_version_prefix,
        visibility):
    """
    Gets labels for maven_publisher, and creates maven publisher rules

    Args:
        name: The name of the original library rule
        srcs: The list of srcs to pass into _maven_publisher_rules
        resources_root: The resources_root to pass into _maven_publisher_rules
        maven_coords: The maven coordinates to use. If None, do not create any
                      publisher rules
        maven_publisher_enabled: Whether or not maven publisher is enabled.
                                 If not, do not create any genrules
        maven_publisher_version_prefix: The version prefix to pass to _maven_publisher_rules
        visibility: The visibility to use for various genrules

    Returns:
        A struct with `labels` that is a list of tags to add to rule, and
        `pom_properties_rule_name` which is either None, or the name of a rule
        that creates pom.properties.
    """

    if not maven_coords:
        return struct(labels = [], pom_properties_rule_name = None)

    coords_parts = maven_coords.split(":")
    if len(coords_parts) != 2:
        fail("Invalid maven coordinates provided. Expected group_id:artifact_id, got " + maven_coords)

    group_id = coords_parts[0]
    artifact_id = coords_parts[1]
    buck_target = "//{}:{}".format(native.package_name(), name)
    labels = [
        "groupId=" + group_id,
        "artifactId=" + artifact_id,
        "buckRule=" + buck_target,
        "maven_coords_specified",
    ]
    if not maven_publisher_enabled:
        return struct(labels = labels, pom_properties_rule_name = None)

    labels.append("maven_publisher_enabled")
    pom_properties_name = "{}_maven_publisher_properties".format(name)
    pom_xml_name = "{}_maven_publisher_xml".format(name)
    sources_jar_name = "{}_maven_publisher_sources".format(name)
    _maven_publisher_rules(
        pom_properties_name,
        pom_xml_name,
        sources_jar_name,
        srcs,
        resources_root,
        buck_target,
        group_id,
        artifact_id,
        maven_publisher_version_prefix,
        visibility,
    )

    return struct(labels = labels, pom_properties_rule_name = pom_properties_name)

def _is_valid_version_prefix(version_prefix):
    parts = version_prefix.split(".")
    if len(parts) != 2:
        return False
    return all([part.isdigit() for part in parts])

java_common = struct(
    duplicate_finder = _duplicate_finder,
    get_extra_annotation_processors_and_deps = _get_extra_annotation_processors_and_deps,
    get_maven_publisher_labels_and_create_rules = _get_maven_publisher_labels_and_create_rules,
)
