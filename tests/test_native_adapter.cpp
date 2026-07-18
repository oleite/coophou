#include "houdini_fixture.h"

#include "native_adapter.h"

#include <OP/OP_Network.h>
#include <OP/OP_Node.h>
#include <QtCore/QJsonArray>
#include <QtCore/QJsonObject>
#include <UT/UT_StringHolder.h>

namespace
{
QJsonObject config(const QString &prefix = "test")
{
    return {
        {"bridge_schema_version", 1},
        {"root_path", "/obj"},
        {"root_entity_id", "root"},
        {"deterministic_id_prefix", prefix},
        {"operator_types", QJsonArray{"geo", "subnet", "null", "merge"}},
        {"parameter_names", QJsonArray{}},
        {"parameter_kinds", QJsonObject{}},
        {"max_nodes", 128},
        {"capture_queue_limit", 16},
        {"apply_queue_limit", 8},
    };
}

QJsonObject reference(const QString &id, const QString &path)
{
    return {
        {"version", 1},
        {"entity_id", id},
        {"entity_kind", "node"},
        {"last_known_path", path},
    };
}

QJsonObject createOperation(
    const QString &operationId,
    const QString &entityId,
    const QString &name)
{
    return {
        {"version", 1},
        {"operation_type", "node.create"},
        {"operation_id", operationId},
        {"spec", QJsonObject{
            {"version", 1},
            {"entity", reference(entityId, "/obj/" + name)},
            {"parent", reference("root", "/obj")},
            {"operator_type", "geo"},
            {"name", name},
            {"position", QJsonArray{2.0, 3.0}},
            {"initial_parameters", QJsonArray{}},
        }},
    };
}

QJsonObject transaction(
    const QString &transactionId,
    const QJsonArray &operations)
{
    return {
        {"version", 1},
        {"transaction_id", transactionId},
        {"author_client_id", "remote-client"},
        {"session_id", "test-session"},
        {"operations", operations},
        {"activity_label", QJsonValue(QJsonValue::Null)},
        {"required_operation_types", QJsonArray{"node.create"}},
    };
}

QJsonObject applyRequest(
    const QJsonObject &tx,
    std::int64_t generation = 1)
{
    return {
        {"bridge_schema_version", 1},
        {"scene_generation", generation},
        {"correlation_id", "correlation-1"},
        {"transaction", tx},
    };
}

QJsonObject payload(const QJsonObject &response)
{
    EXPECT_TRUE(response.value("ok").toBool()) << response.value("error").toObject().value("message").toString().toStdString();
    return response.value("payload").toObject();
}
}

TEST_F(HoudiniFixture, NativeCapabilitiesDeclareExactTargetAndSevenOperations)
{
    const QJsonObject result = payload(NativeAdapter::instance().capabilities());
    EXPECT_EQ(result.value("houdini_version").toString(), "21.0.729");
    EXPECT_EQ(result.value("hdk_api_version").toInt(), 21000693);
    EXPECT_EQ(result.value("bridge_schema_version").toInt(), 1);
    EXPECT_EQ(result.value("production_adapter").toString(), "hdk_cpp");
    EXPECT_EQ(result.value("operation_types").toArray().size(), 7);
}

TEST_F(HoudiniFixture, NativeCaptureSettlesCreateAndAssignsDeterministicIdentity)
{
    NativeAdapter &adapter = NativeAdapter::instance();
    payload(adapter.startCapture(config("capture")));

    OP_Node *node = objectNetwork()->createNodeOfExactType("geo", "captured_geo");
    ASSERT_NE(node, nullptr);
    ASSERT_TRUE(node->setXYWithBoundsChecks(4.0, 5.0));

    const QJsonObject settled = payload(adapter.flushSettle());
    EXPECT_EQ(settled.value("operation_count").toInt(), 1);
    const QJsonObject drained = payload(adapter.drainCapture({
        {"bridge_schema_version", 1}, {"max_count", 8}}));
    const QJsonArray records = drained.value("records").toArray();
    ASSERT_EQ(records.size(), 1);
    const QJsonArray operations = records[0].toObject().value("operations").toArray();
    ASSERT_EQ(operations.size(), 1);
    EXPECT_EQ(operations[0].toObject().value("operation_type").toString(), "node.create");
    EXPECT_FALSE(operations[0].toObject().contains("operation_id"));

    UT_StringHolder id;
    ASSERT_TRUE(node->getUserData("coophou.entity_id", id));
    EXPECT_EQ(QString::fromUtf8(id.c_str()), "capture-1");
    payload(adapter.stopCapture());
}

