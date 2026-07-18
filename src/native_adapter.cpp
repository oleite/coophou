#include "native_adapter.h"

#include "watcher.h"

#include <algorithm>
#include <atomic>
#include <chrono>
#include <cmath>
#include <deque>
#include <functional>
#include <limits>
#include <mutex>
#include <optional>

#include <CH/CH_Manager.h>
#include <OP/OP_Director.h>
#include <OP/OP_Network.h>
#include <OP/OP_Operator.h>
#include <PRM/PRM_Parm.h>
#include <PRM/PRM_ParmList.h>
#include <PRM/PRM_ChoiceList.h>
#include <PRM/PRM_Template.h>
#include <SYS/SYS_Version.h>
#include <UT/UT_HDKVersion.h>
#include <UT/UT_String.h>
#include <UT/UT_StringHolder.h>
#include <UT/UT_Thread.h>

#include <QtCore/QCryptographicHash>
#include <QtCore/QJsonArray>
#include <QtCore/QJsonDocument>
#include <QtCore/QJsonValue>
#include <QtCore/QMap>
#include <QtCore/QRegularExpression>
#include <QtCore/QSet>
#include <QtCore/QUuid>
#include <QtCore/QtGlobal>

namespace
{
constexpr const char *ENTITY_ID_KEY = "coophou.entity_id";
constexpr int MODEL_VERSION = 1;
constexpr int DEFAULT_MAX_NODES = 1024;
constexpr int DEFAULT_CAPTURE_LIMIT = 1024;
constexpr int DEFAULT_APPLY_LIMIT = 128;
constexpr int DEFAULT_APPLIED_HISTORY_LIMIT = 4096;

class AtomicDuration
{
public:
    AtomicDuration(std::atomic<std::int64_t> &total, std::atomic<std::int64_t> &maximum)
        : myTotal(total), myMaximum(maximum), myStart(std::chrono::steady_clock::now()) {}
    ~AtomicDuration()
    {
        const auto elapsed = std::chrono::duration_cast<std::chrono::nanoseconds>(
            std::chrono::steady_clock::now() - myStart).count();
        myTotal.fetch_add(elapsed, std::memory_order_relaxed);
        std::int64_t previous = myMaximum.load(std::memory_order_relaxed);
        while (previous < elapsed
            && !myMaximum.compare_exchange_weak(previous, elapsed, std::memory_order_relaxed)) {}
    }
private:
    std::atomic<std::int64_t> &myTotal;
    std::atomic<std::int64_t> &myMaximum;
    std::chrono::steady_clock::time_point myStart;
};

class DurationCounter
{
public:
    DurationCounter(std::int64_t &count, std::int64_t &total, std::int64_t &maximum)
        : myCount(count), myTotal(total), myMaximum(maximum), myStart(std::chrono::steady_clock::now()) {}
    ~DurationCounter()
    {
        const auto elapsed = std::chrono::duration_cast<std::chrono::nanoseconds>(
            std::chrono::steady_clock::now() - myStart).count();
        ++myCount;
        myTotal += elapsed;
        myMaximum = std::max(myMaximum, static_cast<std::int64_t>(elapsed));
    }
private:
    std::int64_t &myCount;
    std::int64_t &myTotal;
    std::int64_t &myMaximum;
    std::chrono::steady_clock::time_point myStart;
};

const QSet<QString> SUPPORTED_OPERATIONS = {
    "node.create",
    "subtree.create",
    "subtree.delete",
    "node.rename",
    "node.move",
    "node.input.set",
    "node.parameter_tuple.set",
};

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

QString nodePath(const OP_Node *node)
{
    if (!node)
        return {};
    UT_String path;
    node->getFullPath(path);
    return QString::fromUtf8(path.c_str());
}

QString nodeName(const OP_Node *node)
{
    return node ? QString::fromUtf8(node->getName().c_str()) : QString();
}

QString nodeEntityId(const OP_Node *node)
{
    if (!node)
        return {};
    UT_StringHolder value;
    if (!node->getUserData(ENTITY_ID_KEY, value))
        return {};
    return QString::fromUtf8(value.c_str());
}

bool validIdentifier(const QString &value)
{
    static const QRegularExpression pattern(
        QStringLiteral("^[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}$"));
    return pattern.match(value).hasMatch();
}

bool validName(const QString &value)
{
    static const QRegularExpression pattern(
        QStringLiteral("^[A-Za-z_][A-Za-z0-9_]{0,63}$"));
    return pattern.match(value).hasMatch();
}

bool integerInRange(const QJsonValue &value, std::int64_t minimum, std::int64_t maximum)
{
    if (!value.isDouble() || !std::isfinite(value.toDouble())
        || std::floor(value.toDouble()) != value.toDouble())
        return false;
    return value.toDouble() >= static_cast<double>(minimum)
        && value.toDouble() <= static_cast<double>(maximum);
}

bool pathWithinRoot(const QString &path, const QString &root)
{
    return path == root || (root == "/"
        ? path.startsWith('/')
        : path.startsWith(root + "/"));
}

QJsonObject entityRef(
    const QString &entityId,
    const QString &path)
{
    return {
        {"version", MODEL_VERSION},
        {"entity_id", entityId},
        {"entity_kind", "node"},
        {"last_known_path", path.isEmpty()
            ? QJsonValue(QJsonValue::Null)
            : QJsonValue(path)},
    };
}

QJsonObject tupleValue(const QString &kind, const QJsonArray &values)
{
    return {
        {"version", MODEL_VERSION},
        {"value_kind", kind},
        {"values", values},
    };
}

QJsonObject connectionRef(
    const QString &sourceId,
    const QString &sourcePath,
    int outputIndex)
{
    return {
        {"version", MODEL_VERSION},
        {"source", entityRef(sourceId, sourcePath)},
        {"output_index", outputIndex},
    };
}

QByteArray canonicalJson(const QJsonValue &value)
{
    std::function<QJsonValue(const QJsonValue &)> sortValue;
    sortValue = [&sortValue](const QJsonValue &input) -> QJsonValue {
        if (input.isArray())
        {
            QJsonArray result;
            for (const QJsonValue &item : input.toArray())
                result.append(sortValue(item));
            return result;
        }
        if (input.isObject())
        {
            const QJsonObject object = input.toObject();
            QStringList keys = object.keys();
            std::sort(keys.begin(), keys.end());
            QJsonObject result;
            for (const QString &key : keys)
                result.insert(key, sortValue(object.value(key)));
            return result;
        }
        return input;
    };
    return QJsonDocument(sortValue(value).toObject()).toJson(QJsonDocument::Compact);
}

QString semanticHash(const QJsonObject &object)
{
    return QString::fromLatin1(QCryptographicHash::hash(
        canonicalJson(object), QCryptographicHash::Sha256).toHex());
}

bool exactObjectKeys(
    const QJsonObject &object,
    const QSet<QString> &required,
    const QSet<QString> &optional,
    QString &message)
{
    const QStringList actualKeys = object.keys();
    const QSet<QString> actual(actualKeys.begin(), actualKeys.end());
    QSet<QString> missing = required;
    missing.subtract(actual);
    if (!missing.isEmpty())
    {
        message = "required fields are missing";
        return false;
    }
    QSet<QString> allowed = required;
    allowed.unite(optional);
    QSet<QString> extra = actual;
    extra.subtract(allowed);
    if (!extra.isEmpty())
    {
        message = "unknown fields are not allowed";
        return false;
    }
    return true;
}

struct ParameterState
{
    QString kind;
    QJsonArray values;

    QJsonObject json() const { return tupleValue(kind, values); }
    bool operator==(const ParameterState &other) const
    {
        return kind == other.kind && values == other.values;
    }
    bool operator!=(const ParameterState &other) const { return !(*this == other); }
};

struct ConnectionState
{
    QString sourceId;
    int outputIndex{0};

    bool operator==(const ConnectionState &other) const
    {
        return sourceId == other.sourceId && outputIndex == other.outputIndex;
    }
    bool operator!=(const ConnectionState &other) const { return !(*this == other); }
};

struct NodeState
{
    QString id;
    QString parentId;
    QString operatorType;
    QString name;
    QString path;
    double x{0.0};
    double y{0.0};
    QMap<QString, ParameterState> parameters;
    QMap<int, ConnectionState> inputs;
};

struct SceneSnapshot
{
    QMap<QString, NodeState> nodes;
    QHash<QString, OP_Node *> pointers;
    QString rootId;
};

struct TombstoneState
{
    QString parentId;
    QString path;
};

QJsonObject supportedSnapshotJson(
    const SceneSnapshot &snapshot,
    const QMap<QString, TombstoneState> &tombstones,
    const QString &rootPath,
    std::int64_t sceneGeneration)
{
    QJsonArray nodes;
    for (auto node = snapshot.nodes.cbegin(); node != snapshot.nodes.cend(); ++node)
    {
        if (node.key() == snapshot.rootId)
            continue;
        QJsonObject parameters;
        for (auto parameter = node->parameters.cbegin(); parameter != node->parameters.cend(); ++parameter)
            parameters.insert(parameter.key(), parameter.value().json());
        QJsonObject inputs;
        for (auto input = node->inputs.cbegin(); input != node->inputs.cend(); ++input)
            inputs.insert(QString::number(input.key()), QJsonObject{
                {"source_entity_id", input->sourceId},
                {"output_index", input->outputIndex},
            });
        nodes.append(QJsonObject{
            {"version", MODEL_VERSION},
            {"entity_id", node->id},
            {"parent_id", node->parentId},
            {"operator_type", node->operatorType},
            {"name", node->name},
            {"native_path", node->path},
            {"position", QJsonArray{node->x, node->y}},
            {"parameters", parameters},
            {"inputs", inputs},
        });
    }
    QJsonArray deleted;
    for (auto tombstone = tombstones.cbegin(); tombstone != tombstones.cend(); ++tombstone)
        deleted.append(QJsonObject{
            {"version", MODEL_VERSION},
            {"entity_id", tombstone.key()},
            {"parent_id", tombstone->parentId.isEmpty()
                ? QJsonValue(QJsonValue::Null) : QJsonValue(tombstone->parentId)},
            {"last_known_native_path", tombstone->path},
        });
    return {
        {"snapshot_schema_version", 1},
        {"scene_generation", sceneGeneration},
        {"root", QJsonObject{
            {"entity_id", snapshot.rootId},
            {"native_path", rootPath},
        }},
        {"nodes", nodes},
        {"tombstones", deleted},
    };
}

QJsonObject namedParameter(const QString &name, const ParameterState &state)
{
    return {
        {"version", MODEL_VERSION},
        {"name", name},
        {"value", state.json()},
    };
}

QJsonObject nodeSpec(const NodeState &node, const SceneSnapshot &snapshot)
{
    QJsonArray parameters;
    for (auto it = node.parameters.cbegin(); it != node.parameters.cend(); ++it)
        parameters.append(namedParameter(it.key(), it.value()));
    const QString parentPath = snapshot.nodes.contains(node.parentId)
        ? snapshot.nodes.value(node.parentId).path
        : QString();
    return {
        {"version", MODEL_VERSION},
        {"entity", entityRef(node.id, node.path)},
        {"parent", entityRef(node.parentId, parentPath)},
        {"operator_type", node.operatorType},
        {"name", node.name},
        {"position", QJsonArray{node.x, node.y}},
        {"initial_parameters", parameters},
    };
}

QJsonObject operationCandidate(const QString &type)
{
    return {{"version", MODEL_VERSION}, {"operation_type", type}};
}

bool numericArray2(const QJsonValue &value, double &x, double &y)
{
    if (!value.isArray() || value.toArray().size() != 2)
        return false;
    const QJsonArray array = value.toArray();
    if (!array[0].isDouble() || !array[1].isDouble())
        return false;
    x = array[0].toDouble();
    y = array[1].toDouble();
    return std::isfinite(x) && std::isfinite(y)
        && std::abs(x) <= 1.0e6 && std::abs(y) <= 1.0e6;
}
}

