#pragma once

#include <cstdint>

#include <OP/OP_Node.h>
#include <OP/OP_Value.h>
#include <QtCore/QJsonObject>
#include <QtCore/QString>

class NativeAdapter
{
public:
    static constexpr int BRIDGE_SCHEMA_VERSION = 1;

    static NativeAdapter &instance();

    QJsonObject capabilities() const;
    QJsonObject startCapture(const QJsonObject &request);
    QJsonObject stopCapture();
    QJsonObject captureState() const;
    QJsonObject flushSettle();
    QJsonObject extractSupportedSnapshot(const QJsonObject &request);
    QJsonObject drainCapture(const QJsonObject &request);
    QJsonObject enqueueApply(const QJsonObject &request);
    QJsonObject drainApply(const QJsonObject &request);
    QJsonObject resetForTests(const QJsonObject &request);

    void recordEvent(OP_Node *node, OP_EventType reason);
    void recordLifecycle(const QString &event, std::int64_t sceneGeneration);

private:
    NativeAdapter();
    ~NativeAdapter();
    NativeAdapter(const NativeAdapter &) = delete;
    NativeAdapter &operator=(const NativeAdapter &) = delete;

    class Impl;
    Impl *myImpl;
};

QJsonObject coophouBridgeError(
    const QString &code,
    const QString &message,
    const QJsonObject &context = {});

QJsonObject coophouBridgeSuccess(const QJsonObject &payload = {});
