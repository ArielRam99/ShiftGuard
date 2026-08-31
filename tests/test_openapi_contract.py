import re
from pathlib import Path

import yaml


HTTP_METHODS = {"get", "post", "put", "patch", "delete", "options", "head"}


def _openapi_document():
    path = Path(__file__).parents[1] / "docs" / "openapi.yaml"
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def _contract_operations(document):
    return {
        (path, method.upper())
        for path, path_item in document["paths"].items()
        for method in path_item
        if method in HTTP_METHODS
    }


def _flask_path(rule):
    return re.sub(r"<(?:[^:<>]+:)?([^<>]+)>", r"{\1}", rule)


def _application_operations(app):
    operations = set()
    for rule in app.url_map.iter_rules():
        if not rule.rule.startswith("/api"):
            continue
        for method in rule.methods - {"HEAD", "OPTIONS"}:
            operations.add((_flask_path(rule.rule), method))
    return operations


def test_openapi_operations_match_flask_routes(app):
    document = _openapi_document()
    assert document["openapi"] == "3.1.0"
    assert _contract_operations(document) == _application_operations(app)


def test_openapi_operations_are_complete_and_references_resolve():
    document = _openapi_document()
    operation_ids = []
    references = []

    def collect(value):
        if isinstance(value, dict):
            if "$ref" in value:
                references.append(value["$ref"])
            for nested in value.values():
                collect(nested)
        elif isinstance(value, list):
            for nested in value:
                collect(nested)

    for path_item in document["paths"].values():
        for method, operation in path_item.items():
            if method not in HTTP_METHODS:
                continue
            operation_ids.append(operation["operationId"])
            assert operation["responses"]

    assert len(operation_ids) == len(set(operation_ids))
    collect(document)
    for reference in references:
        assert reference.startswith("#/components/")
        target = document
        for part in reference[2:].split("/"):
            target = target[part]