QJsonObject
coophouBridgeError(
    const QString &code,
    const QString &message,
    const QJsonObject &context)
{
    return {
        {"bridge_schema_version", NativeAdapter::BRIDGE_SCHEMA_VERSION},
        {"ok", false},
        {"error", QJsonObject{
            {"code", code},
            {"message", message},
            {"context", context},
        }},
    };
}

QJsonObject
coophouBridgeSuccess(const QJsonObject &payload)
{
    return {
        {"bridge_schema_version", NativeAdapter::BRIDGE_SCHEMA_VERSION},
        {"ok", true},
        {"payload", payload},
    };
}

class NativeAdapter::Impl
{
public:
    mutable std::recursive_mutex mutex;
    bool active{false};
    bool dirty{false};
    bool broadSettle{false};
    bool captureOverflow{false};
    bool applyOverflow{false};
    bool reconciliationRequired{false};
    QString rootPath{"/obj"};
    QString rootEntityId{"root"};
    QSet<QString> operatorTypes{"geo", "subnet", "null", "merge"};
    QStringList parameterNames;
    QMap<QString, QString> parameterKinds;
    QString deterministicPrefix;
    std::int64_t deterministicCounter{0};
    int maxNodes{DEFAULT_MAX_NODES};
    int captureLimit{DEFAULT_CAPTURE_LIMIT};
    int applyLimit{DEFAULT_APPLY_LIMIT};
    int appliedHistoryLimit{DEFAULT_APPLIED_HISTORY_LIMIT};
    int remoteApplyDepth{0};
    int identityWriteDepth{0};
    std::int64_t eventCount{0};
    std::int64_t ignoredEventCount{0};
    std::int64_t suppressedEchoCount{0};
    std::int64_t internalIdentityEventCount{0};
    std::int64_t settleCount{0};
    std::int64_t captureSequence{0};
    std::int64_t applySequence{0};
    std::atomic<std::int64_t> callbackHandlerNsTotal{0};
    std::atomic<std::int64_t> callbackHandlerNsMax{0};
    std::int64_t extractionCount{0};
    std::int64_t extractionNsTotal{0};
    std::int64_t extractionNsMax{0};
    std::int64_t sceneGeneration{1};
    QString currentTransactionId;
    QStringList currentOperationIds;
    QSet<QString> affectedScopes;
    QSet<QString> targetedPaths;
    QSet<QString> predeleteIds;
    QMap<QString, TombstoneState> tombstones;
    SceneSnapshot mirror;
    std::deque<QJsonObject> captureQueue;
    std::deque<QJsonObject> applyQueue;
    QMap<QString, QString> appliedHashes;
    QStringList appliedOrder;
    int faultOperationIndex{-1};

    QString nextId()
    {
        if (!deterministicPrefix.isEmpty())
            return QString("%1-%2").arg(deterministicPrefix).arg(++deterministicCounter);
        return QUuid::createUuid().toString(QUuid::WithoutBraces);
    }

    bool supportsType(const QString &type) const
    {
        return operatorTypes.isEmpty() || operatorTypes.contains(type);
    }

    QString ensureIdentity(
        OP_Node *node,
        const QString &forced,
        QString &error)
    {
        QString id = nodeEntityId(node);
        if (!forced.isEmpty())
            id = forced;
        if (id.isEmpty() || tombstones.contains(id))
            id = nextId();
        if (nodeEntityId(node) == id)
            return id;
        if (!node->canAccess(PRM_WRITE_OK))
        {
            error = QString("node is not writable for identity assignment: %1")
                .arg(nodePath(node));
            return {};
        }
        ++identityWriteDepth;
        node->setUserData(
            ENTITY_ID_KEY,
            UT_StringHolder(id.toUtf8().constData()),
            false);
        --identityWriteDepth;
        if (nodeEntityId(node) != id)
        {
            error = QString("identity assignment did not persist: %1")
                .arg(nodePath(node));
            return {};
        }
        return id;
    }

    std::optional<ParameterState> extractParameter(
        OP_Node *node,
        const QString &name,
        QString &error) const
    {
        PRM_ParmList *list = node->getParmList();
        if (!list)
            return std::nullopt;
        PRM_Parm *parm = list->getParmPtr(UT_StringHolder(name.toUtf8().constData()));
        if (!parm)
            return std::nullopt;
        const int arity = parm->getVectorSize();
        if (arity < 1 || arity > 64)
        {
            error = QString("unsupported parameter tuple arity for %1").arg(name);
            return std::nullopt;
        }
        const fpreal time = CHgetEvalTime();
        for (int index = 0; index < arity; ++index)
        {
            if (parm->getChannel(index))
            {
                error = QString("expressions and keyframes are unsupported for %1").arg(name);
                return std::nullopt;
            }
        }

        QString kind = parameterKinds.value(name);
        const PRM_Type &type = parm->getType();
        if (kind.isEmpty())
        {
            if (type.isOrdinalType())
                kind = type.getOrdinalType() == PRM_Type::PRM_ORD_TOGGLE
                    ? "boolean" : "integer";
            else if (type.isFloatType())
                kind = "float";
            else if (type.isStringType())
                kind = "string";
            else
            {
                error = QString("unsupported parameter storage type for %1").arg(name);
                return std::nullopt;
            }
        }

        QJsonArray values;
        for (int index = 0; index < arity; ++index)
        {
            if (kind == "integer")
            {
                int32 value = 0;
                parm->getValue(time, value, index, 0);
                values.append(static_cast<qint64>(value));
            }
            else if (kind == "boolean")
            {
                int32 value = 0;
                parm->getValue(time, value, index, 0);
                values.append(value != 0);
            }
            else if (kind == "float")
            {
                fpreal value = 0.0;
                parm->getValue(time, value, index, 0);
                values.append(static_cast<double>(value));
            }
            else if (kind == "menu_token" && type.isOrdinalType())
            {
                int32 menuIndex = 0;
                parm->getValue(time, menuIndex, index, 0);
                const PRM_ChoiceList *choices = parm->getTemplatePtr()->getChoiceListPtr();
                UT_String token;
                if (!choices || !choices->tokenFromIndex(token, menuIndex, node, nullptr, parm))
                {
                    error = QString("could not resolve ordinal menu token for %1").arg(name);
                    return std::nullopt;
                }
                values.append(QString::fromUtf8(token.c_str()));
            }
            else if (kind == "string" || kind == "menu_token")
            {
                UT_StringHolder value;
                parm->getValue(time, value, index, false, 0);
                values.append(QString::fromUtf8(value.c_str()));
            }
            else
            {
                error = QString("unknown configured raw value kind for %1").arg(name);
                return std::nullopt;
            }
        }
        return ParameterState{kind, values};
    }

    bool extractSnapshot(SceneSnapshot &result, QString &error)
    {
        DurationCounter duration(extractionCount, extractionNsTotal, extractionNsMax);
        result = SceneSnapshot{};
        OP_Director *director = OPgetDirector();
        OP_Node *root = director ? director->findNode(rootPath.toUtf8().constData()) : nullptr;
        if (!root)
        {
            error = QString("collaboration root does not exist: %1").arg(rootPath);
            return false;
        }

        struct PendingNode { OP_Node *node; QString parentId; };
        QVector<PendingNode> pending;
        pending.append(PendingNode{root, QString()});
        QSet<QString> seenIds;
        QVector<OP_Node *> orderedPointers;
        int cursor = 0;
        while (cursor < pending.size())
        {
            if (cursor >= maxNodes)
            {
                error = "collaboration root exceeds the configured node bound";
                return false;
            }
            const PendingNode item = pending[cursor++];
            OP_Node *node = item.node;
            const QString path = nodePath(node);
            QString type = node->getOperator()
                ? QString::fromUtf8(node->getOperator()->getName().c_str())
                : QString("manager");
            if (node != root && !supportsType(type))
            {
                error = QString("operator type is outside the configured capability: %1")
                    .arg(type);
                return false;
            }

            QString idError;
            QString id = node == root
                ? rootEntityId
                : ensureIdentity(node, QString(), idError);
            if (id.isEmpty())
            {
                error = idError;
                return false;
            }

            if (seenIds.contains(id))
            {
                id = ensureIdentity(node, nextId(), idError);
                if (id.isEmpty())
                {
                    error = idError;
                    return false;
                }
            }
            seenIds.insert(id);

            NodeState state;
            state.id = id;
            state.parentId = item.parentId;
            state.operatorType = type;
            state.name = nodeName(node);
            state.path = path;
            state.x = node->getX();
            state.y = node->getY();
            for (const QString &parameterName : parameterNames)
            {
                QString parameterError;
                const auto parameter = extractParameter(node, parameterName, parameterError);
                if (!parameterError.isEmpty())
                {
                    error = QString("%1 at %2").arg(parameterError, path);
                    return false;
                }
                if (parameter)
                    state.parameters.insert(parameterName, *parameter);
            }
            result.nodes.insert(id, state);
            result.pointers.insert(id, node);
            orderedPointers.append(node);
            if (node == root)
                result.rootId = id;

            for (int childIndex = 0; childIndex < node->getNchildren(); ++childIndex)
            {
                OP_Node *child = node->getChild(childIndex);
                if (child)
                    pending.append(PendingNode{child, id});
            }
        }

        for (OP_Node *node : orderedPointers)
        {
            const QString destinationId = nodeEntityId(node);
            if (!result.nodes.contains(destinationId))
                continue;
            NodeState &state = result.nodes[destinationId];
            const unsigned inputCount = node->nInputs();
            for (unsigned inputIndex = 0; inputIndex < inputCount; ++inputIndex)
            {
                OP_Node *source = node->getInput(static_cast<OP_InputIdx>(inputIndex));
                if (!source)
                    continue;
                const QString sourceId = nodeEntityId(source);
                if (!result.nodes.contains(sourceId))
                    continue;
                const int outputIndex = source->whichOutputIs(
                    node, static_cast<OP_InputIdx>(inputIndex));
                state.inputs.insert(
                    static_cast<int>(inputIndex),
                    ConnectionState{sourceId, std::max(0, outputIndex)});
            }
        }
        return true;
    }

