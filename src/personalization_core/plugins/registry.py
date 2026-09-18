from __future__ import annotations

from personalization_core.domain.errors import InvalidArgumentError

from .builtins import FrequencyAggregator, RecencyDecayAggregator
from .contracts import FeatureAggregator, FeatureExtractor


class FeatureExtractorRegistry:
    def __init__(self) -> None:
        self._extractors: dict[tuple[str, str], FeatureExtractor] = {}
        self._aggregators: dict[tuple[str, str, str], FeatureAggregator] = {}

    def register_extractor(self, extractor: FeatureExtractor) -> None:
        name = self._validated_metadata(extractor.name, "extractor name")
        version = self._validated_metadata(extractor.version, "extractor version")
        key = (name, version)
        if key in self._extractors:
            raise InvalidArgumentError(
                f"extractor {name!r} version {version!r} is already registered"
            )
        self._extractors[key] = extractor

    def register_aggregator(self, aggregator: FeatureAggregator) -> None:
        name = self._validated_metadata(aggregator.name, "aggregator name")
        version = self._validated_metadata(aggregator.version, "aggregator version")
        dimension = self._validated_metadata(
            aggregator.dimension, "aggregator dimension"
        )
        key = (name, version, dimension)
        if key in self._aggregators:
            raise InvalidArgumentError(
                "aggregator "
                f"{name!r} version {version!r} dimension {dimension!r} "
                "is already registered"
            )
        self._aggregators[key] = aggregator

    def extractors_for(self, event_type: str) -> tuple[FeatureExtractor, ...]:
        result = [
            extractor
            for extractor in self._extractors.values()
            if event_type in extractor.supported_event_types
        ]
        return tuple(sorted(result, key=lambda item: (item.name, item.version)))

    def aggregators_for(self, dimension: str) -> tuple[FeatureAggregator, ...]:
        result = [
            aggregator
            for aggregator in self._aggregators.values()
            if aggregator.dimension in {dimension, "*"}
        ]
        return tuple(
            sorted(result, key=lambda item: (item.name, item.version, item.dimension))
        )

    def all_extractors(self) -> tuple[FeatureExtractor, ...]:
        return tuple(self._extractors[key] for key in sorted(self._extractors))

    def all_aggregators(self) -> tuple[FeatureAggregator, ...]:
        return tuple(self._aggregators[key] for key in sorted(self._aggregators))

    @classmethod
    def with_builtins(cls) -> FeatureExtractorRegistry:
        registry = cls()
        registry.register_aggregator(FrequencyAggregator())
        registry.register_aggregator(RecencyDecayAggregator())
        return registry

    @staticmethod
    def _validated_metadata(value: str, label: str) -> str:
        if not value.strip():
            raise InvalidArgumentError(f"{label} must not be blank")
        return value
