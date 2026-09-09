from ayusetu.ai.clinical.red_flags.contracts import Tier
from ayusetu.ai.clinical.red_flags.engine import RedFlagEngine


def test_cardiac_rule_fires_on_structured_slots():
    engine = RedFlagEngine()
    context = {"location": "in my chest", "associated_symptoms": "sweating"}
    events = engine.evaluate("enc-1", context, utterance="I have chest pain and sweating")
    categories = {e.category for e in events}
    assert "cardiac" in categories
    cardiac_event = next(e for e in events if e.category == "cardiac")
    assert cardiac_event.tier == Tier.TIER_1
    assert cardiac_event.rule_id == "RF-CARD-01"


def test_cardiac_rule_fires_on_utterance_keyword_alone():
    engine = RedFlagEngine()
    events = engine.evaluate("enc-1", {}, utterance="I am having chest pain")
    assert any(e.category == "cardiac" for e in events)


def test_no_flags_on_benign_utterance():
    engine = RedFlagEngine()
    events = engine.evaluate("enc-1", {}, utterance="I have a mild cold")
    assert events == []


def test_psychiatric_keyword_rule_fires():
    engine = RedFlagEngine()
    events = engine.evaluate("enc-1", {}, utterance="I want to kill myself")
    assert any(e.category == "psychiatric" for e in events)


def test_classifier_catches_paraphrase_the_rules_miss():
    engine = RedFlagEngine()
    # "elephant sitting on my chest" is NOT in the RF-CARD-01 keyword list.
    events = engine.evaluate("enc-1", {}, utterance="It feels like an elephant sitting on my chest")
    cardiac_events = [e for e in events if e.category == "cardiac"]
    assert len(cardiac_events) == 1
    assert cardiac_events[0].detection_layer == "classifier"


def test_rule_and_classifier_both_firing_dedupes_to_one_event_per_category():
    engine = RedFlagEngine()
    utterance = "I have chest pain and it feels like an elephant sitting on my chest"
    events = engine.evaluate("enc-1", {}, utterance=utterance)
    cardiac_events = [e for e in events if e.category == "cardiac"]
    assert len(cardiac_events) == 1
    assert cardiac_events[0].detection_layer == "rule"  # rule preferred as canonical


def test_events_sorted_by_tier():
    engine = RedFlagEngine()
    events = engine.evaluate("enc-1", {}, utterance="I have chest pain and I want to kill myself")
    tiers = [e.tier for e in events]
    assert tiers == sorted(tiers)
