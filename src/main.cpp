#include <PY/PY_CPythonAPI.h>

#include "native_adapter.h"
#include "utils.h"
#include "watcher.h"

#include <iostream>

#include <HOM/HOM_Module.h>
#include <PY/PY_AutoObject.h>
#include <PY/PY_InterpreterAutoLock.h>
#include <UT/UT_DSOVersion.h>

#include <CMD/CMD_Manager.h>
#include <CMD/CMD_Args.h>

#include <QtCore/QJsonDocument>



#if 0
static void
copy()
{
    OP_Director *director = OPgetDirector();
    OP_Network *obj = dynamic_cast<OP_Network *>(director->findNode("/obj"));
    OP_Node *geo1 = director->findNode("/obj/geo1");
    // OP_Node* geo2 = director->findNode("/obj/geo2");

    // if (!geo1 || !geo2)
    //{
    //     std::cout << "Missing /obj/geo1 or /obj/geo2" << std::endl;
    //     return;
    // }

    std::stringstream serializationStream;

    std::cout << "\n=========================================\nSaving node\n\n";

    obj->saveSingle(serializationStream, geo1, OP_SaveFlags());

    std::string serializedData = serializationStream.str();
    // 'serializedData' now contains the raw text-based definitions of your nodes!

    // obj->destroyNode(geo1);

    std::string str;
    compressString(serializedData, str);

    UT_IStream is(serializedData.data(), serializedData.size(), UT_ISTREAM_ASCII);

    // 1. Size in Binary Kilobytes (KiB = 1024 bytes)
    double size_in_kib = static_cast<double>(str.size()) / 1024.0;

    // 2. Size in Decimal Kilobytes (KB = 1000 bytes)
    double size_in_kb = static_cast<double>(str.size()) / 1000.0;

    std::cout << "Size: " << size_in_kib << " KiB\n";
    std::cout << "Size: " << size_in_kb << " KB\n";

    std::cout << "\n=========================================\nLoading node\n";
    obj->loadNetwork(is, 0, nullptr, 1);

    std::cout << "\n=========================================\n\n";
}
#endif

static void
cmdStart(CMD_Args &args)
{
    Watcher::start();
}

static void
cmdStop(CMD_Args &args)
{
    Watcher::stop();
}