    bool extractTargetedSnapshot(
        const SceneSnapshot &base,
        const QSet<QString> &paths,
        SceneSnapshot &result,
        QString &error)
    {
        DurationCounter duration(extractionCount, extractionNsTotal, extractionNsMax);
        result = base;
        result.pointers.clear();
        OP_Director *director = OPgetDirector();
        OP_Node *root = director ? director->findNode(rootPath.toUtf8().constData()) : nullptr;
        if (!root)
        {
            error = QString("collaboration root does not exist: %1").arg(rootPath);
            return false;
        }
        QStringList orderedPaths = paths.values();
        std::sort(orderedPaths.begin(), orderedPaths.end());
        for (const QString &path : orderedPaths)
        {
            OP_Node *node = director->findNode(path.toUtf8().constData());
            if (!node || node == root)
                continue;
            if (!pathWithinRoot(path, rootPath))
            {
                error = "targeted event path is outside the collaboration root";
                return false;
            }
            const QString type = node->getOperator()
                ? QString::fromUtf8(node->getOperator()->getName().c_str())
                : QString("manager");
            if (!supportsType(type))
            {
                error = QString("operator type is outside the configured capability: %1").arg(type);
                return false;
            }
            QString identityError;
            const QString id = ensureIdentity(node, QString(), identityError);
            if (id.isEmpty() || !result.nodes.contains(id))
            {
                error = identityError.isEmpty()
                    ? QString("targeted event referenced an unmirrored identity: %1").arg(path)
                    : identityError;
                return false;
            }
            OP_Node *parent = node->getParent();
            const QString parentId = parent == root ? result.rootId : nodeEntityId(parent);
            if (!result.nodes.contains(parentId))
            {
                error = QString("targeted node parent identity is unavailable: %1").arg(path);
                return false;
            }
            NodeState state;
            state.id = id;
            state.parentId = parentId;
            state.operatorType = type;
            state.name = nodeName(node);
            state.path = path;
            state.x = node->getX();
            state.y = node->getY();
            for (const QString &parameterName : parameterNames)
            {
                QString parameterError;
                const auto parameter = extractParameter(node, parameterName, parameterError);
                if (!parameterError.isEmpty())
                {
                    error = QString("%1 at %2").arg(parameterError, path);
                    return false;
                }
                if (parameter)
                    state.parameters.insert(parameterName, *parameter);
            }
            const unsigned inputCount = node->nInputs();
            for (unsigned inputIndex = 0; inputIndex < inputCount; ++inputIndex)
            {
                OP_Node *source = node->getInput(static_cast<OP_InputIdx>(inputIndex));
                if (!source)
                    continue;
                const QString sourceId = source == root ? result.rootId : nodeEntityId(source);
                if (!result.nodes.contains(sourceId))
                    continue;
                state.inputs.insert(
                    static_cast<int>(inputIndex),
                    ConnectionState{
                        sourceId,
                        std::max(0, source->whichOutputIs(
                            node, static_cast<OP_InputIdx>(inputIndex))),
                    });
            }
            result.nodes.insert(id, state);

            std::function<void(const QString &, const QString &)> updateDescendantPaths;
            updateDescendantPaths = [&](const QString &parentEntityId, const QString &parentPath) {
                for (auto child = result.nodes.begin(); child != result.nodes.end(); ++child)
                {
                    if (child->parentId != parentEntityId)
                        continue;
                    child->path = parentPath + "/" + child->name;
                    updateDescendantPaths(child.key(), child->path);
                }
            };
            updateDescendantPaths(id, path);
        }
        return true;
    }

    void collectDescendants(
        const SceneSnapshot &snapshot,
        const QString &rootId,
        QStringList &ids) const
    {
        ids.append(rootId);
        for (auto it = snapshot.nodes.cbegin(); it != snapshot.nodes.cend(); ++it)
        {
            if (it->parentId == rootId)
                collectDescendants(snapshot, it.key(), ids);
        }
    }

    QJsonObject candidateConnection(
        const SceneSnapshot &snapshot,
        const ConnectionState &connection) const
    {
        const QString path = snapshot.nodes.contains(connection.sourceId)
            ? snapshot.nodes.value(connection.sourceId).path : QString();
        return connectionRef(connection.sourceId, path, connection.outputIndex);
    }

    QJsonArray diff(const SceneSnapshot &before, const SceneSnapshot &after, QString &error)
    {
        QJsonArray operations;
        QSet<QString> beforeIds(before.nodes.keyBegin(), before.nodes.keyEnd());
        QSet<QString> afterIds(after.nodes.keyBegin(), after.nodes.keyEnd());
        QSet<QString> created = afterIds;
        created.subtract(beforeIds);
        QSet<QString> deleted = beforeIds;
        deleted.subtract(afterIds);

        QMap<QString, QStringList> createdRootsByParent;
        for (const QString &id : created)
            if (!created.contains(after.nodes.value(id).parentId))
                createdRootsByParent[after.nodes.value(id).parentId].append(id);
        for (auto parentGroup = createdRootsByParent.begin();
             parentGroup != createdRootsByParent.end(); ++parentGroup)
        {
            QStringList ids;
            QStringList roots = parentGroup.value();
            std::sort(roots.begin(), roots.end());
            for (const QString &rootId : roots)
            {
                QStringList branch;
                collectDescendants(after, rootId, branch);
                branch.erase(std::remove_if(branch.begin(), branch.end(), [&created](const QString &id) {
                    return !created.contains(id);
                }), branch.end());
                ids.append(branch);
            }
            if (ids.size() == 1)
            {
                QJsonObject operation = operationCandidate("node.create");
                operation["spec"] = nodeSpec(after.nodes.value(ids.front()), after);
                operations.append(operation);
                continue;
            }

            QJsonObject operation = operationCandidate("subtree.create");
            QJsonArray nodes;
            for (const QString &id : ids)
                nodes.append(nodeSpec(after.nodes.value(id), after));
            QJsonArray connections;
            for (const QString &id : ids)
            {
                const NodeState &destination = after.nodes.value(id);
                for (auto input = destination.inputs.cbegin(); input != destination.inputs.cend(); ++input)
                {
                    QJsonObject connection{
                        {"version", MODEL_VERSION},
                        {"destination", entityRef(destination.id, destination.path)},
                        {"input_index", input.key()},
                        {"source", candidateConnection(after, input.value())},
                    };
                    connections.append(connection);
                }
            }
            operation["nodes"] = nodes;
            operation["connections"] = connections;
            operations.append(operation);
        }

        QStringList deletedRoots;
        for (const QString &id : deleted)
            if (!deleted.contains(before.nodes.value(id).parentId))
                deletedRoots.append(id);
        std::sort(deletedRoots.begin(), deletedRoots.end());
        for (const QString &rootId : deletedRoots)
        {
            QStringList ids;
            collectDescendants(before, rootId, ids);
            ids.erase(std::remove_if(ids.begin(), ids.end(), [&deleted](const QString &id) {
                return !deleted.contains(id);
            }), ids.end());
            if (ids.isEmpty() || !predeleteIds.contains(rootId))
            {
                error = QString("deletion lacked callback-time pre-delete evidence for %1")
                    .arg(rootId);
                return {};
            }
            const NodeState &root = before.nodes.value(rootId);
            QJsonArray deletedIds;
            for (const QString &id : ids)
            {
                deletedIds.append(id);
                const NodeState &deletedNode = before.nodes.value(id);
                tombstones.insert(id, TombstoneState{deletedNode.parentId, deletedNode.path});
            }
            QJsonObject operation = operationCandidate("subtree.delete");
            operation["root"] = entityRef(root.id, root.path);
            operation["deleted_entity_ids"] = deletedIds;
            operation["expected_parent_id"] = root.parentId.isEmpty()
                ? QJsonValue(QJsonValue::Null) : QJsonValue(root.parentId);
            operations.append(operation);
        }

        QStringList common;
        for (const QString &id : afterIds)
            if (beforeIds.contains(id))
                common.append(id);
        std::sort(common.begin(), common.end());
        for (const QString &id : common)
        {
            const NodeState &oldNode = before.nodes.value(id);
            const NodeState &newNode = after.nodes.value(id);
            if (oldNode.operatorType != newNode.operatorType
                || oldNode.parentId != newNode.parentId)
            {
                error = QString("unsupported operator type or parent change for %1").arg(id);
                return {};
            }
            if (oldNode.name != newNode.name)
            {
                QJsonObject operation = operationCandidate("node.rename");
                operation["entity"] = entityRef(id, newNode.path);
                operation["name"] = newNode.name;
                operation["expected_name"] = oldNode.name;
                operations.append(operation);
            }
            if (oldNode.x != newNode.x || oldNode.y != newNode.y)
            {
                QJsonObject operation = operationCandidate("node.move");
                operation["entity"] = entityRef(id, newNode.path);
                operation["position"] = QJsonArray{newNode.x, newNode.y};
                operation["expected_position"] = QJsonArray{oldNode.x, oldNode.y};
                operations.append(operation);
            }

            QSet<int> inputIndices(oldNode.inputs.keyBegin(), oldNode.inputs.keyEnd());
            inputIndices.unite(QSet<int>(newNode.inputs.keyBegin(), newNode.inputs.keyEnd()));
            QList<int> sortedInputs = inputIndices.values();
            std::sort(sortedInputs.begin(), sortedInputs.end());
            for (int inputIndex : sortedInputs)
            {
                const bool had = oldNode.inputs.contains(inputIndex);
                const bool has = newNode.inputs.contains(inputIndex);
                if (had == has && (!had || oldNode.inputs.value(inputIndex) == newNode.inputs.value(inputIndex)))
                    continue;
                QJsonObject operation = operationCandidate("node.input.set");
                operation["destination"] = entityRef(id, newNode.path);
                operation["input_index"] = inputIndex;
                operation["expected_source"] = had
                    ? QJsonValue(candidateConnection(before, oldNode.inputs.value(inputIndex)))
                    : QJsonValue(QJsonValue::Null);
                operation["new_source"] = has
                    ? QJsonValue(candidateConnection(after, newNode.inputs.value(inputIndex)))
                    : QJsonValue(QJsonValue::Null);
                operations.append(operation);
            }

            QSet<QString> parameterSet(oldNode.parameters.keyBegin(), oldNode.parameters.keyEnd());
            parameterSet.unite(QSet<QString>(newNode.parameters.keyBegin(), newNode.parameters.keyEnd()));
            QStringList parameters = parameterSet.values();
            std::sort(parameters.begin(), parameters.end());
            for (const QString &name : parameters)
            {
                if (!oldNode.parameters.contains(name) || !newNode.parameters.contains(name))
                {
                    error = QString("supported parameter availability changed for %1:%2")
                        .arg(id, name);
                    return {};
                }
                if (oldNode.parameters.value(name) == newNode.parameters.value(name))
                    continue;
                QJsonObject operation = operationCandidate("node.parameter_tuple.set");
                operation["entity"] = entityRef(id, newNode.path);
                operation["parameter_name"] = name;
                operation["value"] = newNode.parameters.value(name).json();
                operation["expected_value"] = oldNode.parameters.value(name).json();
                operations.append(operation);
            }
        }
        return operations;
    }

    QString referenceId(const QJsonValue &value, QString &error) const
    {
        if (!value.isObject())
        {
            error = "entity reference must be an object";
            return {};
        }
        const QJsonObject reference = value.toObject();
        QString keyError;
        if (!exactObjectKeys(
                reference,
                {"version", "entity_id", "entity_kind", "last_known_path"},
                {}, keyError))
        {
            error = "entity reference fields do not match the bridge schema";
            return {};
        }
        const QJsonValue path = reference.value("last_known_path");
        if (reference.value("version").toInt(-1) != MODEL_VERSION
            || reference.value("entity_kind").toString() != "node"
            || !reference.value("entity_id").isString()
            || !validIdentifier(reference.value("entity_id").toString())
            || (!path.isNull() && (!path.isString()
                || !path.toString().startsWith('/') || path.toString().size() > 1024)))
        {
            error = "entity reference fields are invalid";
            return {};
        }
        return reference.value("entity_id").toString();
    }