TEST_F(HoudiniFixture, NativeBridgeSchemaRejectsUnknownFieldsAndVersions)
{
    NativeAdapter &adapter = NativeAdapter::instance();
    QJsonObject unknown{{"bridge_schema_version", 1}, {"max_count", 1}, {"extra", true}};
    QJsonObject response = adapter.drainCapture(unknown);
    EXPECT_FALSE(response.value("ok").toBool());
    EXPECT_EQ(response.value("error").toObject().value("code").toString(), "SCHEMA_INVALID");

    response = adapter.drainCapture({{"bridge_schema_version", 999}, {"max_count", 1}});
    EXPECT_FALSE(response.value("ok").toBool());
    EXPECT_EQ(response.value("error").toObject().value("code").toString(), "BRIDGE_UNSUPPORTED_VERSION");
}

TEST_F(HoudiniFixture, NativeSupportedSnapshotIsVersionedPlainState)
{
    NativeAdapter &adapter = NativeAdapter::instance();
    payload(adapter.startCapture(config("snapshot")));
    OP_Node *node = objectNetwork()->createNodeOfExactType("geo", "snapshot_geo");
    ASSERT_NE(node, nullptr);
    payload(adapter.flushSettle());
    const QJsonObject snapshot = payload(adapter.extractSupportedSnapshot({
        {"bridge_schema_version", 1},
    }));
    EXPECT_EQ(snapshot.value("snapshot_schema_version").toInt(), 1);
    EXPECT_EQ(snapshot.value("root").toObject().value("entity_id").toString(), "root");
    EXPECT_EQ(snapshot.value("nodes").toArray().size(), 1);
    EXPECT_TRUE(snapshot.value("nodes").toArray()[0].toObject().value("entity_id").isString());
    payload(adapter.stopCapture());
}

TEST_F(HoudiniFixture, NativeApplyCreatesVerifiesSuppressesEchoAndReplaysSafely)
{
    NativeAdapter &adapter = NativeAdapter::instance();
    payload(adapter.startCapture(config("apply")));
    const QJsonObject tx = transaction(
        "transaction-1",
        QJsonArray{createOperation("operation-1", "remote-entity", "remote_geo")});
    payload(adapter.enqueueApply(applyRequest(tx)));
    const QJsonObject drained = payload(adapter.drainApply({
        {"bridge_schema_version", 1},
        {"max_transactions", 1},
        {"max_operations", 8},
    }));
    const QJsonObject first = drained.value("results").toArray()[0].toObject();
    ASSERT_TRUE(first.value("ok").toBool());
    EXPECT_EQ(first.value("payload").toObject().value("status").toString(), "APPLIED_VERIFIED");
    ASSERT_NE(OPgetDirector()->findNode("/obj/remote_geo"), nullptr);
    EXPECT_EQ(payload(adapter.drainCapture({
        {"bridge_schema_version", 1}, {"max_count", 8}})).value("records").toArray().size(), 0);

    payload(adapter.enqueueApply(applyRequest(tx)));
    const QJsonObject replayDrain = payload(adapter.drainApply({
        {"bridge_schema_version", 1},
        {"max_transactions", 1},
        {"max_operations", 8},
    }));
    const QJsonObject replay = replayDrain.value("results").toArray()[0].toObject();
    ASSERT_TRUE(replay.value("ok").toBool());
    EXPECT_EQ(replay.value("payload").toObject().value("status").toString(), "APPLIED_REPLAY");
    EXPECT_GT(payload(adapter.captureState()).value("expected_echoes_suppressed").toInt(), 0);
    payload(adapter.stopCapture());
}

