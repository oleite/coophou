#include "watcher.h"
#include "utils.h"

#include <iostream>

#include <OP/OP_Director.h>

bool Watcher::start()
{
    OP_Director *director = OPgetDirector();
    if (!director)
    {
        std::cout << "ERROR: OP_Director not available.";
        return false;
    }
    director->addGlobalOpChangedCallback(Watcher::globalOpChangedHook, nullptr);
    return true;
}

bool Watcher::stop()
{
    OP_Director *director = OPgetDirector();
    if (!director)
    {
        std::cout << "ERROR: OP_Director not available.";
        return false;
    }
    director->removeGlobalOpChangedCallback(Watcher::globalOpChangedHook, nullptr);
    return true;
}

void Watcher::globalOpChangedHook(OP_Node *node, OP_EventType reason, void *data, void *cbdata)
{
    if (!node)
        return;

    const char *eventName = OPeventToString(reason);
    if (!eventName)
        eventName = "UNKNOWN_EVENT";

    std::cout << Color::SAGE << "[E] " << eventName << " on " << node->getFullPath();

    if (data)
    {
        std::cout << " | Payload Data Pointer: " << data;

        // 3. Intelligently peek into the payload based on the event type
        if (reason == OP_CHILD_CREATED || reason == OP_CHILD_DELETED)
        {
            // For child events, data is an OP_Node*
            OP_Node *childNode = static_cast<OP_Node *>(data);
            std::cout << " (Child Node: " << childNode->getFullPath() << ")";
        }
        else if (reason == OP_PARM_CHANGED)
        {
            // For parameter changes, data is often passed as a raw integer token or index value.
            // We cast through intptr_t to safely read it without alignment/pointer-size truncation issues.
            intptr_t parmIndex = reinterpret_cast<intptr_t>(data);
            std::cout << " (Parm Index/Token ID: " << parmIndex << ")";
        }
    }
    else
    {
        std::cout << " | No Payload";
    }

    std::cout << Color::RESET << std::endl;
}
