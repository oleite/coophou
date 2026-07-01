#include "houdini_fixture.h"

#include <MGR/MGR_Node.h>
#include <OP/OP_Director.h>
#include <OP/OP_Network.h>
#include <OP/OP_Node.h>
#include <PI/PI_ResourceManager.h>

MOT_Director *HoudiniFixture::director = nullptr;

void
HoudiniFixture::SetUpTestSuite()
{
    ASSERT_EQ(director, nullptr);

    director = new MOT_Director("CoopHouTests");

    ASSERT_NE(director, nullptr);

    OPsetDirector(director);
    PIcreateResourceManager();
}

void
HoudiniFixture::TearDownTestSuite()
{
    //
    // Important:
    //
    // Do NOT delete director here.
    // Do NOT call OPsetDirector(nullptr) here.
    // Do NOT call resetForNewFile() here.
    //
    // Houdini owns a lot of global/static state once initialized.
    // Manually tearing it down from a gtest fixture can crash during process
    // shutdown, which is exactly what your log shows.
    //
    // The process is about to exit anyway, so letting the OS reclaim this is
    // safer for test executables.
    //
}

void
HoudiniFixture::SetUp()
{
    ASSERT_NE(director, nullptr);

    //
    // Reset before each test so every test starts from a clean scene.
    //
    // MOT_Director exposes resetForNewFile(), and this is the right place to
    // use it: before the test creates new nodes.
    //
    director->resetForNewFile();

    ASSERT_NE(objectNetwork(), nullptr);
}

void
HoudiniFixture::TearDown()
{
    //
    // Intentionally empty.
    //
    // Resetting in SetUp() is enough for isolation.
    // Avoid doing more Houdini cleanup after the test has finished, because
    // teardown order can be fragile with HDK globals.
    //
}

OP_Network *
HoudiniFixture::objectNetwork() const
{
    if (!director)
        return nullptr;

    return static_cast<OP_Network *>(director->getObjectManager());
}

OP_Node *
HoudiniFixture::createObjectNode(
    const char *typeName,
    const char *nodeName) const
{
    OP_Network *obj = objectNetwork();

    if (!obj)
    {
        ADD_FAILURE() << "Could not access /obj network.";
        return nullptr;
    }

    OP_Node *node = obj->createNode(
        typeName,
        nodeName,
        0,       // notify
        1,       // explicitly
        1,       // loadcontents
        nullptr, // aliased_scripted_op
        nullptr, // mat_icon_filename
        true     // exact_type
    );

    if (!node)
    {
        ADD_FAILURE()
            << "Could not create object node of type '"
            << typeName
            << "' named '"
            << nodeName
            << "'.";
    }

    return node;
}