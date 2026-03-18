"""
Temporal consensus manager for multi-frame voting
"""

import numpy as np
from collections import defaultdict, deque, Counter
from typing import Dict, Tuple

# Import config
import sys
import os
from config import VOTING_WINDOW_SIZE, MIN_CONSENSUS_FRAMES

def _is_unknown(name: str) -> bool:
    """Return True if name represents an Unknown identity."""
    return name.startswith("Unknown")

class TemporalConsensus:
    """Manages temporal voting and consensus for face recognition with optimized vote counting."""

    def __init__(self):
        self.track_votes: Dict[int, deque] = defaultdict(
            lambda: deque(maxlen=VOTING_WINDOW_SIZE))
        self.track_confidences: Dict[int, deque] = defaultdict(
            lambda: deque(maxlen=VOTING_WINDOW_SIZE))
        # Use VOTING_WINDOW_SIZE consistently for all attribute deques
        self.track_ages: Dict[int, deque] = defaultdict(
            lambda: deque(maxlen=VOTING_WINDOW_SIZE))
        self.track_genders: Dict[int, deque] = defaultdict(
            lambda: deque(maxlen=VOTING_WINDOW_SIZE))
        self.track_quality_scores: Dict[int, deque] = defaultdict(
            lambda: deque(maxlen=VOTING_WINDOW_SIZE))
        # Optimization: Maintain running vote counts for faster consensus
        self.track_vote_counts: Dict[int, Dict[str, float]] = defaultdict(dict)

    def add_vote(self, track_id: int, name: str, confidence: float,
                 age: int, gender: str, quality_score: float):
        """
        Record a new recognition vote for a track.
        
        Weight scheme: confidence * quality_score, with Unknown votes discounted
        to 30% weight to allow known identities to win even with fewer frames.
        All five deques are appended together to stay in sync.
        """
        # Optimization: Remove old vote from counts if deque is full
        if len(self.track_votes[track_id]) == VOTING_WINDOW_SIZE:
            old_vote = self.track_votes[track_id][0]
            old_conf = self.track_confidences[track_id][0]
            old_qual = self.track_quality_scores[track_id][0]
            old_weight = old_conf * old_qual
            if _is_unknown(old_vote):
                old_weight *= 0.3
            if old_vote in self.track_vote_counts[track_id]:
                self.track_vote_counts[track_id][old_vote] = max(
                    0.0,
                    self.track_vote_counts[track_id][old_vote] - old_weight
                )
                if self.track_vote_counts[track_id][old_vote] <= 0:
                    del self.track_vote_counts[track_id][old_vote]

        # Add new vote — all deques appended atomically in the same call
        self.track_votes[track_id].append(name)
        self.track_confidences[track_id].append(confidence)
        self.track_ages[track_id].append(age)
        self.track_genders[track_id].append(gender)
        self.track_quality_scores[track_id].append(quality_score)

        # Optimization: Update running counts
        weight = confidence * quality_score
        if _is_unknown(name):
            weight *= 0.3
        if name not in self.track_vote_counts[track_id]:
            self.track_vote_counts[track_id][name] = 0.0
        self.track_vote_counts[track_id][name] += weight

    def get_consensus(self, track_id: int) -> Tuple[str, float, int, str, float]:
        """
        Get consensus name and stats for a track using optimized vote counting.
        Returns: (name, confidence, age, gender, avg_quality)
        """
        votes = list(self.track_votes[track_id])
        confidences = list(self.track_confidences[track_id])
        ages = list(self.track_ages[track_id])
        genders = list(self.track_genders[track_id])
        qualities = list(self.track_quality_scores[track_id])

        if not votes:
            return "Unknown", 0.0, 0, "", 0.0

        # Optimization: Use pre-computed vote counts (much faster than recomputing from scratch).
        # If the running counts map is empty despite having votes (e.g. all weights were zeroed
        # and cleaned up), fall back to a fresh weighted sum from the raw deques.
        weighted_votes = self.track_vote_counts[track_id]
        if weighted_votes:
            best_name = max(weighted_votes, key=weighted_votes.__getitem__)
        else:
            # Fallback: recompute weights from the raw deques
            temp: Dict[str, float] = {}
            for v, c, q in zip(votes, confidences, qualities):
                w = c * q * (0.3 if _is_unknown(v) else 1.0)
                temp[v] = temp.get(v, 0.0) + w
            best_name = max(temp, key=temp.__getitem__) if temp else "Unknown"

        # Enforce minimum consensus before committing to a known identity
        final_name = best_name
        if not _is_unknown(final_name) and len(votes) < MIN_CONSENSUS_FRAMES:
            final_name = "Unknown"

        # Compute avg_confidence from the *best* known identity's votes,
        # regardless of whether we've overridden to "Unknown" this frame.
        name_confidences = [confidences[i] for i, n in enumerate(votes) if n == best_name]
        avg_confidence = float(np.mean(name_confidences)) if name_confidences else 0.0

        avg_age = int(np.mean(ages)) if ages else 0

        # Filter meaningless gender strings before counting
        valid_genders = [g for g in genders if g and g != "Unknown"]
        most_common_gender = Counter(valid_genders).most_common(1)[0][0] if valid_genders else ""

        avg_quality = float(np.mean(qualities)) if qualities else 0.0

        return final_name, avg_confidence, avg_age, most_common_gender, avg_quality

    def clear_track(self, track_id: int):
        self.track_votes.pop(track_id, None)
        self.track_confidences.pop(track_id, None)
        self.track_ages.pop(track_id, None)
        self.track_genders.pop(track_id, None)
        self.track_quality_scores.pop(track_id, None)
        self.track_vote_counts.pop(track_id, None)
