#pragma once

#include <array>       
#include <functional>

#include <OP/OP_Value.h>
#include <QtCore/QJsonObject>

class EventManager
{
public:
    EventManager();

    QJsonObject createPayload(OP_EventType type, const void *data);

private:
    using HandlerFunc = std::function<QJsonObject(const void *)>;
    std::array<HandlerFunc, static_cast<size_t>(OP_EventType::OP_EVENT_TYPE_COUNT)> eventHandlers;

    QJsonObject onChildCreated(const void *data);
    QJsonObject onNodeDeleted(const void *data);
    QJsonObject onNameChanged(const void *data);
    QJsonObject onInputRewired(const void *data);
    QJsonObject onFlagChanged(const void *data);
    QJsonObject onParmChanged(const void *data);
    QJsonObject onParmAnimated(const void *data);
    QJsonObject onChPlaybackChanged(const void *data);
    QJsonObject onSpareParmModified(const void *data);
    QJsonObject onMultiParmModified(const void *data);
};