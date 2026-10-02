from typing import Mapping

SEMANTIC = "semantic"
EPISODIC = "episodic"

VECTOR_LAYERS = (SEMANTIC, EPISODIC)

TYPE_TO_LAYER: dict[str, str] = {
    "best_practice": SEMANTIC,
    "bugs": SEMANTIC,
    "past_review": EPISODIC,
    "chat_episode": EPISODIC,
}

LAYER_TYPES: dict[str, frozenset[str]] = {
    SEMANTIC: frozenset({"best_practice", "bugs"}),
    EPISODIC: frozenset({"past_review", "chat_episode"}),
}

USER_SCOPED_TYPES = frozenset({"past_review", "chat_episode"})
SESSION_SCOPED_TYPES = frozenset({"chat_episode"})


def layer_for_type(doc_type: str | None) -> str:
    return TYPE_TO_LAYER.get(str(doc_type or ""), SEMANTIC)


def layers_for_types(types: set[str] | None) -> list[str]:
    if not types:
        return list(VECTOR_LAYERS)
    names: list[str] = []
    for doc_type in types:
        layer = layer_for_type(doc_type)
        if layer not in names:
            names.append(layer)
    return names or list(VECTOR_LAYERS)


def types_for_layer(layer: str, requested: set[str] | None) -> set[str] | None:
    owned = LAYER_TYPES.get(layer)
    if owned is None:
        return requested
    if not requested:
        return set(owned)
    return {t for t in requested if t in owned}


def scope_filter(
        types: set[str] | None,
        scope: Mapping[str, str] | None,
) -> dict[str, str]:
    if not scope:
        return {}
    requested = {str(item) for item in types} if types else set()
    if not requested:
        return {}
    out: dict[str, str] = {}
    user_id = str(scope.get("user_id") or "").strip()
    session_id = str(scope.get("session_id") or "").strip()
    if user_id and requested <= USER_SCOPED_TYPES:
        out["user_id"] = user_id
    if session_id and requested <= SESSION_SCOPED_TYPES:
        out["session_id"] = session_id
    return out
