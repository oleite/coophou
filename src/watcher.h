#pragma once

#include <cstdint>

#include <OP/OP_Director.h>
#include <OP/OP_Node.h>
#include <OP/OP_Value.h>
#include <QtCore/QJsonObject>
#include <QtCore/QString>

class Watcher
{
public:
    static bool start();
    static bool stop();
    static bool isStarted();
    static std::int64_t observationCount();
    static std::int64_t sceneGeneration();

private:
    static void globalOpChangedHook(
        OP_Node *node,
        OP_EventType reason,
        void *data,
        void *cbdata);
    static void directorEventHook(OP_Director::EventType type, void *cbdata);
    static void writeObservation(const QJsonObject &record);
    static void flushObservations();
    static QString lifecycleEventName(OP_Director::EventType type);
};
