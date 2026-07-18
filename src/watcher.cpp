#include "watcher.h"

#include "event_manager.h"
#include "native_adapter.h"

#include <array>
#include <deque>
#include <iostream>
#include <mutex>

#include <QtCore/QFile>
#include <QtCore/QJsonDocument>
#include <QtCore/QTextStream>
#include <QtCore/QtGlobal>

namespace
{
std::mutex stateMutex;
bool registered = false;
bool probeEnabled = false;
std::int64_t localObservation = 0;
std::int64_t currentSceneGeneration = 1;
int callbackDepth = 0;
bool loadInProgress = false;
bool loadGenerationAdvanced = false;
QString scenario;
QString tracePath;
QFile traceFile;
EventManager serializer;
std::deque<QByteArray> pendingLines;
std::int64_t droppedObservations = 0;
constexpr std::size_t MAX_PENDING_LINES = 16384;

constexpr std::array<OP_Director::EventType, OP_Director::NUM_NETWORK_EVENT_TYPES>
    directorEventTypes = {
        OP_Director::BEGIN_CLEAR_NETWORK,
        OP_Director::END_CLEAR_NETWORK,
        OP_Director::BEGIN_LOAD_NETWORK,
        OP_Director::END_LOAD_NETWORK,
        OP_Director::BEGIN_MERGE_NETWORK,
        OP_Director::END_MERGE_NETWORK,
        OP_Director::BEGIN_SAVE_NETWORK,
        OP_Director::END_SAVE_NETWORK,
    };

ObservationContext nextContext(const QString &transactionHint = {})
{
    ObservationContext context;
    context.scenario = scenario;
    context.sceneGeneration = currentSceneGeneration;
    context.observation = ++localObservation;
    context.callbackDepth = callbackDepth;
    context.transactionHint = transactionHint;
    return context;
}
}

bool
Watcher::start()
{
    std::lock_guard<std::mutex> lock(stateMutex);
    if (registered)
        return true;

    OP_Director *director = OPgetDirector();
    if (!director)
    {
        std::cerr << "coophou probe: OP_Director not available." << std::endl;
        return false;
    }

    scenario = qEnvironmentVariable("COOPHOU_PROBE_SCENARIO", "unspecified");
    tracePath = qEnvironmentVariable("COOPHOU_PROBE_TRACE");
    probeEnabled = !tracePath.isEmpty()
        || qEnvironmentVariableIntValue("COOPHOU_PROBE_STDOUT") == 1;
    if (!tracePath.isEmpty())
    {
        traceFile.setFileName(tracePath);
        if (!traceFile.open(QIODevice::WriteOnly | QIODevice::Append | QIODevice::Text))
        {
            std::cerr << "coophou probe: could not open trace file."
                      << std::endl;
            return false;
        }
    }

    director->addGlobalOpChangedCallback(Watcher::globalOpChangedHook, nullptr);
    for (OP_Director::EventType type : directorEventTypes)
        director->addEventCallback(type, Watcher::directorEventHook, nullptr);
    registered = true;
    return true;
}

bool
Watcher::stop()
{
    std::lock_guard<std::mutex> lock(stateMutex);
    if (!registered)
        return true;

    OP_Director *director = OPgetDirector();
    if (!director)
    {
        std::cerr << "coophou probe: OP_Director unavailable during stop."
                  << std::endl;
        return false;
    }

    director->removeGlobalOpChangedCallback(Watcher::globalOpChangedHook, nullptr);
    for (OP_Director::EventType type : directorEventTypes)
        director->removeEventCallback(type, Watcher::directorEventHook, nullptr);
    registered = false;
    if (probeEnabled)
        flushObservations();
    else
        pendingLines.clear();
    probeEnabled = false;
    if (traceFile.isOpen())
        traceFile.close();
    return true;
}

bool
Watcher::isStarted()
{
    std::lock_guard<std::mutex> lock(stateMutex);
    return registered;
}

std::int64_t
Watcher::observationCount()
{
    std::lock_guard<std::mutex> lock(stateMutex);
    return localObservation;
}

std::int64_t
Watcher::sceneGeneration()
{
    std::lock_guard<std::mutex> lock(stateMutex);
    return currentSceneGeneration;
}

void
Watcher::writeObservation(const QJsonObject &record)
{
    const QByteArray line = QJsonDocument(record).toJson(QJsonDocument::Compact) + '\n';
    if (pendingLines.size() >= MAX_PENDING_LINES)
    {
        pendingLines.pop_front();
        ++droppedObservations;
    }
    pendingLines.push_back(line);
}

void
Watcher::flushObservations()
{
    while (!pendingLines.empty())
    {
        const QByteArray line = std::move(pendingLines.front());
        pendingLines.pop_front();
        if (traceFile.isOpen())
            traceFile.write(line);
        else if (qEnvironmentVariableIntValue("COOPHOU_PROBE_STDOUT") == 1)
            std::cout << line.constData();
    }
    if (traceFile.isOpen())
        traceFile.flush();
    if (droppedObservations)
        std::cerr << "coophou probe: dropped " << droppedObservations
                  << " observations because the bounded native queue filled."
                  << std::endl;
}

void
Watcher::globalOpChangedHook(
    OP_Node *node,
    OP_EventType reason,
    void *data,
    void *cbdata)
{
    (void)cbdata;
    if (probeEnabled)
    {
        ++callbackDepth;
        const ObservationContext context = nextContext();
        // serializer resolves every Houdini value while the callback is active.
        // No OP_Node* or data pointer is stored in the resulting JSON object.
        writeObservation(serializer.createObservation(node, reason, data, context));
        --callbackDepth;
    }
    NativeAdapter::instance().recordEvent(node, reason);
}

QString
Watcher::lifecycleEventName(OP_Director::EventType type)
{
    switch (type)
    {
    case OP_Director::BEGIN_CLEAR_NETWORK: return "BeforeClear";
    case OP_Director::END_CLEAR_NETWORK: return "AfterClear";
    case OP_Director::BEGIN_LOAD_NETWORK: return "BeforeLoad";
    case OP_Director::END_LOAD_NETWORK: return "AfterLoad";
    case OP_Director::BEGIN_MERGE_NETWORK: return "BeforeMerge";
    case OP_Director::END_MERGE_NETWORK: return "AfterMerge";
    case OP_Director::BEGIN_SAVE_NETWORK: return "BeforeSave";
    case OP_Director::END_SAVE_NETWORK: return "AfterSave";
    default: return "UNKNOWN_DIRECTOR_EVENT";
    }
}

void
Watcher::directorEventHook(OP_Director::EventType type, void *cbdata)
{
    (void)cbdata;
    if (type == OP_Director::BEGIN_LOAD_NETWORK)
    {
        loadInProgress = true;
        loadGenerationAdvanced = false;
    }
    if (type == OP_Director::END_CLEAR_NETWORK)
    {
        ++currentSceneGeneration;
        if (loadInProgress)
            loadGenerationAdvanced = true;
    }
    else if (type == OP_Director::END_LOAD_NETWORK)
    {
        if (!loadGenerationAdvanced)
            ++currentSceneGeneration;
        loadInProgress = false;
        loadGenerationAdvanced = false;
    }
    if (probeEnabled)
    {
        ++callbackDepth;
        const ObservationContext context = nextContext("scene_lifecycle");
        writeObservation(serializer.createLifecycleObservation(
            lifecycleEventName(type), static_cast<int>(type), context));
        --callbackDepth;
    }
    NativeAdapter::instance().recordLifecycle(
        lifecycleEventName(type), currentSceneGeneration);
}
