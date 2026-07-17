#include "houdini_fixture.h"

#include "event_manager.h"
#include "watcher.cpp"

#include <OP/OP_Network.h>
#include <OP/OP_Node.h>
#include <QtCore/QJsonObject>
#include <UT/UT_String.h>

#include <string>

namespace
{
    std::string jsonString(const QJsonObject &json, const char *key)
    {
        return json.value(key).toString().toStdString();
    }

    std::string nodePath(OP_Node *node)
    {
        UT_String path;
        node->getFullPath(path);
        return path.c_str();
    }
}

TEST_F(HoudiniFixture, CanCreateObjectNodeWithoutHipFile)
{
    OP_Network *obj = objectNetwork();

    ASSERT_NE(obj, nullptr);

    OP_Node *geo = createObjectNode("geo", "geo_child");

    ASSERT_NE(geo, nullptr);

    EXPECT_EQ(nodePath(obj), "/obj");
    EXPECT_EQ(nodePath(geo), "/obj/geo_child");
}

TEST_F(HoudiniFixture, ChildCreatedPayloadUsesRealHoudiniNodes)
{
    OP_Network *obj = objectNetwork();

    ASSERT_NE(obj, nullptr);

    OP_Node *child = createObjectNode("geo", "geo_child");

    ASSERT_NE(child, nullptr);

    EventManager manager;

    QJsonObject json = manager.createPayload(
        obj,
        OP_EventType::OP_CHILD_CREATED,
        child);

    EXPECT_EQ(jsonString(json, "event"), "child_created");
    EXPECT_EQ(jsonString(json, "parent_path"), "/obj");
    EXPECT_EQ(jsonString(json, "child_name"), "geo_child");
}

TEST_F(HoudiniFixture, UnknownEventReturnsEmptyPayload)
{
    OP_Network *obj = objectNetwork();

    ASSERT_NE(obj, nullptr);

    EventManager manager;

    QJsonObject json = manager.createPayload(
        obj,
        static_cast<OP_EventType>(999999),
        nullptr);

    EXPECT_TRUE(json.isEmpty());
}

TEST_F(HoudiniFixture, SanityCheck)
{

    OP_Network *obj = objectNetwork();

    ASSERT_NE(obj, nullptr);

    ASSERT_TRUE(Watcher::start());


    OP_Node *child = createObjectNode("geo", "geo_child");

    ASSERT_NE(child, nullptr);

}