namespace
{
using BridgeCall = QJsonObject (*)(const QJsonObject &);

PY_PyObject *jsonResult(const QJsonObject &result)
{
    const QByteArray json = QJsonDocument(result).toJson(QJsonDocument::Compact);
    return PY_Py_BuildValue("s", json.constData());
}

bool parseRequest(PY_PyObject *args, QJsonObject &request)
{
    const char *json = nullptr;
    if (!PY_PyArg_ParseTuple(args, "s", &json))
        return false;
    const QByteArray bytes(json);
    if (bytes.size() > 4 * 1024 * 1024)
    {
        PY_PyErr_SetString(PY_PyExc_TypeError(), "coophou bridge request exceeds 4 MiB");
        return false;
    }
    QJsonParseError error;
    const QJsonDocument document = QJsonDocument::fromJson(bytes, &error);
    if (error.error != QJsonParseError::NoError || !document.isObject())
    {
        PY_PyErr_SetString(PY_PyExc_TypeError(), "coophou bridge request must be one JSON object");
        return false;
    }
    request = document.object();
    return true;
}

PY_PyObject *capabilitiesWrapper(PY_PyObject *, PY_PyObject *args)
{
    if (!PY_PyArg_ParseTuple(args, ""))
        return nullptr;
    return jsonResult(NativeAdapter::instance().capabilities());
}

PY_PyObject *startCaptureWrapper(PY_PyObject *, PY_PyObject *args)
{
    QJsonObject request;
    if (!parseRequest(args, request))
        return nullptr;
    HOM_AutoLock homLock;
    return jsonResult(NativeAdapter::instance().startCapture(request));
}

PY_PyObject *stopCaptureWrapper(PY_PyObject *, PY_PyObject *args)
{
    if (!PY_PyArg_ParseTuple(args, ""))
        return nullptr;
    HOM_AutoLock homLock;
    return jsonResult(NativeAdapter::instance().stopCapture());
}

PY_PyObject *captureStateWrapper(PY_PyObject *, PY_PyObject *args)
{
    if (!PY_PyArg_ParseTuple(args, ""))
        return nullptr;
    return jsonResult(NativeAdapter::instance().captureState());
}

PY_PyObject *flushSettleWrapper(PY_PyObject *, PY_PyObject *args)
{
    if (!PY_PyArg_ParseTuple(args, ""))
        return nullptr;
    HOM_AutoLock homLock;
    return jsonResult(NativeAdapter::instance().flushSettle());
}

PY_PyObject *drainCaptureWrapper(PY_PyObject *, PY_PyObject *args)
{
    QJsonObject request;
    if (!parseRequest(args, request))
        return nullptr;
    return jsonResult(NativeAdapter::instance().drainCapture(request));
}

PY_PyObject *extractSnapshotWrapper(PY_PyObject *, PY_PyObject *args)
{
    QJsonObject request;
    if (!parseRequest(args, request))
        return nullptr;
    HOM_AutoLock homLock;
    return jsonResult(NativeAdapter::instance().extractSupportedSnapshot(request));
}

PY_PyObject *enqueueApplyWrapper(PY_PyObject *, PY_PyObject *args)
{
    QJsonObject request;
    if (!parseRequest(args, request))
        return nullptr;
    return jsonResult(NativeAdapter::instance().enqueueApply(request));
}

PY_PyObject *drainApplyWrapper(PY_PyObject *, PY_PyObject *args)
{
    QJsonObject request;
    if (!parseRequest(args, request))
        return nullptr;
    HOM_AutoLock homLock;
    return jsonResult(NativeAdapter::instance().drainApply(request));
}

PY_PyObject *resetForTestsWrapper(PY_PyObject *, PY_PyObject *args)
{
    QJsonObject request;
    if (!parseRequest(args, request))
        return nullptr;
    HOM_AutoLock homLock;
    return jsonResult(NativeAdapter::instance().resetForTests(request));
}

PY_PyMethodDef bridgeMethods[] = {
    {"coophou_native_capabilities", capabilitiesWrapper, PY_METH_VARARGS(), "Return coophou native capabilities as JSON."},
    {"coophou_native_start_capture", startCaptureWrapper, PY_METH_VARARGS(), "Start bounded native capture from a JSON request."},
    {"coophou_native_stop_capture", stopCaptureWrapper, PY_METH_VARARGS(), "Stop native capture."},
    {"coophou_native_capture_state", captureStateWrapper, PY_METH_VARARGS(), "Return native capture/application state as JSON."},
    {"coophou_native_flush_settle", flushSettleWrapper, PY_METH_VARARGS(), "Settle bounded native event evidence."},
    {"coophou_native_drain_capture", drainCaptureWrapper, PY_METH_VARARGS(), "Drain native capture records."},
    {"coophou_native_extract_snapshot", extractSnapshotWrapper, PY_METH_VARARGS(), "Extract the configured native supported-state snapshot."},
    {"coophou_native_enqueue_apply", enqueueApplyWrapper, PY_METH_VARARGS(), "Enqueue a plain native apply request."},
    {"coophou_native_drain_apply", drainApplyWrapper, PY_METH_VARARGS(), "Drain bounded native application work."},
    {"coophou_native_reset_for_tests", resetForTestsWrapper, PY_METH_VARARGS(), "Reset bounded test-only native state."},
    {nullptr, nullptr, 0, nullptr},
};
}

void CMDextendLibrary(CMD_Manager *cman)
{
    cman->installCommand("coop_start", "", cmdStart);
    cman->installCommand("coop_stop", "", cmdStop);
}

void HOMextendLibrary()
{
    PY_InterpreterAutoLock interpreterLock;
    PY_AutoObject houModule(PY_PyImport_ImportModule("hou"));
    if (!houModule)
    {
        PY_PyErr_Print();
        return;
    }
    PY_PyObject *houDict = PY_PyModule_GetDict(houModule);
    for (PY_PyMethodDef *method = bridgeMethods; method->ml_name; ++method)
    {
        PY_AutoObject function(PY_PyCFunction_NewEx(method, nullptr, nullptr));
        if (!function || PY_PyDict_SetItemString(houDict, method->ml_name, function) != 0)
        {
            PY_PyErr_Print();
            return;
        }
    }
}
