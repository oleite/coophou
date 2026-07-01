#pragma once

#include <array>       
#include <functional>

#include <OP/OP_Value.h>
#include <OP/OP_Node.h>
#include <QtCore/QJsonObject>

class EventManager
{
public:
    EventManager();

    QJsonObject createPayload(OP_Node *node, OP_EventType reason, void *data);

private:
    QJsonObject onChildCreated(OP_Node *node, void *data);
    QJsonObject onNodeDeleted(OP_Node *node, void *data);
    QJsonObject onNameChanged(OP_Node *node, void *data);
    QJsonObject onInputRewired(OP_Node *node, void *data);
    QJsonObject onFlagChanged(OP_Node *node, void *data);
    QJsonObject onParmChanged(OP_Node *node, void *data);
    QJsonObject onParmAnimated(OP_Node *node, void *data);
    QJsonObject onChPlaybackChanged(OP_Node *node, void *data);
    QJsonObject onSpareParmModified(OP_Node *node, void *data);
    QJsonObject onMultiParmModified(OP_Node *node, void *data);
};