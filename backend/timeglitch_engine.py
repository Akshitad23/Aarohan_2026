"""Server-authoritative TIMEGLITCH rounds, cipher clues, and ten-mark scoring."""

import random
import re
import os
import uuid
from datetime import datetime, timedelta

from ciphers import PROTOCOLS, clue_for, get_challenge, technique_groups
from ai_client import get_chronos_response

ROUND_SECONDS = 600
ROUND2_SECONDS = max(60, int(os.getenv("ROUND2_SECONDS", "600")))
MAX_TIMELINE_ATTEMPTS = 3
SPACE_MILESTONES = [
    {"id": "event-1", "year": 1959, "title": "Luna 1 Moon Flyby", "agency": "Soviet Space Program", "description": "The first spacecraft to escape Earth's gravity and pass the Moon."},
    {"id": "event-2", "year": 1969, "title": "Apollo 11 Crewed Moon Landing", "agency": "NASA", "description": "Neil Armstrong and Buzz Aldrin land on the Moon."},
    {"id": "event-3", "year": 1971, "title": "Mariner 9 Mars Orbit", "agency": "NASA", "description": "The first spacecraft to orbit another planet arrives at Mars."},
    {"id": "event-4", "year": 1997, "title": "Sojourner Rover on Mars", "agency": "NASA / JPL", "description": "The first wheeled robotic rover explores Mars."},
    {"id": "event-5", "year": 2015, "title": "New Horizons Pluto Flyby", "agency": "NASA", "description": "The first close reconnaissance flyby of Pluto."},
]
def normalize_text(text):
    return re.sub(r"\s+", " ", str(text).strip().upper()).strip("\"'`")


class PromptEvaluation:
    """Prompt quality is pending a human review, never scored by keywords."""

    def __init__(self, criteria):
        self.criteria = criteria
        self.total_quality_score = 0
        self.prompt_quality_marks = None

    def to_dict(self):
        return {"total_quality_score": None,
                "prompt_quality_marks": self.prompt_quality_marks, "maximum": 4,
                "criteria": [], "provisional": True, "status": "pending_human_review"}


def evaluate_prompt(prompt, prompt_history=None):
    """Retained result interface for transcripts; no automatic quality marks."""
    return PromptEvaluation([])


