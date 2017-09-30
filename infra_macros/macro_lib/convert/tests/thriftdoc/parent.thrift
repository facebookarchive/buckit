include "tools/build/buck/infra_macros/macro_lib/convert/tests/thriftdoc/leaf1.thrift"
include "tools/build/buck/infra_macros/macro_lib/convert/tests/thriftdoc/leaf2.thrift"

namespace py parent

/** @should first.leaf <= second.leaf */
struct Parent {
  1: leaf1.Leaf1 first
  2: leaf2.Leaf2 second
}
