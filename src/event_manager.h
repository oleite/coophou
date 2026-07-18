#pragma once

#include <cstdint>

#include <OP/OP_Node.h>
#include <OP/OP_Value.h>
#include <QtCore/QJsonObject>
#include <QtCore/QString>

struct ObservationContext
{
    QString adapter{"hdk"};
    QString scenario{"unspecified"};
    std::int64_t sceneGeneration{1};
    std::int64_t observation{1};
    int callbackDepth{1};
    QString transactionHint;
};

class EventManager
{
public:
    QJsonObject createObservation(
        OP_Node *node,
        OP_EventType reason,
        void *data,
        const ObservationContext &context) const;

    QJsonObject createLifecycleObservation(
        const QString &event,
        int eventReason,
        const ObservationContext &context) const;

    // Compatibility entry point retained for the original sketch tests.
    QJsonObject createPayload(OP_Node *node, OP_EventType reason, void *data) const;

private:
    static QString nodePath(const OP_Node *node);
    static QString entityId(const OP_Node *node);
    static QJsonObject baseObservation(const ObservationContext &context);
};
