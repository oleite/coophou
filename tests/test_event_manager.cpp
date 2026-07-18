#include "houdini_fixture.h"

#include "event_manager.h"
#include "watcher.h"

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
    EXPECT_TRUE(json.value("payload").isObject());
}

TEST_F(HoudiniFixture, UnknownEventIsRecordedSafely)
{
    OP_Network *obj = objectNetwork();

    ASSERT_NE(obj, nullptr);

    EventManager manager;

    QJsonObject json = manager.createPayload(
        obj,
        static_cast<OP_EventType>(999999),
        nullptr);

    EXPECT_EQ(jsonString(json, "event"), "UNKNOWN_EVENT");
    EXPECT_EQ(json.value("event_reason").toInt(), 999999);
    EXPECT_TRUE(json.value("payload").toObject().contains("data_semantics"));
}

TEST_F(HoudiniFixture, WatcherStartStopRestartIsIdempotent)
{
    ASSERT_TRUE(Watcher::start());
    ASSERT_TRUE(Watcher::start());
    EXPECT_TRUE(Watcher::isStarted());
    ASSERT_TRUE(Watcher::stop());
    ASSERT_TRUE(Watcher::stop());
    EXPECT_FALSE(Watcher::isStarted());
    ASSERT_TRUE(Watcher::start());
    ASSERT_TRUE(Watcher::stop());
}

namespace
{
int foreignCallbackCount = 0;

void foreignCallback(OP_Node *, OP_EventType, void *, void *)
{
    ++foreignCallbackCount;
}
}

TEST_F(HoudiniFixture, WatcherStopDoesNotRemoveForeignGlobalCallback)
{
    OP_Director *opDirector = OPgetDirector();
    ASSERT_NE(opDirector, nullptr);
    foreignCallbackCount = 0;
    opDirector->addGlobalOpChangedCallback(foreignCallback, nullptr);

    ASSERT_TRUE(Watcher::start());
    ASSERT_TRUE(Watcher::stop());
    OP_Node *node = createObjectNode("geo", "foreign_callback_probe");
    ASSERT_NE(node, nullptr);
    opDirector->globalOpChanged(node, OP_NAME_CHANGED, nullptr);

    EXPECT_GT(foreignCallbackCount, 0);
    opDirector->removeGlobalOpChangedCallback(foreignCallback, nullptr);
}
