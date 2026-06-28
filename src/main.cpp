#include "utils.h"

#include <iostream>

#include <CMD/CMD_Manager.h>

#include <OP/OP_Director.h>
#include <OP/OP_Value.h>


#include <UT/UT_DSOVersion.h>



namespace Color {
    const std::string RESET = "\033[0m";
    const std::string SAGE = "\033[38;2;135;169;141m";  // Soft earth green
    const std::string ROSE = "\033[38;2;212;141;143m";  // Pastel dusty rose
    const std::string SLATE = "\033[38;2;112;128;144m";  // Cool muted blue-grey
    const std::string SAND = "\033[38;2;221;190;169m";  // Soft warm beige
}



static void 
globalOpChangedHook(OP_Node *node, OP_EventType reason, void *data, void *cbdata)
{
    if (!node)
        return;

    // 1. Get the human-readable string name of the event
    const char* eventName = OPeventToString(reason);
    if (!eventName)
        eventName = "UNKNOWN_EVENT";

    // Start building our output diagnostic line
    std::cout << Color::SAGE << "[E] " << eventName << " on " << node->getFullPath();

    // 2. Directly print the raw payload pointer if it exists
    if (data)
    {
        std::cout << " | Payload Data Pointer: " << data;

        // 3. Intelligently peek into the payload based on the event type
        if (reason == OP_CHILD_CREATED || reason == OP_CHILD_DELETED)
        {
            // For child events, data is an OP_Node*
            OP_Node *childNode = static_cast<OP_Node*>(data);
            std::cout << " (Child Node: " << childNode->getFullPath() << ")";
        }
        else if (reason == OP_PARM_CHANGED)
        {
            // For parameter changes, data is often passed as a raw integer token or index value.
            // We cast through intptr_t to safely read it without alignment/pointer-size truncation issues.
            intptr_t parmIndex = reinterpret_cast<intptr_t>(data);
            std::cout << " (Parm Index/Token ID: " << parmIndex << ")";
        }
    }
    else
    {
        std::cout << " | No Payload";
    }

    std::cout << Color::RESET << std::endl;
}








#include <OP/OP_Network.h>
#include <UT/UT_String.h>
#include <UT/UT_IStream.h>
#include <sstream>
#include <iostream>


static void
copy()
{
    OP_Director* director = OPgetDirector();
    OP_Network* obj = dynamic_cast<OP_Network*>(director->findNode("/obj"));
    OP_Node* geo1 = director->findNode("/obj/geo1");
    //OP_Node* geo2 = director->findNode("/obj/geo2");


    //if (!geo1 || !geo2)
    //{
    //    std::cout << "Missing /obj/geo1 or /obj/geo2" << std::endl;
    //    return;
    //}

    std::stringstream serializationStream;


    std::cout << "\n=========================================\nSaving node\n\n";

    obj->saveSingle(serializationStream, geo1, OP_SaveFlags());

    std::string serializedData = serializationStream.str();
    // 'serializedData' now contains the raw text-based definitions of your nodes!

    //obj->destroyNode(geo1);
    


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




#include <CMD/CMD_Args.h>

static void
cmdStart(CMD_Args& args)
{
    OP_Director* director = OPgetDirector();
    if (director)
    {
        director->addGlobalOpChangedCallback(globalOpChangedHook, nullptr);
    }
}

static void
cmdStop(CMD_Args& args)
{
    OP_Director* director = OPgetDirector();
    if (director)
    {
        director->removeGlobalOpChangedCallback(globalOpChangedHook, nullptr);
    }
}



#include <PRM/PRM_Parm.h>


static void
cmdParm(CMD_Args& args)
{
    const char *nodePath = args.argp('n');
    if (!args.found('n'))
    {
	    args.err() << "Missing -n option to specify node path.\n";
        return;
    }

    PRM_DataFactory *factory();

    OP_Node *node = OPgetDirector()->findNode(nodePath);
    node->getParmPtr("ry");
    
    
    
}

void
CMDextendLibrary(CMD_Manager* cman)
{
    cman->installCommand("coop_start", "", cmdStart);
    cman->installCommand("coop_stop", "", cmdStop);
    cman->installCommand("coop_parm", "n:", cmdParm);

}
