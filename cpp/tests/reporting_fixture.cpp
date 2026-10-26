// Intentionally mixed outcomes for Python reporting integration tests only.
// This optional executable is never registered with CTest.
#include <gtest/gtest.h>

TEST(ReportingFixture, Passing) {
    EXPECT_EQ(2 + 2, 4);
}

TEST(ReportingFixture, Failing) {
    ADD_FAILURE() << "Intentional reporting fixture failure: expected < 5 & safe";
}

TEST(ReportingFixture, Skipped) {
    GTEST_SKIP() << "Intentional integration skip";
}

TEST(ReportingFixture, DISABLED_NotRun) {
    FAIL() << "Disabled fixture must not run";
}
