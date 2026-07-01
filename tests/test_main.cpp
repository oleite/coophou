#include <gtest/gtest.h>

#include <UT/UT_Main.h>

static int
testMain(int argc, char *argv[])
{
    ::testing::InitGoogleTest(&argc, argv);
    return RUN_ALL_TESTS();
}

UT_MAIN(testMain)