    std::optional<ParameterState> parseTupleValue(
        const QJsonValue &value,
        QString &error) const
    {
        if (!value.isObject())
        {
            error = "parameter tuple value must be an object";
            return std::nullopt;
        }
        const QJsonObject object = value.toObject();
        QString keyError;
        if (!exactObjectKeys(
                object, {"version", "value_kind", "values"}, {}, keyError))
        {
            error = "parameter tuple fields do not match the bridge schema";
            return std::nullopt;
        }
        const QString kind = object.value("value_kind").toString();
        const QJsonArray values = object.value("values").toArray();
        if (object.value("version").toInt(-1) != MODEL_VERSION
            || !QSet<QString>{"integer", "float", "boolean", "string", "menu_token"}.contains(kind)
            || values.isEmpty() || values.size() > 64)
        {
            error = "parameter tuple value fields are invalid";
            return std::nullopt;
        }
        for (const QJsonValue &item : values)
        {
            if (kind == "integer")
            {
                if (!item.isDouble() || std::floor(item.toDouble()) != item.toDouble()
                    || item.toDouble() < std::numeric_limits<int32>::min()
                    || item.toDouble() > std::numeric_limits<int32>::max())
                {
                    error = "integer parameter tuple contains a non-integer";
                    return std::nullopt;
                }
            }
            else if (kind == "float")
            {
                if (!item.isDouble() || !std::isfinite(item.toDouble()))
                {
                    error = "float parameter tuple contains a non-finite value";
                    return std::nullopt;
                }
            }
            else if (kind == "boolean" && !item.isBool())
            {
                error = "boolean parameter tuple contains a non-boolean";
                return std::nullopt;
            }
            else if ((kind == "string" || kind == "menu_token")
                && (!item.isString() || item.toString().size() > 4096
                    || (kind == "menu_token" && item.toString().isEmpty())))
            {
                error = "string parameter tuple contains a non-string";
                return std::nullopt;
            }
        }
        return ParameterState{kind, values};
    }

    std::optional<ConnectionState> parseConnection(
        const QJsonValue &value,
        QString &error) const
    {
        if (value.isNull())
            return std::nullopt;
        if (!value.isObject())
        {
            error = "connection reference must be an object or null";
            return std::nullopt;
        }
        const QJsonObject object = value.toObject();
        QString keyError;
        if (!exactObjectKeys(
                object, {"version", "source", "output_index"}, {}, keyError))
        {
            error = "connection fields do not match the bridge schema";
            return std::nullopt;
        }
        const QString sourceId = referenceId(object.value("source"), error);
        const int outputIndex = object.value("output_index").toInt(-1);
        if (!error.isEmpty())
            return std::nullopt;
        if (object.value("version").toInt(-1) != MODEL_VERSION
            || !integerInRange(object.value("output_index"), 0, 255))
        {
            error = "connection reference fields are invalid";
            return std::nullopt;
        }
        return ConnectionState{sourceId, outputIndex};
    }

    bool siblingNameExists(
        const SceneSnapshot &snapshot,
        const QString &parentId,
        const QString &name,
        const QString &exceptId = {}) const
    {
        for (auto it = snapshot.nodes.cbegin(); it != snapshot.nodes.cend(); ++it)
            if (it->parentId == parentId && it->name == name && it.key() != exceptId)
                return true;
        return false;
    }

    bool parseNodeSpec(
        const QJsonObject &spec,
        const SceneSnapshot &snapshot,
        NodeState &state,
        QString &error) const
    {
        QString keyError;
        if (!exactObjectKeys(
                spec,
                {"version", "entity", "parent", "operator_type", "name", "position", "initial_parameters"},
                {}, keyError)
            || spec.value("version").toInt(-1) != MODEL_VERSION)
        {
            error = "create spec has an unsupported version";
            return false;
        }
        state.id = referenceId(spec.value("entity"), error);
        state.parentId = referenceId(spec.value("parent"), error);
        state.operatorType = spec.value("operator_type").toString();
        state.name = spec.value("name").toString();
        if (!error.isEmpty())
            return false;
        if (!snapshot.nodes.contains(state.parentId))
        {
            error = "create parent identity does not exist";
            return false;
        }
        if (snapshot.nodes.contains(state.id) || tombstones.contains(state.id))
        {
            error = "create identity already exists or is tombstoned";
            return false;
        }
        if (!supportsType(state.operatorType) || !validIdentifier(state.operatorType)
            || !validName(state.name)
            || !OP_Node::isValidOpName(state.name.toUtf8().constData()))
        {
            error = "create type or name is outside the supported capability";
            return false;
        }
        if (siblingNameExists(snapshot, state.parentId, state.name))
        {
            error = "create name collides with an existing sibling";
            return false;
        }
        if (!numericArray2(spec.value("position"), state.x, state.y))
        {
            error = "create position is invalid";
            return false;
        }
        state.path = snapshot.nodes.value(state.parentId).path + "/" + state.name;
        if (!spec.value("initial_parameters").isArray())
        {
            error = "create initial_parameters must be an array";
            return false;
        }
        for (const QJsonValue &parameterValue : spec.value("initial_parameters").toArray())
        {
            if (!parameterValue.isObject())
            {
                error = "create initial parameter must be an object";
                return false;
            }
            const QJsonObject parameter = parameterValue.toObject();
            QString parameterKeyError;
            const QString name = parameter.value("name").toString();
            if (!exactObjectKeys(
                    parameter, {"version", "name", "value"}, {}, parameterKeyError)
                || parameter.value("version").toInt(-1) != MODEL_VERSION
                || !parameterNames.contains(name) || state.parameters.contains(name))
            {
                error = "create initial parameter is unsupported or duplicated";
                return false;
            }
            const auto tuple = parseTupleValue(parameter.value("value"), error);
            if (!tuple)
                return false;
            state.parameters.insert(name, *tuple);
        }
        return true;
    }

    bool prevalidateOperation(
        const QJsonObject &operation,
        SceneSnapshot &staged,
        QString &error) const
    {
        if (operation.value("version").toInt(-1) != MODEL_VERSION
            || !operation.value("operation_id").isString()
            || !validIdentifier(operation.value("operation_id").toString()))
        {
            error = "operation common fields are invalid";
            return false;
        }
        const QString type = operation.value("operation_type").toString();
        if (!SUPPORTED_OPERATIONS.contains(type))
        {
            error = "operation type is unsupported";
            return false;
        }
        QSet<QString> operationFields{"version", "operation_type", "operation_id"};
        if (type == "node.create")
            operationFields.insert("spec");
        else if (type == "subtree.create")
            operationFields.unite({"nodes", "connections"});
        else if (type == "subtree.delete")
            operationFields.unite({"root", "deleted_entity_ids", "expected_parent_id"});
        else if (type == "node.rename")
            operationFields.unite({"entity", "name", "expected_name"});
        else if (type == "node.move")
            operationFields.unite({"entity", "position", "expected_position"});
        else if (type == "node.input.set")
            operationFields.unite({"destination", "input_index", "expected_source", "new_source"});
        else
            operationFields.unite({"entity", "parameter_name", "value", "expected_value"});
        QString operationKeyError;
        if (!exactObjectKeys(operation, operationFields, {}, operationKeyError))
        {
            error = "operation fields do not match the bridge schema";
            return false;
        }

        auto applyCreateSpec = [&](const QJsonObject &spec) -> bool {
            NodeState state;
            if (!parseNodeSpec(spec, staged, state, error))
                return false;
            staged.nodes.insert(state.id, state);
            return true;
        };

        if (type == "node.create")
            return operation.value("spec").isObject()
                && applyCreateSpec(operation.value("spec").toObject());

        if (type == "subtree.create")
        {
            if (!operation.value("nodes").isArray()
                || operation.value("nodes").toArray().isEmpty()
                || operation.value("nodes").toArray().size() > maxNodes
                || !operation.value("connections").isArray())
            {
                error = "subtree create arrays are invalid";
                return false;
            }
            QSet<QString> newIds;
            for (const QJsonValue &specValue : operation.value("nodes").toArray())
            {
                if (!specValue.isObject())
                {
                    error = "subtree node spec must be an object";
                    return false;
                }
                if (!applyCreateSpec(specValue.toObject()))
                    return false;
                const QString id = referenceId(specValue.toObject().value("entity"), error);
                newIds.insert(id);
            }
            for (const QJsonValue &connectionValue : operation.value("connections").toArray())
            {
                if (!connectionValue.isObject())
                {
                    error = "subtree connection must be an object";
                    return false;
                }
                const QJsonObject connection = connectionValue.toObject();
                QString connectionKeyError;
                if (!exactObjectKeys(
                        connection,
                        {"version", "destination", "input_index", "source"},
                        {}, connectionKeyError)
                    || connection.value("version").toInt(-1) != MODEL_VERSION)
                {
                    error = "subtree connection fields do not match the bridge schema";
                    return false;
                }
                const QString destinationId = referenceId(connection.value("destination"), error);
                const int inputIndex = connection.value("input_index").toInt(-1);
                const auto source = parseConnection(connection.value("source"), error);
                if (!error.isEmpty() || !source || !newIds.contains(destinationId)
                    || !staged.nodes.contains(source->sourceId)
                    || !integerInRange(connection.value("input_index"), 0, 255))
                {
                    if (error.isEmpty())
                        error = "subtree connection references invalid endpoints";
                    return false;
                }
                staged.nodes[destinationId].inputs.insert(inputIndex, *source);
            }
            return true;
        }

        if (type == "subtree.delete")
        {
            const QString rootId = referenceId(operation.value("root"), error);
            if (!error.isEmpty() || !staged.nodes.contains(rootId) || rootId == staged.rootId)
            {
                if (error.isEmpty()) error = "delete root does not exist or is the collaboration root";
                return false;
            }
            QStringList actualIds;
            collectDescendants(staged, rootId, actualIds);
            if (!operation.value("deleted_entity_ids").isArray()
                || operation.value("deleted_entity_ids").toArray().isEmpty())
            {
                error = "delete subtree identity set must be a non-empty array";
                return false;
            }
            QJsonArray declared = operation.value("deleted_entity_ids").toArray();
            QStringList declaredIds;
            for (const QJsonValue &value : declared)
            {
                if (!value.isString() || !validIdentifier(value.toString()))
                {
                    error = "delete subtree identity set contains an invalid ID";
                    return false;
                }
                declaredIds.append(value.toString());
            }
            if (declaredIds != actualIds)
            {
                error = "delete subtree identity set is not exact or parent-first";
                return false;
            }
            const QJsonValue expectedParent = operation.value("expected_parent_id");
            if (!expectedParent.isNull()
                && (!expectedParent.isString()
                    || !validIdentifier(expectedParent.toString())
                    || expectedParent.toString() != staged.nodes.value(rootId).parentId))
            {
                error = "delete parent precondition failed";
                return false;
            }
            QSet<QString> deleting(actualIds.begin(), actualIds.end());
            for (const QString &id : actualIds)
                staged.nodes.remove(id);
            for (auto it = staged.nodes.begin(); it != staged.nodes.end(); ++it)
            {
                QList<int> inputs = it->inputs.keys();
                for (int index : inputs)
                    if (deleting.contains(it->inputs.value(index).sourceId))
                        it->inputs.remove(index);
            }
            return true;
        }

        const QJsonValue targetValue = type == "node.input.set"
            ? operation.value("destination") : operation.value("entity");
        const QString targetId = referenceId(targetValue, error);
        if (!error.isEmpty() || !staged.nodes.contains(targetId))
        {
            if (error.isEmpty()) error = "operation target identity does not exist";
            return false;
        }
        NodeState &target = staged.nodes[targetId];
        if (type == "node.rename")
        {
            const QString name = operation.value("name").toString();
            const QJsonValue expected = operation.value("expected_name");
            if ((!expected.isNull() && (!expected.isString()
                    || expected.toString() != target.name))
                || !validName(name) || !OP_Node::isValidOpName(name.toUtf8().constData())
                || siblingNameExists(staged, target.parentId, name, targetId))
            {
                error = "rename precondition, name, or sibling uniqueness failed";
                return false;
            }
            target.name = name;
            target.path = staged.nodes.value(target.parentId).path + "/" + name;
            return true;
        }
        if (type == "node.move")
        {
            double x = 0.0, y = 0.0;
            if (!numericArray2(operation.value("position"), x, y))
            {
                error = "move position is invalid";
                return false;
            }
            if (!operation.value("expected_position").isNull())
            {
                double expectedX = 0.0, expectedY = 0.0;
                if (!numericArray2(operation.value("expected_position"), expectedX, expectedY)
                    || expectedX != target.x || expectedY != target.y)
                {
                    error = "move position precondition failed";
                    return false;
                }
            }
            target.x = x;
            target.y = y;
            return true;
        }
        if (type == "node.input.set")
        {
            const int inputIndex = operation.value("input_index").toInt(-1);
            if (!integerInRange(operation.value("input_index"), 0, 255))
            {
                error = "input index is invalid";
                return false;
            }
            QString parseError;
            const auto expected = parseConnection(operation.value("expected_source"), parseError);
            if (!parseError.isEmpty()) { error = parseError; return false; }
            const auto replacement = parseConnection(operation.value("new_source"), parseError);
            if (!parseError.isEmpty()) { error = parseError; return false; }
            const bool hasCurrent = target.inputs.contains(inputIndex);
            if (expected.has_value() != hasCurrent
                || (expected && target.inputs.value(inputIndex) != *expected)
                || (replacement && !staged.nodes.contains(replacement->sourceId)))
            {
                error = "input connection precondition or source identity failed";
                return false;
            }
            if (replacement)
                target.inputs.insert(inputIndex, *replacement);
            else
                target.inputs.remove(inputIndex);
            return true;
        }

        const QString name = operation.value("parameter_name").toString();
        if (!parameterNames.contains(name) || !target.parameters.contains(name))
        {
            error = "parameter is outside the configured supported set";
            return false;
        }
        const auto replacement = parseTupleValue(operation.value("value"), error);
        if (!replacement)
            return false;
        if (!operation.value("expected_value").isNull())
        {
            const auto expected = parseTupleValue(operation.value("expected_value"), error);
            if (!expected || *expected != target.parameters.value(name))
            {
                if (error.isEmpty()) error = "parameter tuple precondition failed";
                return false;
            }
        }
        if (replacement->values.size() != target.parameters.value(name).values.size()
            || replacement->kind != target.parameters.value(name).kind)
        {
            error = "parameter raw kind or tuple arity does not match Houdini state";
            return false;
        }
        target.parameters.insert(name, *replacement);
        return true;
    }