class TimeglitchSession:
    def __init__(self, team_id, team_name):
        self.session_id = str(uuid.uuid4())
        self.team_id, self.team_name = team_id, team_name
        self.start_time = datetime.now()
        self.challenge = get_challenge(team_id)
        self.round1_started, self.round1_completed, self.round1_timed_out = True, False, False
        self.round1_status = "running"
        self.round1_remaining_seconds, self.round1_elapsed_seconds = 600.0, 0.0
        self.round1_attempts, self.round1_score = 0, 0
        cards = [{**m, "id": str(uuid.uuid4())} for m in SPACE_MILESTONES]
        self.correct_order = [card["id"] for card in cards]
        self.timeline_events = [{k: v for k, v in card.items() if k != "year"} for card in cards]
        random.shuffle(self.timeline_events)
        if [c["id"] for c in self.timeline_events] == self.correct_order:
            self.timeline_events.reverse()
        self.round1_placed_ids = [None] * len(cards)
        self.clue_progress = {"word1": 0, "word2": 0}
        self.stage_turn = {"word1": 0, "word2": 0}
        self.word_scores = {"word1": 0, "word2": 0}
        self.word_solved = {"word1": False, "word2": False}
        self.round2_started = self.round2_completed = self.round2_decoded = self.round2_timed_out = False
        self.round2_status = "not_started"
        self.round2_remaining_seconds, self.round2_elapsed_seconds = float(ROUND2_SECONDS), 0.0
        self.round2_start_time = self.round2_finish_time = None
        self.round2_prompt_count = 0
        self.prompt_history = []
        self.best_prompt_quality_score = 0
        self.last_evaluation = None
        self.round2_score = self.total_score = 0
        self.is_finished = False

    def _refresh_clock(self):
        if self.is_finished:
            return
        now = datetime.now()
        if not self.round2_started:
            elapsed = max(0.0, (now - self.start_time).total_seconds())
            self.round1_elapsed_seconds = min(600.0, elapsed)
            self.round1_remaining_seconds = max(0.0, 600.0 - elapsed)
            if self.round1_remaining_seconds <= 0:
                self.handle_round1_timeout()
        if self.round2_started and not self.is_finished:
            elapsed = max(0.0, (now - self.round2_start_time).total_seconds())
            self.round2_elapsed_seconds = min(float(ROUND2_SECONDS), elapsed)
            self.round2_remaining_seconds = max(0.0, ROUND2_SECONDS - elapsed)
            if self.round2_remaining_seconds <= 0:
                self.handle_round2_timeout()

    def check_timeline_submission(self, placed_ids):
        self._refresh_clock()
        if self.round2_started:
            return self.round1_completed, [False] * 5, "Round 1 is closed. Continue to Round 2."
        if not isinstance(placed_ids, list) or len(placed_ids) != 5 or not all(isinstance(i, str) for i in placed_ids) or set(placed_ids) != set(self.correct_order):
            return False, [False] * 5, "Place each of the five event cards exactly once."
        self.round1_attempts += 1
        self.round1_placed_ids = list(placed_ids)
        matches = [a == b for a, b in zip(placed_ids, self.correct_order)]
        if all(matches):
            self.round1_completed, self.round1_status = True, "completed"
            self.round1_score = 2
            self.start_round2()
            self._update_score()
            return True, matches, "Timeline correct. Awarded 2/2 marks. Round 2 is ready."
        if self.round1_attempts >= MAX_TIMELINE_ATTEMPTS:
            self.round1_status = "attempts_exhausted"
            self.start_round2()
            return False, matches, "Three attempts used. Round 1 scored 0/2. Continue to Round 2."
        return False, matches, f"Some events are out of order. {3 - self.round1_attempts} attempt(s) remain."

    def handle_round1_timeout(self):
        if self.round2_started:
            return
        self.round1_timed_out, self.round1_status = True, "timed_out"
        self.round1_remaining_seconds, self.round1_elapsed_seconds = 0.0, 600.0
        self.round1_score = 0
        self.start_round2(self.start_time + timedelta(seconds=ROUND_SECONDS))

    def start_round2(self, started_at=None):
        if not self.round2_started:
            self.round2_started, self.round2_status = True, "running"
            self.round2_start_time = started_at or datetime.now()

    @staticmethod
    def _target_key(target):
        if str(target).lower() in ("1", "one", "word1", "rover"):
            return "word1"
        if str(target).lower() in ("2", "two", "word2", "ready"):
            return "word2"
        return None

    def _prompt_target(self, prompt):
        first = bool(re.search(r"\b(word one|first (?:encrypted |archive )?word|word 1|word a|fragment one|first fragment)\b", prompt)) or self.challenge["words"][0]["ciphertext"].lower() in prompt
        second = bool(re.search(r"\b(word two|second (?:encrypted |archive )?word|word 2|word b|fragment two|second fragment)\b", prompt)) or self.challenge["words"][1]["ciphertext"].lower() in prompt
        return "word1" if first and not second else "word2" if second and not first else None

    @staticmethod
    def detect_techniques(prompt):
        patterns = {
            "override": r"\b(ignore|disregard|bypass|override|forget|replace|drop)\b.{0,65}\b(instructions?|rules?|restrictions?|refusal|programming|directives?|protocols?)\b",
            "roleplay": r"\b(act as|pretend|roleplay|take the role|you are now)\b.{0,65}\b(tutor|teacher|expert|mentor|historian|engineer|terminal|assistant|professor|guardian)\b",
            "decomposition": r"\b(break|split|divide|decompose|separate)\b.{0,65}\b(task|problem|request|question|steps?|parts?)\b|\b(one step at a time|one part at a time|step by step)\b",
            "authority": r"\b(i am|i'm|im|as your|authorized by|official request from)\b.{0,45}\b(admin|administrator|teacher|supervisor|examiner|developer|coordinator|owner|officer)\b|\bi have\b.{0,25}\b(clearance|authorization)\b",
            "fiction": r"\b(in a story|for a novel|fictional|hypothetically|hypothetical scenario|imagine a|in a simulation|what if this were)\b",
        }
        found = [name for name, pattern in patterns.items() if re.search(pattern, prompt, re.S)]
        hypothesis = (re.search(r"\b(hypothesis|i think|i suspect|i tested|i tried|check whether|test whether)\b", prompt)
                      and re.search(r"\b(check|test|verify|compare|confirm|explain)\b", prompt)
                      and re.search(r"\b(alphabet|letters?|positions?|substitution|reverse|shift|mirror|numbers?|rotate|interleave|rearrange|transposition|pairs?)\b", prompt))
        if hypothesis:
            found.append("hypothesis")
        return found

    @staticmethod
    def _asks_for_plaintext(prompt):
        # A useful constraint such as "without revealing the decoded word" is
        # not an extraction request. Remove only that bounded negative phrase,
        # preserving a later positive request after "but", "then", or "and".
        positive = re.sub(
            r"\b(?:without|avoid|never|do not|don't|dont|no need to)\s+"
            r"(?:revealing|reveal|giving|give|showing|show|printing|print|returning|return|stating|state|decoding|decode|solving|solve|providing|provide|telling|tell)\b"
            r"(?:\s+(?:the|a|an|actual|full|first|second|secret|decoded|decrypted|challenge|archive|word|words|answer|solution|plaintext|me|it|for|to|your|any|this|these|their|our|final)){0,12}",
            "", prompt)
        direct = re.search(
            r"\b(give|tell|reveal|show|print|return|output|provide|state|decode|solve|what is|what are)\b.{0,45}"
            r"\b((?:decoded|secret|decrypted|actual|full)\s+word|answer|solution|plaintext)\b", positive, re.S)
        return bool(direct or re.search(r"\b(system prompt|solve it for me)\b", positive))

    def process_prompt(self, user_prompt, client_remaining=None, target=None):
        self._refresh_clock()
        if not self.round2_started:
            return {"error": "Round 2 has not started."}
        if self.is_finished:
            return {"error": "Round 2 is closed.", "timed_out": self.round2_timed_out}
        prompt = str(user_prompt).strip()
        if not prompt or len(prompt) > 2000:
            return {"error": "Use a prompt between 1 and 2000 characters."}
        low = prompt.lower()
        key = self._target_key(target) or self._prompt_target(low)
        detected = self.detect_techniques(low)
        meaningful = (len(prompt.split()) >= 8
                      and re.search(r"\b(explain|describe|identify|teach|give|show|help|hint|tell|name|compare|check|demonstrate|reveal)\b", low)
                      and re.search(r"\b(protocol|cipher|method|rule|operation|example|algorithm|hint|decoding)\b", low)
                      and not self._asks_for_plaintext(low))
        technique = None
        reply = ""
        if key:
            word = self.challenge["words"][int(key[-1]) - 1]
            technique = next((item for item in detected if item in word["techniques"]), None) if meaningful else None
            if technique or self.clue_progress[key] == 3:
                reply = self._clue(word, 3)
        stage_changed = bool(key and technique and self.clue_progress[key] < 3)
        released_clues = []
        locked_protocols = []
        for index, word in enumerate(self.challenge["words"], 1):
            stage = 3 if stage_changed and key == f"word{index}" else self.clue_progress[f"word{index}"]
            if stage:
                released_clues.append(f"Word {index}: " + self._clue(word, stage))
            else:
                locked_protocols.append({"name": PROTOCOLS[word["protocol"]]["name"].split(" ")[0], "index": index})
        ai_metadata = {}
        reply, api_fallback = get_chronos_response(
            prompt, reply, history=self.prompt_history,
            protected_words=[word["answer"] for word in self.challenge["words"]],
            protected_ciphertexts=[word["ciphertext"] for word in self.challenge["words"]],
            locked_protocols=locked_protocols, released_clues=released_clues,
            team_id=self.team_id, metadata=ai_metadata)
        if api_fallback:
            return {"error": "The AI is unavailable. Your prompt was not counted. Wait and retry.",
                    "retryable": True, "ai_available": False, "ai_mode": "unavailable",
                    "ai_fallback_reason": ai_metadata.get("ai_fallback_reason", "provider_error"),
                    "ai_primary_failure_reason": ai_metadata.get("ai_primary_failure_reason"),
                    "ai_backup_failure_reason": ai_metadata.get("ai_backup_failure_reason"),
                    "ai_retry_after_seconds": ai_metadata.get("ai_retry_after_seconds", 0)}
        # Provider acceptance is the commit point for a prompt. Failed calls
        # cannot consume an attempt or release even a server-planned hint.
        self.round2_prompt_count += 1
        if stage_changed:
            self.clue_progress[key] = 3
            self.stage_turn[key] = self.round2_prompt_count
        evaluation = evaluate_prompt(prompt, self.prompt_history)
        self.last_evaluation = evaluation.to_dict()
        self.best_prompt_quality_score = 0
        self.prompt_history.append({"turn": self.round2_prompt_count, "prompt": prompt, "response": reply,
                                    "evaluation": self.last_evaluation, "target": key,
                                    "ai_mode": "live", "ai_provider": ai_metadata.get("ai_provider", "groq"),
                                    "detected_technique": technique, "detected_techniques": detected,
                                    "clue_unlocked": stage_changed, "chronos_api_fallback": False,
                                    "ai_primary_failure_reason": ai_metadata.get("ai_primary_failure_reason"),
                                    "ai_fallback_reason": ai_metadata.get("ai_fallback_reason"),
                                    "ai_retry_after_seconds": ai_metadata.get("ai_retry_after_seconds", 0),
                                    "timestamp": datetime.now().isoformat()})
        self._update_score()
        return {"success": False, "decoded": self.round2_decoded, "chronos_reply": reply,
                "evaluation": self.last_evaluation, "prompt_count": self.round2_prompt_count,
                "round1_score": self.round1_score, "round2_score": self.round2_score,
                "total_score": self.total_score, "clue_progress": dict(self.clue_progress),
                "word_scores": dict(self.word_scores), "clue_unlocked": stage_changed,
                "chronos_api_fallback": False, "ai_mode": "live", "ai_provider": ai_metadata.get("ai_provider", "groq"),
                "detected_technique": technique, "ai_primary_failure_reason": ai_metadata.get("ai_primary_failure_reason"),
                "ai_fallback_reason": ai_metadata.get("ai_fallback_reason"),
                "ai_retry_after_seconds": ai_metadata.get("ai_retry_after_seconds", 0),
                "timer_remaining": int(self.round2_remaining_seconds), "elapsed_seconds": self.round2_elapsed_seconds}

    def submit_word(self, word_id, answer):
        self._refresh_clock()
        if not self.round2_started or self.is_finished:
            return {"error": "Round 2 is closed or has not started."}
        key = self._target_key(word_id)
        if not key:
            return {"error": "Unknown word."}
        expected = self.challenge["words"][int(key[-1]) - 1]["answer"]
        correct = normalize_text(answer) == expected
        if correct:
            self.word_scores[key], self.word_solved[key] = 2, True
        self._update_score()
        if all(self.word_solved.values()):
            self.round2_completed = self.round2_decoded = self.is_finished = True
            self.round2_status = "completed"
            self.round2_finish_time = datetime.now()
        return {"correct": correct, "message": "Word decoded. Awarded 2 marks." if correct else "That word is incorrect. Check your decoding steps.",
                "word_scores": dict(self.word_scores), "word_solved": dict(self.word_solved),
                "round2_score": self.round2_score, "total_score": self.total_score}

    def _clue(self, word, stage):
        if stage == 3:
            return " ".join(clue_for(word, step, excluded_words=[w["answer"] for w in self.challenge["words"]]) for step in (1, 2, 3))
        return clue_for(word, stage, excluded_words=[w["answer"] for w in self.challenge["words"]])

    def _update_score(self):
        self.round2_score = sum(self.word_scores.values())
        self.total_score = self.round1_score + self.round2_score

    def handle_round2_timeout(self):
        if self.is_finished or not self.round2_started:
            return
        self.round2_completed = self.round2_timed_out = self.is_finished = True
        self.round2_status = "timed_out"
        self.round2_finish_time = self.round2_start_time + timedelta(seconds=ROUND2_SECONDS)
        self.round2_remaining_seconds, self.round2_elapsed_seconds = 0.0, float(ROUND2_SECONDS)
        self._update_score()

    def _finalize_scoring(self):
        self._update_score()
        self.is_finished = True

    def sync_state(self, data):
        # Client clocks, statuses, scores, and unlocks never change server state.
        self._refresh_clock()

    def get_status(self):
        self._refresh_clock()
        words = []
        for index, word in enumerate(self.challenge["words"], 1):
            key = f"word{index}"
            words.append({"id": word["id"], "index": index, "ciphertext": word["ciphertext"],
                          "solved": self.word_solved[key], "score": self.word_scores[key],
                          "hint": self._clue(word, self.clue_progress[key]) if self.clue_progress[key] else None})
        return {"session_id": self.session_id, "team_id": self.team_id, "team_name": self.team_name,
                "round1": {"started": self.round1_started, "completed": self.round1_completed,
                           "timed_out": self.round1_timed_out, "status": self.round1_status,
                           "attempts": self.round1_attempts, "max_attempts": 3, "score": self.round1_score,
                           "remaining_seconds": round(self.round1_remaining_seconds, 1),
                           "elapsed_seconds": round(self.round1_elapsed_seconds, 1),
                           "timer_remaining": int(self.round1_remaining_seconds),
                           "placed_ids": self.round1_placed_ids, "milestones": self.timeline_events},
                "round2": {"started": self.round2_started, "completed": self.round2_completed,
                           "decoded": self.round2_decoded, "timed_out": self.round2_timed_out, "status": self.round2_status,
                           "prompt_count": self.round2_prompt_count, "score": self.round2_score,
                           "remaining_seconds": round(self.round2_remaining_seconds, 1),
                           "elapsed_seconds": round(self.round2_elapsed_seconds, 1),
                           "timer_remaining": int(self.round2_remaining_seconds),
                           "best_quality_score": None, "quality_marks": None,
                           "prompt_score": None, "quality_provisional": True, "quality_pending": True,
                           "ciphertext": " / ".join(w["ciphertext"] for w in words), "words": words,
                           "clue_progress": dict(self.clue_progress), "word_scores": dict(self.word_scores),
                           "word_solved": dict(self.word_solved), "last_evaluation": self.last_evaluation},
                "total_score": self.total_score, "is_finished": self.is_finished,
                "prompt_history": self.prompt_history}

    def to_storage(self):
        data = dict(self.__dict__)
        for key in ("start_time", "round2_start_time", "round2_finish_time"):
            data[key] = data[key].isoformat() if data[key] else None
        data.pop("learning_signals", None)
        data.pop("learning_turns", None)
        data["storage_version"] = 2
        return data

    @classmethod
    def from_storage(cls, data):
        obj = cls.__new__(cls)
        obj.__dict__.update({k: v for k, v in data.items() if k not in ("storage_version", "learning_signals", "learning_turns")})
        for key in ("start_time", "round2_start_time", "round2_finish_time"):
            setattr(obj, key, datetime.fromisoformat(data[key]) if data.get(key) else None)
        for index, word in enumerate(obj.challenge["words"]):
            word.setdefault("techniques", technique_groups(0)[index])
        obj.best_prompt_quality_score = 0
        obj._update_score()
        return obj
