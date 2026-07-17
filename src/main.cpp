#include "utils.h"
#include "watcher.h"

#include <iostream>

#include <UT/UT_DSOVersion.h>

#include <CMD/CMD_Manager.h>
#include <CMD/CMD_Args.h>



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

void CMDextendLibrary(CMD_Manager *cman)
{
    cman->installCommand("coop_start", "", cmdStart);
    cman->installCommand("coop_stop", "", cmdStop);
}
