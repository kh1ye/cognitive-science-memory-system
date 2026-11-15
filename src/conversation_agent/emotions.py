"""Bounded, short-lived emotion state; no memory engine writes."""
import math

from cognitive_memory.provenance import source_span

EMOJIS = {"energetic": "⚡", "happy": "😄", "calm": "😌", "neutral": "😐",
          "tired": "😴", "sad": "😔", "anxious": "😟", "irritable": "😤"}
EMOTION_TTL = 300
CONFIDENCE_THRESHOLD = .75
TEMPORARY_EMOTION_TOPICS = {"emotion", "current_emotion", "mood", "current_mood", "feeling", "current_feeling",
                            "emotional_state", "情绪", "当前情绪", "心情", "当前心情", "疲惫程度"}


def neutral_emotion():
    return {"label": "neutral", "confidence": 0., "emoji": EMOJIS["neutral"], "expires_at": 0.}


def resolve_emotion(previous, assessment, message, now):
    active = previous if previous and previous["expires_at"] > now else neutral_emotion()
    if (assessment.is_user_state and assessment.confidence >= CONFIDENCE_THRESHOLD
        and assessment.evidence_text and source_span(assessment.evidence_text, message) is not None):
        return {"label": assessment.label, "confidence": assessment.confidence,
                "emoji": EMOJIS[assessment.label], "expires_at": now + EMOTION_TTL}
    return dict(active)


def public_emotion(emotion, now):
    active = emotion if emotion and emotion["expires_at"] > now else neutral_emotion()
    return {"label": active["label"], "confidence": active["confidence"], "emoji": active["emoji"],
            "ttl_seconds": max(0, math.ceil(active["expires_at"] - now))}
