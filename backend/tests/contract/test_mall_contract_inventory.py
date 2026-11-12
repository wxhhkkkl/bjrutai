"""Check the planned API inventory; these tests do not claim routes are implemented."""

import json
import re
from pathlib import Path

import pytest

FEATURE = Path(__file__).resolve().parents[3] / "specs/022-independent-mall"
METHODS = {"get", "post", "put", "patch", "delete"}


def inventory_errors(contract):
    errors = []
    seen = set()
    for path, methods in contract["paths"].items():
        for method, operation in methods.items():
            if method not in METHODS:
                continue
            name = operation["operationId"]
            if name in seen:
                errors.append("duplicate operationId")
            seen.add(name)
            parameters = operation.get("parameters", []) + methods.get("parameters", [])
            for parameter in re.findall(r"{([^}]+)}", path):
                if not any(
                    p.get("name") == parameter and p.get("in") == "path" and p.get("required")
                    for p in parameters
                ):
                    errors.append("missing path parameter")
            if (
                method != "get"
                and name not in {"quoteMallOrder", "wechatPaymentNotify", "wechatRefundNotify"}
                and not any(
                    p.get("name") == "Idempotency-Key"
                    and p.get("in") == "header"
                    and p.get("required")
                    for p in parameters
                )
            ):
                errors.append("missing idempotency key")
            if not operation.get("x-requirements") or any(
                not re.fullmatch(r"FR-\d{3}", item) or not 1 <= int(item[3:]) <= 94
                for item in operation.get("x-requirements", [])
            ):
                errors.append("invalid requirement")
            if operation.get("x-actor-policy") == "admin" and not (
                operation.get("x-permission") or operation.get("x-permission-policy")
            ):
                errors.append("missing admin permission")
            if name in {"wechatPaymentNotify", "wechatRefundNotify"} and (
                operation.get("x-implementation-gate") != "G-PROTOCOL"
            ):
                errors.append("notification governance gate missing")

    def walk(node):
        if isinstance(node, dict):
            if "$ref" in node:
                ref = node["$ref"]
                target = contract
                try:
                    if not ref.startswith("#/"):
                        raise KeyError(ref)
                    for part in ref[2:].split("/"):
                        target = target[part.replace("~1", "/").replace("~0", "~")]
                except (KeyError, TypeError):
                    errors.append("unresolved reference")
            if "properties" in node and not set(node.get("required", [])).issubset(
                node["properties"]
            ):
                errors.append("required property missing")
            for value in node.values():
                walk(value)
        elif isinstance(node, list):
            for value in node:
                walk(value)

    walk(contract)
    return errors


@pytest.fixture
def contract():
    return json.loads((FEATURE / "contracts/openapi.json").read_text())


def test_planned_inventory_is_internally_consistent(contract):
    assert inventory_errors(contract) == []
    tasks = json.loads((FEATURE / "tasks-map.json").read_text())
    operations = [op["operationId"] for ms in contract["paths"].values() for op in ms.values()]
    owners = [op for task in tasks["tasks"] for op in task["operationIds"]]
    assert len(operations) == len(set(operations)) == 104
    assert sorted(owners) == sorted(operations)


@pytest.mark.parametrize(
    "damage,expected",
    [
        ("duplicate", "duplicate operationId"),
        ("path", "missing path parameter"),
        ("key", "missing idempotency key"),
        ("requirement", "invalid requirement"),
        ("reference", "unresolved reference"),
        ("required", "required property missing"),
        ("permission", "missing admin permission"),
        ("gate", "notification governance gate missing"),
    ],
)
def test_invalid_contract_changes_are_rejected(contract, damage, expected):
    operations = [op for ms in contract["paths"].values() for op in ms.values()]
    if damage == "duplicate":
        operations[1]["operationId"] = operations[0]["operationId"]
    elif damage == "path":
        target = contract["paths"]["/api/v1/mall/orders/{orderId}"]["get"]
        target["parameters"] = []
    elif damage == "key":
        target = next(op for op in operations if op["operationId"] == "createMallOrder")
        target["parameters"] = []
    elif damage == "requirement":
        operations[0]["x-requirements"] = ["FR-999"]
    elif damage == "reference":
        contract["components"]["schemas"]["Order"]["properties"]["items"] = {
            "$ref": "#/components/schemas/DoesNotExist"
        }
    elif damage == "required":
        contract["components"]["schemas"]["Order"]["required"].append("missing")
    elif damage == "permission":
        target = next(op for op in operations if op["operationId"] == "getAdminMallOrder")
        target.pop("x-permission")
    else:
        target = next(op for op in operations if op["operationId"] == "wechatPaymentNotify")
        target.pop("x-implementation-gate")
    assert expected in inventory_errors(contract)


def test_order_details_do_not_leak_internal_fields(contract):
    schemas = contract["components"]["schemas"]
    buyer = schemas["BuyerOrderDetail"]
    admin = schemas["AdminOrderDetail"]
    assert buyer["additionalProperties"] is False
    assert "internalNote" not in buyer["properties"]
    assert "buyer" not in buyer["properties"]
    assert {"internalNote", "buyer"}.issubset(admin["required"])
    for obj in (buyer, admin):
        assert {
            "payableAmountCent",
            "receivedAt",
            "timeline",
            "availableActions",
        }.issubset(obj["required"])


def test_adjustments_support_a_missing_original_result(contract):
    adjustment = contract["components"]["schemas"]["Adjustment"]
    assert {"originResultId", "originEvidenceId", "originResultPresence"}.issubset(
        adjustment["required"]
    )
    assert {"type": "null"} in adjustment["properties"]["originResultId"]["anyOf"]