    bool setParameterValue(
        OP_Node *node,
        const QString &name,
        const ParameterState &value,
        QString &error) const
    {
        PRM_Parm *parm = node && node->getParmList()
            ? node->getParmList()->getParmPtr(UT_StringHolder(name.toUtf8().constData()))
            : nullptr;
        if (!parm || parm->getVectorSize() != value.values.size())
        {
            error = "native parameter tuple is missing or has a different arity";
            return false;
        }
        if (!node->canAccess(PRM_WRITE_OK))
        {
            error = "native parameter target is not writable";
            return false;
        }
        const fpreal time = CHgetEvalTime();
        for (int index = 0; index < value.values.size(); ++index)
        {
            bool changed = false;
            if (value.kind == "integer")
                changed = parm->setValue(time, static_cast<int32>(value.values[index].toInt()), false, index);
            else if (value.kind == "boolean")
                changed = parm->setValue(time, static_cast<int32>(value.values[index].toBool() ? 1 : 0), false, index);
            else if (value.kind == "float")
                changed = parm->setValue(time, static_cast<fpreal>(value.values[index].toDouble()), false, index);
            else if (value.kind == "menu_token" && parm->getType().isOrdinalType())
            {
                const PRM_ChoiceList *choices = parm->getTemplatePtr()->getChoiceListPtr();
                const QString wanted = value.values[index].toString();
                int selectedIndex = -1;
                const int choiceCount = choices ? choices->getSize(parm) : 0;
                for (int choiceIndex = 0; choiceIndex < choiceCount; ++choiceIndex)
                {
                    UT_String token;
                    if (choices->tokenFromIndex(token, choiceIndex, node, nullptr, parm)
                        && QString::fromUtf8(token.c_str()) == wanted)
                    {
                        selectedIndex = choiceIndex;
                        break;
                    }
                }
                if (selectedIndex < 0)
                {
                    error = QString("menu token is unavailable: %1").arg(wanted);
                    return false;
                }
                changed = parm->setValue(time, static_cast<int32>(selectedIndex), false, index);
            }
            else
            {
                const QByteArray bytes = value.values[index].toString().toUtf8();
                changed = parm->setValue(time, bytes.constData(), CH_STRING_LITERAL, false, index);
            }
            if (!changed)
            {
                error = QString("native parameter component %1 was rejected").arg(index);
                return false;
            }
        }
        return true;
    }

    bool applyCreateSpec(
        const QJsonObject &spec,
        SceneSnapshot &live,
        QString &error)
    {
        const QString parentId = referenceId(spec.value("parent"), error);
        const QString entityId = referenceId(spec.value("entity"), error);
        if (!error.isEmpty())
            return false;
        OP_Network *parent = dynamic_cast<OP_Network *>(live.pointers.value(parentId, nullptr));
        if (!parent || !parent->canAccess(PRM_WRITE_OK))
        {
            error = "native create parent is missing, not a network, or not writable";
            return false;
        }
        const QByteArray type = spec.value("operator_type").toString().toUtf8();
        const QByteArray name = spec.value("name").toString().toUtf8();
        OP_Node *node = parent->createNodeOfExactType(type.constData(), name.constData());
        if (!node)
        {
            error = "native exact-type node creation failed";
            return false;
        }
        if (nodeName(node) != QString::fromUtf8(name))
        {
            error = "Houdini changed the requested create name";
            return false;
        }
        QString identityError;
        if (ensureIdentity(node, entityId, identityError) != entityId)
        {
            error = identityError;
            return false;
        }
        double x = 0.0, y = 0.0;
        if (!numericArray2(spec.value("position"), x, y)
            || !node->setXYWithBoundsChecks(x, y))
        {
            error = "native create position was rejected";
            return false;
        }
        for (const QJsonValue &parameterValue : spec.value("initial_parameters").toArray())
        {
            const QJsonObject parameter = parameterValue.toObject();
            const auto value = parseTupleValue(parameter.value("value"), error);
            if (!value || !setParameterValue(node, parameter.value("name").toString(), *value, error))
                return false;
        }
        return extractSnapshot(live, error);
    }

    bool applyOperation(
        const QJsonObject &operation,
        SceneSnapshot &live,
        QString &error)
    {
        const QString type = operation.value("operation_type").toString();
        if (type == "node.create")
            return applyCreateSpec(operation.value("spec").toObject(), live, error);
        if (type == "subtree.create")
        {
            for (const QJsonValue &spec : operation.value("nodes").toArray())
                if (!applyCreateSpec(spec.toObject(), live, error))
                    return false;
            for (const QJsonValue &connectionValue : operation.value("connections").toArray())
            {
                const QJsonObject connection = connectionValue.toObject();
                const QString destinationId = referenceId(connection.value("destination"), error);
                const auto source = parseConnection(connection.value("source"), error);
                const int inputIndex = connection.value("input_index").toInt(-1);
                OP_Node *destination = live.pointers.value(destinationId, nullptr);
                OP_Node *sourceNode = source ? live.pointers.value(source->sourceId, nullptr) : nullptr;
                if (!error.isEmpty() || !destination || !sourceNode
                    || destination->setInput(inputIndex, sourceNode, source->outputIndex) != UT_ERROR_NONE)
                {
                    if (error.isEmpty()) error = "native subtree connection failed";
                    return false;
                }
            }
            return extractSnapshot(live, error);
        }

        const QJsonValue targetValue = type == "subtree.delete" ? operation.value("root")
            : type == "node.input.set" ? operation.value("destination")
            : operation.value("entity");
        const QString targetId = referenceId(targetValue, error);
        OP_Node *target = live.pointers.value(targetId, nullptr);
        if (!error.isEmpty() || !target)
        {
            if (error.isEmpty()) error = "native target identity lookup failed";
            return false;
        }
        if (type == "subtree.delete")
        {
            OP_Network *parent = target->getParent();
            if (!parent || !OP_Network::canDestroyNode(target))
            {
                error = "native delete target cannot be destroyed";
                return false;
            }
            for (const QJsonValue &idValue : operation.value("deleted_entity_ids").toArray())
            {
                const QString id = idValue.toString();
                const NodeState deletedNode = live.nodes.value(id);
                tombstones.insert(id, TombstoneState{deletedNode.parentId, deletedNode.path});
            }
            parent->destroyNode(target);
        }
        else if (type == "node.rename")
        {
            OP_Network *parent = target->getParent();
            const QByteArray name = operation.value("name").toString().toUtf8();
            if (!parent || !target->canAccess(PRM_WRITE_OK))
            {
                error = "native rename target is not writable";
                return false;
            }
            parent->renameNode(target, name.constData());
            if (nodeName(target) != QString::fromUtf8(name))
            {
                error = "native rename did not produce the requested name";
                return false;
            }
        }
        else if (type == "node.move")
        {
            double x = 0.0, y = 0.0;
            if (!numericArray2(operation.value("position"), x, y)
                || !target->setXYWithBoundsChecks(x, y))
            {
                error = "native move was rejected";
                return false;
            }
        }
        else if (type == "node.input.set")
        {
            const auto source = parseConnection(operation.value("new_source"), error);
            OP_Node *sourceNode = source ? live.pointers.value(source->sourceId, nullptr) : nullptr;
            if (!error.isEmpty()
                || target->setInput(
                    operation.value("input_index").toInt(),
                    sourceNode,
                    source ? source->outputIndex : 0) != UT_ERROR_NONE)
            {
                if (error.isEmpty()) error = "native input change was rejected";
                return false;
            }
        }
        else
        {
            const auto value = parseTupleValue(operation.value("value"), error);
            if (!value || !setParameterValue(
                target, operation.value("parameter_name").toString(), *value, error))
                return false;
        }
        return extractSnapshot(live, error);
    }

