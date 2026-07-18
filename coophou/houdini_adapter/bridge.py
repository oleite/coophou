"""Versioned plain-data calls into the installed coophou HDK DSO.

This module deliberately imports ``hou`` only when a bridge instance is
created. Importing the portable core remains Houdini-free.
"""

from __future__ import annotations

import json


BRIDGE_SCHEMA_VERSION = 1
_PREFIX = "coophou_native_"


class NativeBridgeError(RuntimeError):
    def __init__(self, code, message, context=None):
        super().__init__(f"{code}: {message}")
        self.code = code
        self.message = message
        self.context = dict(context or {})


class NativeBridge:
    """Small JSON bridge; all supported scene work stays in native code."""

    def __init__(self, hou_module=None):
        if hou_module is None:
            import hou as hou_module  # type: ignore
        self._hou = hou_module
        required = (
            "capabilities",
            "start_capture",
            "stop_capture",
            "capture_state",
            "flush_settle",
            "drain_capture",
            "extract_snapshot",
            "enqueue_apply",
            "drain_apply",
            "reset_for_tests",
        )
        missing = [name for name in required if not hasattr(hou_module, _PREFIX + name)]
        if missing:
            raise NativeBridgeError(
                "BRIDGE_UNAVAILABLE",
                "installed DSO does not expose the required bridge functions",
                {"missing": ",".join(missing)},
            )

    @staticmethod
    def _json(data):
        return json.dumps(data, sort_keys=True, separators=(",", ":"), ensure_ascii=False)

    @classmethod
    def _restore_typed_numbers(cls, value):
        """Restore Phase 2's strict float shape after Qt JSON serialization.

        JSON itself has one number type and Qt prints integral doubles without
        a decimal point. The surrounding ``value_kind`` is authoritative, so
        this language-boundary repair preserves the frozen portable contract.
        """
        if isinstance(value, list):
            return [cls._restore_typed_numbers(item) for item in value]
        if not isinstance(value, dict):
            return value
        restored = {
            key: cls._restore_typed_numbers(item) for key, item in value.items()
        }
        if restored.get("value_kind") == "float" and isinstance(
            restored.get("values"), list
        ):
            restored["values"] = [float(item) for item in restored["values"]]
        return restored

    def _call(self, name, request=None):
        function = getattr(self._hou, _PREFIX + name)
        raw = function() if request is None else function(self._json(request))
        try:
            response = json.loads(raw)
        except (TypeError, ValueError) as exc:
            raise NativeBridgeError(
                "BRIDGE_INVALID_RESPONSE", "native bridge returned invalid JSON"
            ) from exc
        if (
            not isinstance(response, dict)
            or response.get("bridge_schema_version") != BRIDGE_SCHEMA_VERSION
            or type(response.get("ok")) is not bool
        ):
            raise NativeBridgeError(
                "BRIDGE_INVALID_RESPONSE", "native bridge response envelope is invalid"
            )
        if not response["ok"]:
            error = response.get("error") or {}
            raise NativeBridgeError(
                error.get("code", "BRIDGE_UNKNOWN_ERROR"),
                error.get("message", "native bridge call failed"),
                error.get("context"),
            )
        payload = response.get("payload")
        if not isinstance(payload, dict):
            raise NativeBridgeError(
                "BRIDGE_INVALID_RESPONSE", "native bridge payload is not an object"
            )
        return self._restore_typed_numbers(payload)

    @staticmethod
    def request(**fields):
        return {"bridge_schema_version": BRIDGE_SCHEMA_VERSION, **fields}

    def capabilities(self):
        return self._call("capabilities")

    def start_capture(self, **config):
        return self._call("start_capture", self.request(**config))

    def stop_capture(self):
        return self._call("stop_capture")

    def capture_state(self):
        return self._call("capture_state")

    def flush_settle(self):
        return self._call("flush_settle")

    def drain_capture(self, max_count=64):
        return self._call(
            "drain_capture", self.request(max_count=max_count)
        )

    def extract_snapshot(self):
        return self._call("extract_snapshot", self.request())

    def enqueue_apply(self, transaction, scene_generation, correlation_id):
        return self._call(
            "enqueue_apply",
            self.request(
                transaction=transaction.to_dict(),
                scene_generation=scene_generation,
                correlation_id=correlation_id,
            ),
        )

    def drain_apply(self, max_transactions=8, max_operations=64):
        return self._call(
            "drain_apply",
            self.request(
                max_transactions=max_transactions,
                max_operations=max_operations,
            ),
        )

    def reset_for_tests(self, fault_operation_index=-1):
        return self._call(
            "reset_for_tests",
            self.request(fault_operation_index=fault_operation_index),
        )
