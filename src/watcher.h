#pragma once

#include <OP/OP_Node.h>
#include <OP/OP_Value.h>

class Watcher
{
public:
    static bool start();
    static bool stop();

private:
    static void globalOpChangedHook(OP_Node *node, OP_EventType reason, void *data, void *cbdata);
};
