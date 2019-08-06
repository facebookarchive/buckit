// Copyright 2004-present Facebook. All Rights Reserved.

#include <gtest/gtest.h>
#include <stdlib.h>

using namespace ::testing;

TEST(ImageCppUnittest, TestContainer) {
  EXPECT_EQ(1, 1);

  ASSERT_STREQ("nobody", std::getenv("USER"));
}
