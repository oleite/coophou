#include "event_manager.h"

EventManager::EventManager()
{
}

QJsonObject EventManager::createPayload(OP_Node *node, OP_EventType reason, void *data)
{
    switch (reason)
    {
    case OP_EventType::OP_CHILD_CREATED:
        return onChildCreated(node, data);

    case OP_EventType::OP_NODE_DELETED:
        return onNodeDeleted(node, data);

    case OP_EventType::OP_NAME_CHANGED:
        return onNameChanged(node, data);

    case OP_EventType::OP_INPUT_REWIRED:
        return onInputRewired(node, data);

    case OP_EventType::OP_FLAG_CHANGED:
        return onFlagChanged(node, data);

    case OP_EventType::OP_PARM_CHANGED:
        return onParmChanged(node, data);

    case OP_EventType::OP_PARM_ANIMATED:
        return onParmAnimated(node, data);

    case OP_EventType::OP_CHPLAYBACK_CHANGED:
        return onChPlaybackChanged(node, data);

    case OP_EventType::OP_SPAREPARM_MODIFIED:
        return onSpareParmModified(node, data);

    case OP_EventType::OP_MULTIPARM_MODIFIED:
        return onMultiParmModified(node, data);

    default:
        return {};
    }
}

QJsonObject EventManager::onChildCreated(OP_Node *node, void *data)
{
    if (!node || !data)
        return {};

    auto *child = static_cast<OP_Node *>(data);

    UT_String parentPath;
    UT_String childPath;

    node->getFullPath(parentPath);
    child->getFullPath(childPath);

    const QString childPathString = QString::fromUtf8(childPath.c_str());
    const QString childName = childPathString.section('/', -1);

    return {
        {"event", "child_created"},
        {"parent_path", QString::fromUtf8(parentPath.c_str())},
        {"child_name", childName},
    };
}

QJsonObject EventManager::onNodeDeleted(OP_Node *node, void *data)
{
    return {};
}

QJsonObject EventManager::onNameChanged(OP_Node *node, void *data)
{
    return {};
}

QJsonObject EventManager::onInputRewired(OP_Node *node, void *data)
{
    return {};
}

QJsonObject EventManager::onFlagChanged(OP_Node *node, void *data)
{
    return {};
}

QJsonObject EventManager::onParmChanged(OP_Node *node, void *data)
{
    return {};
}
QJsonObject EventManager::onParmAnimated(OP_Node *node, void *data)
{
    return {};
}

QJsonObject EventManager::onChPlaybackChanged(OP_Node *node, void *data)
{
    return {};
}
QJsonObject EventManager::onSpareParmModified(OP_Node *node, void *data)
{
    return {};
}

QJsonObject EventManager::onMultiParmModified(OP_Node *node, void *data)
{
    return {};
}
