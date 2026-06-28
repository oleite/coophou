#include "event_manager.h"

#define REGISTER_EVENT(enumVal, func) \
    eventHandlers[static_cast<size_t>(OP_EventType::enumVal)] = [this](const void *d) { return func(d); };

EventManager::EventManager()
{
    REGISTER_EVENT(OP_CHILD_CREATED, onChildCreated)
    REGISTER_EVENT(OP_NODE_DELETED, onNodeDeleted)
    REGISTER_EVENT(OP_NAME_CHANGED, onNameChanged)
    REGISTER_EVENT(OP_INPUT_REWIRED, onInputRewired)
    REGISTER_EVENT(OP_FLAG_CHANGED, onFlagChanged)
    REGISTER_EVENT(OP_PARM_CHANGED, onParmChanged)
    REGISTER_EVENT(OP_PARM_ANIMATED, onParmAnimated)
    REGISTER_EVENT(OP_CHPLAYBACK_CHANGED, onChPlaybackChanged)
    REGISTER_EVENT(OP_SPAREPARM_MODIFIED, onSpareParmModified)
    REGISTER_EVENT(OP_MULTIPARM_MODIFIED, onMultiParmModified)
}

#undef REGISTER_EVENT

QJsonObject EventManager::createPayload(OP_EventType type, const void *data)
{
    size_t index = static_cast<size_t>(type);

    if (index >= eventHandlers.size() || !eventHandlers[index])
        return QJsonObject(); 

    return eventHandlers[index](data);
}

QJsonObject EventManager::onChildCreated(const void *data)
{
}

QJsonObject EventManager::onNodeDeleted(const void *data)
{
}

QJsonObject EventManager::onNameChanged(const void *data)
{
}

QJsonObject EventManager::onInputRewired(const void *data)
{
}

QJsonObject EventManager::onFlagChanged(const void *data)
{
}

QJsonObject EventManager::onParmChanged(const void *data)
{
}

QJsonObject EventManager::onParmAnimated(const void *data)
{
}

QJsonObject EventManager::onChPlaybackChanged(const void *data)
{
}

QJsonObject EventManager::onSpareParmModified(const void *data)
{
}

QJsonObject EventManager::onMultiParmModified(const void *data)
{
}
