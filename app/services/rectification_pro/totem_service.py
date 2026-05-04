from __future__ import annotations

from app.models.rectification_pro_models import CandidateTime, MethodMatch


class TotemService:
    def evaluate_candidate(self, *, candidate: CandidateTime) -> dict[str, object]:
        degree_index = int(candidate.asc_degree) + (self._sign_offset(candidate.asc_sign)) + 1
        degree_index = max(1, min(360, degree_index))
        return {
            "asc_degree_index": degree_index,
            "asc_sign": candidate.asc_sign,
            "degree_in_sign": int(candidate.asc_degree),
            "totem_available": False,
            "totem_source": None,
            "warnings": ["totem_database_not_connected"],
        }

    def as_method_match(self, *, event_id: str, candidate: CandidateTime) -> MethodMatch:
        return MethodMatch(
            event_id=event_id,
            method="totem",
            matches=[self.evaluate_candidate(candidate=candidate)],
            event_score=0.0,
            warnings=["totem_database_not_connected"],
        )

    @staticmethod
    def _sign_offset(sign_name_en: str) -> int:
        signs = [
            "Aries",
            "Taurus",
            "Gemini",
            "Cancer",
            "Leo",
            "Virgo",
            "Libra",
            "Scorpio",
            "Sagittarius",
            "Capricorn",
            "Aquarius",
            "Pisces",
        ]
        try:
            idx = signs.index(sign_name_en)
        except ValueError:
            idx = 0
        return idx * 30
