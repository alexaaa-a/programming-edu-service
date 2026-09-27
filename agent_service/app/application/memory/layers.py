WORKING = "working"
SEMANTIC = "semantic"
EPISODIC = "episodic"
STUDENT = "student"

VECTOR_LAYERS = (SEMANTIC, EPISODIC, STUDENT)

TYPE_TO_LAYER: dict[str, str] = {
    "best_practice": SEMANTIC,
    "bugs": SEMANTIC,
    "past_review": EPISODIC,
    "chat_episode": EPISODIC,
    "student_note": STUDENT,
    "working": WORKING,
}

LAYER_TYPES: dict[str, frozenset[str]] = {
    SEMANTIC: frozenset({"best_practice", "bugs"}),
    EPISODIC: frozenset({"past_review", "chat_episode"}),
    STUDENT: frozenset({"student_note"}),
    WORKING: frozenset({"working"}),
}


def layer_for_type(doc_type: str | None) -> str:
    return TYPE_TO_LAYER.get(str(doc_type or ""), SEMANTIC)


def layers_for_types(types: set[str] | None) -> list[str]:
    if not types:
        return list(VECTOR_LAYERS)
    names: list[str] = []
    for doc_type in types:
        layer = layer_for_type(doc_type)
        if layer == WORKING:
            continue
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