    bool verifySnapshots(
        const SceneSnapshot &expected,
        const SceneSnapshot &actual,
        QJsonObject &mismatch) const
    {
        QSet<QString> expectedIds(expected.nodes.keyBegin(), expected.nodes.keyEnd());
        QSet<QString> actualIds(actual.nodes.keyBegin(), actual.nodes.keyEnd());
        if (expectedIds != actualIds)
        {
            mismatch = {{"property", "entity_ids"}, {"expected_count", expectedIds.size()}, {"actual_count", actualIds.size()}};
            return false;
        }
        for (const QString &id : expectedIds)
        {
            const NodeState &wanted = expected.nodes.value(id);
            const NodeState &found = actual.nodes.value(id);
            auto fail = [&](const QString &property, const QJsonValue &expectedValue, const QJsonValue &actualValue) {
                mismatch = {{"entity_id", id}, {"property", property}, {"expected", expectedValue}, {"actual", actualValue}};
                return false;
            };
            if (wanted.parentId != found.parentId) return fail("parent_id", wanted.parentId, found.parentId);
            if (wanted.operatorType != found.operatorType) return fail("operator_type", wanted.operatorType, found.operatorType);
            if (wanted.name != found.name) return fail("name", wanted.name, found.name);
            if (std::abs(wanted.x - found.x) > 1e-9 || std::abs(wanted.y - found.y) > 1e-9)
                return fail("position", QJsonArray{wanted.x, wanted.y}, QJsonArray{found.x, found.y});
            if (wanted.inputs != found.inputs)
            {
                auto inputsJson = [](const QMap<int, ConnectionState> &inputs) {
                    QJsonObject result;
                    for (auto input = inputs.cbegin(); input != inputs.cend(); ++input)
                        result.insert(QString::number(input.key()), QJsonObject{
                            {"source_entity_id", input->sourceId},
                            {"output_index", input->outputIndex},
                        });
                    return result;
                };
                return fail("inputs", inputsJson(wanted.inputs), inputsJson(found.inputs));
            }
            for (auto parameter = wanted.parameters.cbegin(); parameter != wanted.parameters.cend(); ++parameter)
            {
                if (!found.parameters.contains(parameter.key())
                    || found.parameters.value(parameter.key()) != parameter.value())
                    return fail(
                        QString("parameter:%1").arg(parameter.key()),
                        parameter.value().json(),
                        found.parameters.contains(parameter.key())
                            ? QJsonValue(found.parameters.value(parameter.key()).json())
                            : QJsonValue(QJsonValue::Null));
            }
        }
        return true;
    }

    QJsonObject applyRequest(const QJsonObject &request)
    {
        const QJsonObject transaction = request.value("transaction").toObject();
        const QString transactionId = transaction.value("transaction_id").toString();
        const QString hash = semanticHash(transaction);
        QString transactionKeyError;
        if (!exactObjectKeys(
                transaction,
                {"version", "transaction_id", "author_client_id", "session_id", "operations", "activity_label", "required_operation_types"},
                {}, transactionKeyError)
            || transaction.value("version").toInt(-1) != MODEL_VERSION
            || !validIdentifier(transactionId)
            || !validIdentifier(transaction.value("author_client_id").toString())
            || !validIdentifier(transaction.value("session_id").toString())
            || !transaction.value("operations").isArray()
            || transaction.value("operations").toArray().isEmpty()
            || transaction.value("operations").toArray().size() > 256
            || !transaction.value("required_operation_types").isArray()
            || (!transaction.value("activity_label").isNull()
                && (!transaction.value("activity_label").isString()
                    || transaction.value("activity_label").toString().isEmpty()
                    || transaction.value("activity_label").toString().size() > 256)))
            return coophouBridgeError("SCHEMA_INVALID", "transaction fields are invalid");
        if (appliedHashes.contains(transactionId))
        {
            if (appliedHashes.value(transactionId) != hash)
                return coophouBridgeError("DUPLICATE_CONFLICT", "transaction ID was reused with different content");
            return coophouBridgeSuccess({
                {"status", "APPLIED_REPLAY"},
                {"transaction_id", transactionId},
                {"changed", false},
            });
        }

        QString error;
        SceneSnapshot before;
        if (!extractSnapshot(before, error))
            return coophouBridgeError("APPLICATION_PREVALIDATION_FAILED", error);
        SceneSnapshot expected = before;
        QStringList operationIds;
        QSet<QString> operationTypes;
        QSet<QString> requiredTypes;
        for (const QJsonValue &required : transaction.value("required_operation_types").toArray())
        {
            const QString type = required.toString();
            if (!required.isString() || !SUPPORTED_OPERATIONS.contains(type)
                || requiredTypes.contains(type))
                return coophouBridgeError("TRANSACTION_INVALID", "transaction capability requirements are invalid");
            requiredTypes.insert(type);
        }
        const QJsonArray operations = transaction.value("operations").toArray();
        for (int index = 0; index < operations.size(); ++index)
        {
            if (!operations[index].isObject())
                return coophouBridgeError("SCHEMA_INVALID", "transaction operation must be an object", {{"operation_index", index}});
            const QJsonObject operation = operations[index].toObject();
            const QString operationId = operation.value("operation_id").toString();
            if (operationIds.contains(operationId))
                return coophouBridgeError("TRANSACTION_INVALID", "transaction contains duplicate operation IDs");
            operationIds.append(operationId);
            operationTypes.insert(operation.value("operation_type").toString());
            if (!prevalidateOperation(operation, expected, error))
                return coophouBridgeError(
                    "APPLICATION_PREVALIDATION_FAILED",
                    error,
                    {{"transaction_id", transactionId}, {"operation_id", operationId}, {"operation_index", index}, {"scene_generation", sceneGeneration}});
        }
        if (!requiredTypes.isEmpty() && !operationTypes.subtract(requiredTypes).isEmpty())
            return coophouBridgeError("TRANSACTION_INVALID", "transaction capability requirements omit an operation type");

        currentTransactionId = transactionId;
        currentOperationIds = operationIds;
        ++remoteApplyDepth;
        SceneSnapshot live = before;
        int failedIndex = -1;
        QString failedOperationId;
        bool failedBeforeOperation = false;
        for (int index = 0; index < operations.size(); ++index)
        {
            if (faultOperationIndex == index)
            {
                error = "injected native operation-boundary failure";
                failedIndex = index;
                failedOperationId = operationIds[index];
                failedBeforeOperation = true;
                break;
            }
            if (!applyOperation(operations[index].toObject(), live, error))
            {
                failedIndex = index;
                failedOperationId = operationIds[index];
                break;
            }
        }
        --remoteApplyDepth;
        currentTransactionId.clear();
        currentOperationIds.clear();
        if (failedIndex >= 0)
        {
            reconciliationRequired = true;
            return coophouBridgeError(
                "RECONCILIATION_REQUIRED",
                "unexpected partial native application; normal advancement stopped",
                {{"cause", error}, {"transaction_id", transactionId}, {"operation_id", failedOperationId}, {"operation_index", failedIndex}, {"scene_generation", sceneGeneration}, {"partial_apply", failedBeforeOperation ? failedIndex > 0 : true}});
        }

        QJsonObject mismatch;
        if (!verifySnapshots(expected, live, mismatch))
        {
            reconciliationRequired = true;
            mismatch["transaction_id"] = transactionId;
            mismatch["operation_id"] = operationIds.isEmpty()
                ? QJsonValue(QJsonValue::Null)
                : QJsonValue(operationIds.last());
            mismatch["scene_generation"] = sceneGeneration;
            return coophouBridgeError(
                "RECONCILIATION_REQUIRED",
                "native post-apply semantic verification failed",
                mismatch);
        }
        live.pointers.clear();
        mirror = live;
        dirty = false;
        broadSettle = false;
        affectedScopes.clear();
        targetedPaths.clear();
        predeleteIds.clear();
        appliedHashes.insert(transactionId, hash);
        appliedOrder.append(transactionId);
        while (appliedOrder.size() > appliedHistoryLimit)
            appliedHashes.remove(appliedOrder.takeFirst());
        return coophouBridgeSuccess({
            {"status", "APPLIED_VERIFIED"},
            {"transaction_id", transactionId},
            {"changed", true},
            {"operation_count", operations.size()},
            {"scene_generation", sceneGeneration},
            {"apply_sequence", ++applySequence},
        });
    }

    void enqueueCaptureRecord(const QJsonObject &record)
    {
        if (static_cast<int>(captureQueue.size()) >= captureLimit)
        {
            captureOverflow = true;
            reconciliationRequired = true;
            return;
        }
        captureQueue.push_back(record);
    }
};

NativeAdapter::NativeAdapter()
    : myImpl(new Impl())
{
}

NativeAdapter::~NativeAdapter()
{
    delete myImpl;
}

NativeAdapter &
NativeAdapter::instance()
{
    static NativeAdapter adapter;
    return adapter;
}

QJsonObject
NativeAdapter::capabilities() const
{
    std::lock_guard<std::recursive_mutex> lock(myImpl->mutex);
    QJsonArray operationTypes;
    QStringList operations = SUPPORTED_OPERATIONS.values();
    std::sort(operations.begin(), operations.end());
    for (const QString &operation : operations)
        operationTypes.append(operation);
    return coophouBridgeSuccess({
        {"houdini_version", SYS_VERSION_FULL},
        {"houdini_build", SYS_VERSION_BUILD_INT},
        {"hdk_api_version", HDK_API_VERSION},
        {"platform", platformName()},
        {"bridge_schema_version", BRIDGE_SCHEMA_VERSION},
        {"production_adapter", "hdk_cpp"},
        {"capture_source", "OP_Director.global_and_lifecycle"},
        {"application_gateway", "native_main_thread_bounded"},
        {"supported_snapshot_extractor", "native_scoped_v1"},
        {"operation_types", operationTypes},
        {"dso_unload_claimed", false},
        {"undo_behavior_claimed", false},
    });
}

