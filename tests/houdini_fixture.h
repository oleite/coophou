#pragma once

#include <gtest/gtest.h>

#include <MOT/MOT_Director.h>

class OP_Network;
class OP_Node;

class HoudiniFixture : public ::testing::Test
{
protected:
    static void SetUpTestSuite();
    static void TearDownTestSuite();

    void SetUp() override;
    void TearDown() override;

    OP_Network *objectNetwork() const;

    OP_Node *createObjectNode(
        const char *typeName,
        const char *nodeName) const;

protected:
    static MOT_Director *director;
};