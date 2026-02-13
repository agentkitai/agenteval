"""Semantic similarity grader using sentence-transformers."""

from __future__ import annotations

from dataclasses import dataclass, field

from agenteval.models import EvalCase, AgentResult, GradeResult


@dataclass
class SemanticGrader:
    """Compare agent output to expected text via cosine similarity."""

    expected: str = ""
    threshold: float = 0.8
    model_name: str = "all-MiniLM-L6-v2"

    _model: object = field(default=None, init=False, repr=False)

    async def grade(self, case: EvalCase, result: AgentResult) -> GradeResult:
        try:
            from sentence_transformers import SentenceTransformer
            from sentence_transformers.util import cos_sim
        except ImportError:
            raise ImportError(
                "sentence-transformers is required for the semantic grader. "
                "Install it with: pip install agentevalkit[semantic]"
            )

        if self._model is None:
            self._model = SentenceTransformer(self.model_name)
        embeddings = self._model.encode([self.expected, result.output], convert_to_tensor=True)
        similarity = float(cos_sim(embeddings[0], embeddings[1]).item())

        passed = similarity >= self.threshold
        return GradeResult(
            passed=passed,
            score=similarity,
            reason=f"Similarity {similarity:.3f} {'≥' if passed else '<'} {self.threshold}",
        )
