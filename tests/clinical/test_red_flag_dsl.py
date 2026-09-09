from ayusetu.ai.clinical.red_flags.dsl import evaluate_condition


def test_all_requires_every_condition():
    cond = {"all": [{"slot": "a", "in": [1]}, {"slot": "b", "in": [2]}]}
    assert evaluate_condition(cond, {"a": 1, "b": 2}) is True
    assert evaluate_condition(cond, {"a": 1, "b": 3}) is False


def test_any_requires_one_condition():
    cond = {"any": [{"slot": "a", "in": [1]}, {"slot": "b", "in": [2]}]}
    assert evaluate_condition(cond, {"a": 9, "b": 2}) is True
    assert evaluate_condition(cond, {"a": 9, "b": 9}) is False


def test_contains_on_string_value():
    cond = {"slot": "text", "contains": "chest pain"}
    assert evaluate_condition(cond, {"text": "I have severe CHEST PAIN today"}) is True
    assert evaluate_condition(cond, {"text": "I have a headache"}) is False


def test_contains_on_list_value():
    cond = {"slot": "symptoms", "contains": "dyspnoea"}
    assert evaluate_condition(cond, {"symptoms": ["fever", "dyspnoea"]}) is True
    assert evaluate_condition(cond, {"symptoms": ["fever", "cough"]}) is False


def test_missing_slot_never_matches():
    cond = {"slot": "not_elicited_slot", "contains": "anything"}
    assert evaluate_condition(cond, {}) is False


def test_nested_all_any_combination():
    cond = {
        "all": [
            {"slot": "location", "contains": "chest"},
            {"any": [{"slot": "symptoms", "contains": "sweating"}, {"slot": "symptoms", "contains": "dyspnoea"}]},
        ]
    }
    context = {"location": "in my chest", "symptoms": ["sweating"]}
    assert evaluate_condition(cond, context) is True