QJsonObject
NativeAdapter::startCapture(const QJsonObject &request)
{
    std::lock_guard<std::recursive_mutex> lock(myImpl->mutex);
    QString keyError;
    if (!exactObjectKeys(
            request,
            {"bridge_schema_version"},
            {"root_path", "root_entity_id", "deterministic_id_prefix", "operator_types", "parameter_names", "parameter_kinds", "max_nodes", "capture_queue_limit", "apply_queue_limit"},
            keyError))
        return coophouBridgeError("SCHEMA_INVALID", keyError);
    if (request.value("bridge_schema_version").toInt(-1) != BRIDGE_SCHEMA_VERSION)
        return coophouBridgeError("BRIDGE_UNSUPPORTED_VERSION", "unsupported bridge schema version");
    if (!UT_Thread::isMainThread())
        return coophouBridgeError("MAIN_THREAD_REQUIRED", "capture start must run on Houdini's main thread");
    if (myImpl->active)
        return coophouBridgeSuccess({{"already_started", true}, {"scene_generation", myImpl->sceneGeneration}});

    if ((request.contains("operator_types") && !request.value("operator_types").isArray())
        || (request.contains("parameter_names") && !request.value("parameter_names").isArray())
        || (request.contains("parameter_kinds") && !request.value("parameter_kinds").isObject())
        || (request.contains("root_path") && !request.value("root_path").isString())
        || (request.contains("root_entity_id") && !request.value("root_entity_id").isString()))
        return coophouBridgeError("SCHEMA_INVALID", "capture configuration field types are invalid");

    auto validBound = [&request](const char *name, int minimum, int maximum) {
        if (!request.contains(name))
            return true;
        const QJsonValue value = request.value(name);
        return value.isDouble() && std::floor(value.toDouble()) == value.toDouble()
            && value.toDouble() >= minimum && value.toDouble() <= maximum;
    };
    if (!validBound("max_nodes", 1, 100000)
        || !validBound("capture_queue_limit", 1, 65536)
        || !validBound("apply_queue_limit", 1, 4096))
        return coophouBridgeError("SCHEMA_INVALID", "capture configuration bounds are invalid");

    myImpl->rootPath = request.value("root_path").toString("/obj");
    myImpl->rootEntityId = request.value("root_entity_id").toString("root");
    myImpl->deterministicPrefix = request.value("deterministic_id_prefix").toString();
    if (myImpl->rootPath.isEmpty() || !myImpl->rootPath.startsWith('/')
        || (myImpl->rootPath.size() > 1 && myImpl->rootPath.endsWith('/'))
        || myImpl->rootPath.size() > 1024 || myImpl->rootEntityId != "root"
        || (!myImpl->deterministicPrefix.isEmpty()
            && !validIdentifier(myImpl->deterministicPrefix)))
        return coophouBridgeError("SCHEMA_INVALID", "capture root or ID configuration is invalid");
    myImpl->deterministicCounter = 0;
    myImpl->maxNodes = std::clamp(request.value("max_nodes").toInt(DEFAULT_MAX_NODES), 1, 100000);
    myImpl->captureLimit = std::clamp(request.value("capture_queue_limit").toInt(DEFAULT_CAPTURE_LIMIT), 1, 65536);
    myImpl->applyLimit = std::clamp(request.value("apply_queue_limit").toInt(DEFAULT_APPLY_LIMIT), 1, 4096);
    myImpl->parameterNames.clear();
    for (const QJsonValue &value : request.value("parameter_names").toArray())
    {
        if (!value.isString() || !validName(value.toString()))
            return coophouBridgeError("SCHEMA_INVALID", "parameter_names contains an invalid value");
        if (!myImpl->parameterNames.contains(value.toString()))
            myImpl->parameterNames.append(value.toString());
    }
    myImpl->parameterKinds.clear();
    const QJsonObject kinds = request.value("parameter_kinds").toObject();
    for (auto it = kinds.begin(); it != kinds.end(); ++it)
    {
        const QString kind = it.value().toString();
        if (!myImpl->parameterNames.contains(it.key())
            || !QSet<QString>{"integer", "float", "boolean", "string", "menu_token"}.contains(kind))
            return coophouBridgeError("SCHEMA_INVALID", "parameter_kinds contains an unknown raw kind");
        myImpl->parameterKinds.insert(it.key(), kind);
    }
    if (request.contains("operator_types"))
    {
        myImpl->operatorTypes.clear();
        for (const QJsonValue &value : request.value("operator_types").toArray())
        {
            if (!value.isString() || !validIdentifier(value.toString()))
                return coophouBridgeError("SCHEMA_INVALID", "operator_types contains an invalid value");
            myImpl->operatorTypes.insert(value.toString());
        }
    }

    myImpl->captureQueue.clear();
    myImpl->applyQueue.clear();
    myImpl->captureOverflow = false;
    myImpl->applyOverflow = false;
    myImpl->reconciliationRequired = false;
    myImpl->callbackHandlerNsTotal.store(0, std::memory_order_relaxed);
    myImpl->callbackHandlerNsMax.store(0, std::memory_order_relaxed);
    myImpl->extractionCount = 0;
    myImpl->extractionNsTotal = 0;
    myImpl->extractionNsMax = 0;
    myImpl->dirty = false;
    myImpl->broadSettle = false;
    myImpl->affectedScopes.clear();
    myImpl->targetedPaths.clear();
    myImpl->predeleteIds.clear();
    if (!Watcher::start())
        return coophouBridgeError("CAPTURE_START_FAILED", "native watcher could not start");
    myImpl->sceneGeneration = Watcher::sceneGeneration();
    QString error;
    SceneSnapshot initial;
    if (!myImpl->extractSnapshot(initial, error))
    {
        Watcher::stop();
        return coophouBridgeError("CAPTURE_BOOTSTRAP_FAILED", error);
    }
    initial.pointers.clear();
    myImpl->mirror = initial;
    myImpl->active = true;
    return coophouBridgeSuccess({
        {"already_started", false},
        {"root_path", myImpl->rootPath},
        {"root_entity_id", myImpl->mirror.rootId},
        {"scene_generation", myImpl->sceneGeneration},
        {"mirrored_nodes", myImpl->mirror.nodes.size()},
    });
}

QJsonObject
NativeAdapter::stopCapture()
{
    std::lock_guard<std::recursive_mutex> lock(myImpl->mutex);
    const bool wasActive = myImpl->active;
    myImpl->active = false;
    myImpl->dirty = false;
    myImpl->broadSettle = false;
    myImpl->remoteApplyDepth = 0;
    myImpl->identityWriteDepth = 0;
    myImpl->affectedScopes.clear();
    myImpl->targetedPaths.clear();
    myImpl->predeleteIds.clear();
    myImpl->captureQueue.clear();
    myImpl->applyQueue.clear();
    myImpl->mirror = SceneSnapshot{};
    myImpl->tombstones.clear();
    myImpl->appliedHashes.clear();
    myImpl->appliedOrder.clear();
    myImpl->currentTransactionId.clear();
    myImpl->currentOperationIds.clear();
    if (!Watcher::stop())
        return coophouBridgeError("CAPTURE_STOP_FAILED", "native watcher could not stop cleanly");
    return coophouBridgeSuccess({{"was_started", wasActive}});
}

QJsonObject
NativeAdapter::captureState() const
{
    std::lock_guard<std::recursive_mutex> lock(myImpl->mutex);
    return coophouBridgeSuccess({
        {"active", myImpl->active},
        {"dirty", myImpl->dirty},
        {"scene_generation", myImpl->sceneGeneration},
        {"capture_queue_size", static_cast<qint64>(myImpl->captureQueue.size())},
        {"apply_queue_size", static_cast<qint64>(myImpl->applyQueue.size())},
        {"capture_overflow", myImpl->captureOverflow},
        {"apply_overflow", myImpl->applyOverflow},
        {"reconciliation_required", myImpl->reconciliationRequired},
        {"events_seen", myImpl->eventCount},
        {"events_ignored", myImpl->ignoredEventCount},
        {"expected_echoes_suppressed", myImpl->suppressedEchoCount},
        {"identity_events_suppressed", myImpl->internalIdentityEventCount},
        {"settle_count", myImpl->settleCount},
        {"callback_handler_ns_total", myImpl->callbackHandlerNsTotal.load(std::memory_order_relaxed)},
        {"callback_handler_ns_max", myImpl->callbackHandlerNsMax.load(std::memory_order_relaxed)},
        {"snapshot_extraction_count", myImpl->extractionCount},
        {"snapshot_extraction_ns_total", myImpl->extractionNsTotal},
        {"snapshot_extraction_ns_max", myImpl->extractionNsMax},
        {"mirrored_nodes", myImpl->mirror.nodes.size()},
        {"tombstones", myImpl->tombstones.size()},
    });
}

void
NativeAdapter::recordEvent(OP_Node *node, OP_EventType reason)
{
    AtomicDuration duration(myImpl->callbackHandlerNsTotal, myImpl->callbackHandlerNsMax);
    std::lock_guard<std::recursive_mutex> lock(myImpl->mutex);
    if (!myImpl->active)
        return;
    ++myImpl->eventCount;
    if (myImpl->identityWriteDepth > 0)
    {
        ++myImpl->internalIdentityEventCount;
        return;
    }
    if (myImpl->remoteApplyDepth > 0)
    {
        ++myImpl->suppressedEchoCount;
        return;
    }

    const bool supportedSignal = reason == OP_CHILD_CREATED
        || reason == OP_NODE_PREDELETE
        || reason == OP_NAME_CHANGED
        || reason == OP_UI_MOVED
        || reason == OP_INPUT_CHANGED
        || reason == OP_INPUT_REWIRED
        || reason == OP_PARM_CHANGED;
    if (!supportedSignal)
    {
        ++myImpl->ignoredEventCount;
        return;
    }
    const QString path = nodePath(node);
    if (!pathWithinRoot(path, myImpl->rootPath))
        return;

    myImpl->dirty = true;
    const bool structuralSignal = reason == OP_CHILD_CREATED
        || reason == OP_NODE_PREDELETE;
    if (structuralSignal)
        myImpl->broadSettle = true;
    else
        myImpl->targetedPaths.insert(path);
    QString scope = reason == OP_CHILD_CREATED
        ? path : nodePath(node ? node->getParent() : nullptr);
    if (!pathWithinRoot(scope, myImpl->rootPath))
        scope = myImpl->rootPath;
    myImpl->affectedScopes.insert(scope);
    if (reason == OP_NODE_PREDELETE && node)
    {
        QVector<OP_Node *> pending{node};
        int cursor = 0;
        while (cursor < pending.size() && cursor < myImpl->maxNodes)
        {
            OP_Node *current = pending[cursor++];
            const QString id = nodeEntityId(current);
            if (!id.isEmpty())
                myImpl->predeleteIds.insert(id);
            for (int index = 0; index < current->getNchildren(); ++index)
                if (OP_Node *child = current->getChild(index))
                    pending.append(child);
        }
    }
}

void
NativeAdapter::recordLifecycle(const QString &event, std::int64_t sceneGeneration)
{
    std::lock_guard<std::recursive_mutex> lock(myImpl->mutex);
    myImpl->sceneGeneration = sceneGeneration;
    if (!myImpl->active)
        return;
    if (event == "AfterClear" || event == "AfterLoad")
    {
        myImpl->captureQueue.clear();
        myImpl->applyQueue.clear();
        myImpl->mirror = SceneSnapshot{};
        myImpl->tombstones.clear();
        myImpl->affectedScopes.clear();
        myImpl->targetedPaths.clear();
        myImpl->predeleteIds.clear();
        myImpl->dirty = true;
        myImpl->broadSettle = true;
        myImpl->affectedScopes.insert(myImpl->rootPath);
        myImpl->enqueueCaptureRecord({
            {"bridge_schema_version", BRIDGE_SCHEMA_VERSION},
            {"record_type", "scene.replaced"},
            {"scene_generation", sceneGeneration},
            {"lifecycle_event", event},
        });
    }
    else if (event == "AfterMerge")
    {
        myImpl->dirty = true;
        myImpl->broadSettle = true;
        myImpl->affectedScopes.insert(myImpl->rootPath);
        myImpl->enqueueCaptureRecord({
            {"bridge_schema_version", BRIDGE_SCHEMA_VERSION},
            {"record_type", "scene.merge_requires_settle"},
            {"scene_generation", sceneGeneration},
        });
    }
}

