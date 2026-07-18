#include "event_manager.h"

#include <SYS/SYS_Version.h>
#include <OP/OP_Network.h>
#include <UT/UT_HDKVersion.h>
#include <UT/UT_String.h>
#include <UT/UT_StringHolder.h>
#include <UT/UT_UndoManager.h>

#include <QtCore/QDateTime>
#include <QtCore/QJsonValue>
#include <QtCore/QtGlobal>

namespace
{
constexpr int TRACE_VERSION = 1;
constexpr const char *ENTITY_ID_KEY = "coophou.entity_id";

QString platformName()
{
#if defined(_WIN32)
    return "windows";
#elif defined(__APPLE__)
    return "macos";
#elif defined(__linux__)
    return "linux";
#else
    return "unknown";
#endif
}

QString undoState()
{
    return UTperformingUndoRedo() ? "undo_or_redo" : "not_undo_redo";
}
}

QString
EventManager::nodePath(const OP_Node *node)
{
    if (!node)
        return {};
    UT_String path;
    node->getFullPath(path);
    return QString::fromUtf8(path.c_str());
}

QString
EventManager::entityId(const OP_Node *node)
{
    if (!node)
        return {};
    UT_StringHolder value;
    if (!node->getUserData(ENTITY_ID_KEY, value))
        return {};
    return QString::fromUtf8(value.c_str());
}

QJsonObject
EventManager::baseObservation(const ObservationContext &context)
{
    return {
        {"trace_version", TRACE_VERSION},
        {"adapter", context.adapter},
        {"scenario", context.scenario},
        {"houdini_version", SYS_VERSION_FULL},
        {"houdini_build", SYS_VERSION_BUILD_INT},
        {"platform", platformName()},
        {"python_version", QJsonValue::Null},
        {"qt_version", QT_VERSION_STR},
        {"hdk_api_version", HDK_API_VERSION},
        {"scene_generation", static_cast<qint64>(context.sceneGeneration)},
        {"observation", static_cast<qint64>(context.observation)},
        {"timestamp_ns", static_cast<qint64>(
            QDateTime::currentMSecsSinceEpoch() * static_cast<qint64>(1000000))},
        {"event", "UNKNOWN_EVENT"},
        {"event_reason", QJsonValue::Null},
        {"node_path", QJsonValue::Null},
        {"parent_path", QJsonValue::Null},
        {"entity_id", QJsonValue::Null},
        {"payload", QJsonObject{}},
        {"undo_state", undoState()},
        {"callback_depth", context.callbackDepth},
        {"transaction_hint", context.transactionHint.isEmpty()
            ? QJsonValue(QJsonValue::Null)
            : QJsonValue(context.transactionHint)},
        {"suppression", QJsonObject{{"depth", 0}, {"label", QJsonValue::Null}}},
    };
}

QJsonObject
EventManager::createObservation(
    OP_Node *node,
    OP_EventType reason,
    void *data,
    const ObservationContext &context) const
{
    QJsonObject result = baseObservation(context);
    const bool knownReason = static_cast<int>(reason) >= 0 && reason < OP_EVENT_TYPE_COUNT;
    const char *eventName = knownReason ? OPeventToString(reason) : nullptr;
    result["event"] = eventName ? QString::fromUtf8(eventName) : QString("UNKNOWN_EVENT");
    result["event_reason"] = static_cast<int>(reason);

    if (node)
    {
        const QString path = nodePath(node);
        result["node_path"] = path.isEmpty() ? QJsonValue(QJsonValue::Null) : QJsonValue(path);
        OP_Network *parent = node->getParent();
        const QString parentPath = nodePath(parent);
        result["parent_path"] = parentPath.isEmpty()
            ? QJsonValue(QJsonValue::Null)
            : QJsonValue(parentPath);
        const QString id = entityId(node);
        result["entity_id"] = id.isEmpty() ? QJsonValue(QJsonValue::Null) : QJsonValue(id);
    }

    // The callback payload is deliberately not dereferenced.  Its event-specific
    // meaning remains unverified for this Houdini build until paired traces prove
    // a safe interpretation.  Pointer addresses are neither stable nor useful.
    result["payload"] = QJsonObject{
        {"data_present", data != nullptr},
        {"data_semantics", data ? "unverified" : "none"},
    };
    return result;
}

QJsonObject
EventManager::createLifecycleObservation(
    const QString &event,
    int eventReason,
    const ObservationContext &context) const
{
    QJsonObject result = baseObservation(context);
    result["event"] = event;
    result["event_reason"] = eventReason;
    result["payload"] = QJsonObject{{"lifecycle", true}};
    return result;
}

QJsonObject
EventManager::createPayload(OP_Node *node, OP_EventType reason, void *data) const
{
    ObservationContext context;
    QJsonObject result = createObservation(node, reason, data, context);
    if (reason == OP_CHILD_CREATED)
    {
        result["event"] = "child_created";
        result["parent_path"] = nodePath(node);
    }
    return result;
}