TEST_F(HoudiniFixture, NativeApplyRejectsStaleGenerationBeforeQueueing)
{
    NativeAdapter &adapter = NativeAdapter::instance();
    const QJsonObject started = payload(adapter.startCapture(config("stale")));
    const std::int64_t generation = static_cast<std::int64_t>(started.value("scene_generation").toDouble());
    const QJsonObject tx = transaction(
        "transaction-stale",
        QJsonArray{createOperation("operation-stale", "stale-entity", "stale_geo")});
    const QJsonObject rejected = adapter.enqueueApply(applyRequest(tx, generation + 1));
    EXPECT_FALSE(rejected.value("ok").toBool());
    EXPECT_EQ(rejected.value("error").toObject().value("code").toString(), "STALE_SCENE_GENERATION");
    EXPECT_EQ(payload(adapter.captureState()).value("apply_queue_size").toInt(), 0);
    payload(adapter.stopCapture());
}

TEST_F(HoudiniFixture, NativeApplyQueueOverflowIsExplicitAndStopsAdvancement)
{
    NativeAdapter &adapter = NativeAdapter::instance();
    QJsonObject bounded = config("apply-bound");
    bounded["apply_queue_limit"] = 1;
    const QJsonObject started = payload(adapter.startCapture(bounded));
    const auto generation = static_cast<std::int64_t>(
        started.value("scene_generation").toDouble());
    payload(adapter.enqueueApply(applyRequest(transaction(
        "transaction-bound-a",
        QJsonArray{createOperation("operation-bound-a", "bound-a", "bound_a")}),
        generation)));
    const QJsonObject overflow = adapter.enqueueApply(applyRequest(transaction(
        "transaction-bound-b",
        QJsonArray{createOperation("operation-bound-b", "bound-b", "bound_b")}),
        generation));
    EXPECT_FALSE(overflow.value("ok").toBool());
    EXPECT_EQ(overflow.value("error").toObject().value("code").toString(), "QUEUE_OVERFLOW");
    const QJsonObject state = payload(adapter.captureState());
    EXPECT_TRUE(state.value("apply_overflow").toBool());
    EXPECT_TRUE(state.value("reconciliation_required").toBool());
    payload(adapter.stopCapture());
}

TEST_F(HoudiniFixture, NativeFaultInjectionReportsTruthfulPartialApplyAndStops)
{
    NativeAdapter &adapter = NativeAdapter::instance();
    payload(adapter.startCapture(config("fault")));
    payload(adapter.resetForTests({
        {"bridge_schema_version", 1}, {"fault_operation_index", 1}}));
    const QJsonArray operations{
        createOperation("operation-first", "fault-first", "fault_first"),
        createOperation("operation-second", "fault-second", "fault_second"),
    };
    const QJsonObject tx = transaction("transaction-fault", operations);
    payload(adapter.enqueueApply(applyRequest(tx)));
    const QJsonObject drained = payload(adapter.drainApply({
        {"bridge_schema_version", 1},
        {"max_transactions", 1},
        {"max_operations", 8},
    }));
    const QJsonObject result = drained.value("results").toArray()[0].toObject();
    EXPECT_FALSE(result.value("ok").toBool());
    EXPECT_EQ(result.value("error").toObject().value("code").toString(), "RECONCILIATION_REQUIRED");
    EXPECT_TRUE(result.value("error").toObject().value("context").toObject().value("partial_apply").toBool());
    EXPECT_NE(OPgetDirector()->findNode("/obj/fault_first"), nullptr);
    EXPECT_EQ(OPgetDirector()->findNode("/obj/fault_second"), nullptr);
    EXPECT_TRUE(payload(adapter.captureState()).value("reconciliation_required").toBool());
    payload(adapter.stopCapture());
}