QJsonObject
NativeAdapter::flushSettle()
{
    std::lock_guard<std::recursive_mutex> lock(myImpl->mutex);
    if (!UT_Thread::isMainThread())
        return coophouBridgeError("MAIN_THREAD_REQUIRED", "capture settle must run on Houdini's main thread");
    if (!myImpl->active)
        return coophouBridgeError("CAPTURE_NOT_STARTED", "native capture is not active");
    if (myImpl->captureOverflow)
        return coophouBridgeError("QUEUE_OVERFLOW", "capture queue overflow requires reconciliation");
    if (!myImpl->dirty)
        return coophouBridgeSuccess({{"settled", false}, {"operation_count", 0}});

    QString extractionError;
    SceneSnapshot current;
    const bool extracted = myImpl->broadSettle || myImpl->mirror.nodes.isEmpty()
        ? myImpl->extractSnapshot(current, extractionError)
        : myImpl->extractTargetedSnapshot(
            myImpl->mirror, myImpl->targetedPaths, current, extractionError);
    if (!extracted)
    {
        myImpl->reconciliationRequired = true;
        return coophouBridgeError("CAPTURE_EXTRACTION_FAILED", extractionError);
    }
    QString diffError;
    const QJsonArray operations = myImpl->mirror.nodes.isEmpty()
        ? QJsonArray{} : myImpl->diff(myImpl->mirror, current, diffError);
    if (!diffError.isEmpty())
    {
        myImpl->reconciliationRequired = true;
        return coophouBridgeError("CAPTURE_UNSUPPORTED_CHANGE", diffError);
    }
    ++myImpl->settleCount;
    if (!operations.isEmpty())
    {
        QJsonArray scopes;
        QStringList sortedScopes = myImpl->affectedScopes.values();
        std::sort(sortedScopes.begin(), sortedScopes.end());
        for (const QString &scope : sortedScopes)
            scopes.append(scope);
        myImpl->enqueueCaptureRecord({
            {"bridge_schema_version", BRIDGE_SCHEMA_VERSION},
            {"record_type", "capture.change_set"},
            {"scene_generation", myImpl->sceneGeneration},
            {"capture_sequence", ++myImpl->captureSequence},
            {"affected_scopes", scopes},
            {"operations", operations},
            {"diagnostics", QJsonObject{
                {"events_seen_total", myImpl->eventCount},
                {"settle_count", myImpl->settleCount},
            }},
        });
    }
    current.pointers.clear();
    myImpl->mirror = current;
    myImpl->dirty = false;
    myImpl->broadSettle = false;
    myImpl->affectedScopes.clear();
    myImpl->targetedPaths.clear();
    myImpl->predeleteIds.clear();
    return coophouBridgeSuccess({
        {"settled", true},
        {"operation_count", operations.size()},
        {"mirrored_nodes", current.nodes.size()},
    });
}

QJsonObject
NativeAdapter::extractSupportedSnapshot(const QJsonObject &request)
{
    std::lock_guard<std::recursive_mutex> lock(myImpl->mutex);
    QString keyError;
    if (!exactObjectKeys(request, {"bridge_schema_version"}, {}, keyError))
        return coophouBridgeError("SCHEMA_INVALID", keyError);
    if (request.value("bridge_schema_version").toInt(-1) != BRIDGE_SCHEMA_VERSION)
        return coophouBridgeError("BRIDGE_UNSUPPORTED_VERSION", "unsupported bridge schema version");
    if (!UT_Thread::isMainThread())
        return coophouBridgeError("MAIN_THREAD_REQUIRED", "snapshot extraction must run on Houdini's main thread");
    if (!myImpl->active)
        return coophouBridgeError("CAPTURE_NOT_STARTED", "native adapter is not active");
    QString error;
    SceneSnapshot snapshot;
    if (!myImpl->extractSnapshot(snapshot, error))
    {
        myImpl->reconciliationRequired = true;
        return coophouBridgeError("SNAPSHOT_EXTRACTION_FAILED", error);
    }
    return coophouBridgeSuccess(supportedSnapshotJson(
        snapshot,
        myImpl->tombstones,
        myImpl->rootPath,
        myImpl->sceneGeneration));
}

QJsonObject
NativeAdapter::drainCapture(const QJsonObject &request)
{
    std::lock_guard<std::recursive_mutex> lock(myImpl->mutex);
    QString keyError;
    if (!exactObjectKeys(request, {"bridge_schema_version", "max_count"}, {}, keyError))
        return coophouBridgeError("SCHEMA_INVALID", keyError);
    if (request.value("bridge_schema_version").toInt(-1) != BRIDGE_SCHEMA_VERSION)
        return coophouBridgeError("BRIDGE_UNSUPPORTED_VERSION", "unsupported bridge schema version");
    if (!integerInRange(request.value("max_count"), 1, 4096))
        return coophouBridgeError("SCHEMA_INVALID", "capture drain bound is invalid");
    const int maxCount = std::clamp(request.value("max_count").toInt(64), 1, 4096);
    QJsonArray records;
    while (!myImpl->captureQueue.empty() && records.size() < maxCount)
    {
        records.append(myImpl->captureQueue.front());
        myImpl->captureQueue.pop_front();
    }
    return coophouBridgeSuccess({
        {"records", records},
        {"remaining", static_cast<qint64>(myImpl->captureQueue.size())},
        {"overflow", myImpl->captureOverflow},
    });
}

QJsonObject
NativeAdapter::enqueueApply(const QJsonObject &request)
{
    std::lock_guard<std::recursive_mutex> lock(myImpl->mutex);
    QString keyError;
    if (!exactObjectKeys(
            request,
            {"bridge_schema_version", "scene_generation", "correlation_id", "transaction"},
            {}, keyError))
        return coophouBridgeError("SCHEMA_INVALID", keyError);
    if (request.value("bridge_schema_version").toInt(-1) != BRIDGE_SCHEMA_VERSION)
        return coophouBridgeError("BRIDGE_UNSUPPORTED_VERSION", "unsupported bridge schema version");
    if (!request.value("transaction").isObject()
        || !integerInRange(request.value("scene_generation"), 1, 9007199254740991LL)
        || !request.value("correlation_id").isString()
        || !validIdentifier(request.value("correlation_id").toString()))
        return coophouBridgeError("SCHEMA_INVALID", "apply request fields are invalid");
    if (static_cast<std::int64_t>(request.value("scene_generation").toDouble()) != myImpl->sceneGeneration)
        return coophouBridgeError("STALE_SCENE_GENERATION", "apply request targets a stale scene generation");
    if (myImpl->reconciliationRequired)
        return coophouBridgeError("RECONCILIATION_REQUIRED", "native adapter has stopped normal application");
    if (static_cast<int>(myImpl->applyQueue.size()) >= myImpl->applyLimit)
    {
        myImpl->applyOverflow = true;
        myImpl->reconciliationRequired = true;
        return coophouBridgeError("QUEUE_OVERFLOW", "application queue is full");
    }
    myImpl->applyQueue.push_back(request);
    return coophouBridgeSuccess({
        {"queued", true},
        {"queue_size", static_cast<qint64>(myImpl->applyQueue.size())},
    });
}

QJsonObject
NativeAdapter::drainApply(const QJsonObject &request)
{
    std::lock_guard<std::recursive_mutex> lock(myImpl->mutex);
    QString keyError;
    if (!exactObjectKeys(
            request,
            {"bridge_schema_version", "max_transactions", "max_operations"},
            {}, keyError))
        return coophouBridgeError("SCHEMA_INVALID", keyError);
    if (request.value("bridge_schema_version").toInt(-1) != BRIDGE_SCHEMA_VERSION)
        return coophouBridgeError("BRIDGE_UNSUPPORTED_VERSION", "unsupported bridge schema version");
    if (!UT_Thread::isMainThread())
        return coophouBridgeError("MAIN_THREAD_REQUIRED", "native application must drain on Houdini's main thread");
    if (!myImpl->active)
        return coophouBridgeError("CAPTURE_NOT_STARTED", "native adapter is not active");
    if (myImpl->reconciliationRequired)
        return coophouBridgeError("RECONCILIATION_REQUIRED", "native adapter has stopped normal application");
    if (!integerInRange(request.value("max_transactions"), 1, 128)
        || !integerInRange(request.value("max_operations"), 1, 4096))
        return coophouBridgeError("SCHEMA_INVALID", "application drain bounds are invalid");
    const int maxTransactions = std::clamp(
        request.value("max_transactions").toInt(8), 1, 128);
    const int maxOperations = std::clamp(
        request.value("max_operations").toInt(64), 1, 4096);
    int operationBudget = maxOperations;
    QJsonArray results;
    while (!myImpl->applyQueue.empty()
        && results.size() < maxTransactions)
    {
        const QJsonObject &queued = myImpl->applyQueue.front();
        const int operationCount = queued.value("transaction").toObject()
            .value("operations").toArray().size();
        if (!results.isEmpty() && operationCount > operationBudget)
            break;
        if (operationCount > maxOperations)
        {
            myImpl->reconciliationRequired = true;
            return coophouBridgeError(
                "DRAIN_BUDGET_EXCEEDED",
                "one queued transaction exceeds the bounded operation slice",
                {{"operation_count", operationCount}, {"max_operations", maxOperations}});
        }
        QJsonObject requestCopy = queued;
        myImpl->applyQueue.pop_front();
        QJsonObject result = myImpl->applyRequest(requestCopy);
        result["correlation_id"] = requestCopy.value("correlation_id");
        results.append(result);
        operationBudget -= operationCount;
        if (!result.value("ok").toBool())
            break;
    }
    return coophouBridgeSuccess({
        {"results", results},
        {"remaining", static_cast<qint64>(myImpl->applyQueue.size())},
        {"operation_budget_remaining", operationBudget},
    });
}

QJsonObject
NativeAdapter::resetForTests(const QJsonObject &request)
{
    std::lock_guard<std::recursive_mutex> lock(myImpl->mutex);
    QString keyError;
    if (!exactObjectKeys(
            request,
            {"bridge_schema_version", "fault_operation_index"},
            {}, keyError))
        return coophouBridgeError("SCHEMA_INVALID", keyError);
    if (request.value("bridge_schema_version").toInt(-1) != BRIDGE_SCHEMA_VERSION)
        return coophouBridgeError("BRIDGE_UNSUPPORTED_VERSION", "unsupported bridge schema version");
    if (!integerInRange(request.value("fault_operation_index"), -1, 255))
        return coophouBridgeError("SCHEMA_INVALID", "fault operation index is invalid");
    myImpl->faultOperationIndex = request.value("fault_operation_index").toInt(-1);
    myImpl->captureOverflow = false;
    myImpl->applyOverflow = false;
    myImpl->reconciliationRequired = false;
    myImpl->captureQueue.clear();
    myImpl->applyQueue.clear();
    myImpl->dirty = false;
    myImpl->broadSettle = false;
    myImpl->affectedScopes.clear();
    myImpl->targetedPaths.clear();
    myImpl->predeleteIds.clear();
    myImpl->appliedHashes.clear();
    myImpl->appliedOrder.clear();
    return coophouBridgeSuccess({{"fault_operation_index", myImpl->faultOperationIndex}});
}
