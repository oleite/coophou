import hou


class Event:
    _registry = {}
    eventType = "UnknownEvent"

    def __init_subclass__(cls, **kwargs):
        super().__init_subclass__(**kwargs)
        cls._registry[cls.eventType] = cls

    @staticmethod
    def extractPayload(event):
        return {"unknown_event": event}

    @staticmethod
    def applyPayload(payload):
        print("    not implemented yet")
        pass

    @classmethod
    def errMissingNode(cls, nodePath):
        print(f"Error: Node {nodePath} not found for event type {cls.eventType}")


def getEvent(eventTypeStr):
    return Event._registry.get(eventTypeStr, Event)


class EventPositionChanged(Event):
    eventType = "PositionChanged"

    @staticmethod
    def extractPayload(event):
        nodePath = event["node"]
        print(event)
        return {
            "node": nodePath,
            "pos": tuple(hou.node(nodePath).position()),
        }

    @staticmethod
    def applyPayload(payload):
        node = hou.node(payload["node"])

        if not node:
            return Event.errMissingNode(payload["node"])

        node.setPosition(payload["pos"])


class EventParmTupleChanged(Event):
    eventType = "ParmTupleChanged"

    @staticmethod
    def extractPayload(event):
        parmTuplePath = event["node"] + "/" + event["parm_tuple"]
        return {
            "parm_tuple": parmTuplePath,
            "data": hou.parmTuple(parmTuplePath).asData(),
        }

    @staticmethod
    def applyPayload(payload):
        parmTuple = hou.parmTuple(payload["parm_tuple"])

        if not parmTuple:
            return Event.errMissingNode(payload["parm_tuple"])

        parmTuple.setFromData(payload["data"])


class EventNameChanged(Event):
    eventType = "NameChanged"

    @staticmethod
    def extractPayload(event):
        nodePath = event["node"]
        return {
            "node": nodePath,
            "name": hou.node(nodePath).name(),
        }

    @staticmethod
    def applyPayload(payload):
        node = hou.node(payload["node"])

        if not node:
            return Event.errMissingNode(payload["node"])

        node.setName(payload["name"])


class EventChildCreated(Event):
    eventType = "ChildCreated"

    @staticmethod
    def extractPayload(event):
        print("\n" * 10)

        nodeType = hou.node(event["child_node"]).type().name()
        return {
            "node": event["child_node"],
            "type": nodeType,
        }

    @staticmethod
    def applyPayload(payload):
        print("\n" * 10)

        parentPath = "/".join(payload["node"].split("/")[:-1])

        parentNode = hou.node(parentPath)
        if not parentNode:
            return Event.errMissingNode(parentPath)

        parentNode.createNode(payload["type"], node_name=payload["node"].split("/")[-1])


class EventChildDeleted(Event):
    eventType = "ChildDeleted"

    @staticmethod
    def extractPayload(event):
        return {
            "node": event["child_node"],
        }

    @staticmethod
    def applyPayload(payload):
        node = hou.node(payload["node"])

        if not node:
            return Event.errMissingNode(payload["node"])

        node.destroy()


class EventChildSelectionChanged(Event):
    eventType = "ChildSelectionChanged"

    @staticmethod
    def extractPayload(event):
        node = hou.node(event["node"])
        selection = [item.name() for item in node.selectedItems()]
        return {
            "node": event["node"],
            "selection": selection,
        }

    @staticmethod
    def applyPayload(payload):
        node = hou.node(payload["node"])

        if not node:
            return Event.errMissingNode(payload["node"])

        for item in node.allItems():
            selected = item.name() in payload["selection"]
            if selected:
                item.setColor(hou.Color((1, 0, 0)))
            else:
                item.setColor(hou.Color((0.8, 0.8, 0.8)))


class EventCustomNodeDataChanged(Event):
    eventType = "CustomNodeDataChanged"

    @staticmethod
    def extractPayload(event):
        nodePath = event["node"]

        return {
            "node": nodePath,
            "data": hou.node(nodePath).asData(
                inputs=True,
                children=True,
                position=True,
            ),
        }

    @staticmethod
    def applyPayload(payload):
        node = hou.node(payload["node"])

        if not node:
            return Event.errMissingNode(payload["node"])

        node.setFromData(payload["data"])


class EventInputRewired(Event):
    eventType = "InputRewired"

    @staticmethod
    def extractPayload(event):
        nodePath = event["node"]
        return {
            "node": nodePath,
            "data": hou.node(nodePath).asData(
                inputs=True,
            ),
        }

    @staticmethod
    def applyPayload(payload):
        node = hou.node(payload["node"])

        if not node:
            return Event.errMissingNode(payload["node"])

        node.setFromData(payload["data"])


class EventAppearanceChanged(Event):
    eventType = "AppearanceChanged"

    @staticmethod
    def extractPayload(event):
        nodePath = event["node"]
        return {
            "node": nodePath,
            "data": hou.node(nodePath).asData(
                nodes_only=True,
                children=False,
                editables=False,
                inputs=True,
                position=True,
                parms=False,
            ),
        }

    @staticmethod
    def applyPayload(payload):
        node = hou.node(payload["node"])

        if not node:
            return Event.errMissingNode(payload["node"])

        node.setFromData(payload["data"])
