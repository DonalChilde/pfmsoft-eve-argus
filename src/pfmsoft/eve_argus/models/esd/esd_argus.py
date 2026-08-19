"""Static data models customized for Argus usage."""

from dataclasses import dataclass, field


@dataclass(slots=True, kw_only=True)
class Materials:
    type_id: int
    quantity: int


@dataclass(slots=True, kw_only=True)
class Skills:
    type_id: int
    level: int


@dataclass(slots=True, kw_only=True)
class Copying:
    result_id: int
    blueprint_id: int
    time: int
    materials: list[Materials] | None = field(default_factory=list[Materials])
    skills: list[Skills] | None = field(default_factory=list[Skills])


@dataclass(slots=True, kw_only=True)
class Invention:
    result_id: int
    blueprint_id: int
    probability: float
    time: int
    materials: list[Materials] | None = field(default_factory=list[Materials])
    skills: list[Skills] | None = field(default_factory=list[Skills])


@dataclass(slots=True, kw_only=True)
class Reaction:
    result_id: int
    blueprint_id: int
    time: int
    materials: list[Materials] | None = field(default_factory=list[Materials])
    skills: list[Skills] | None = field(default_factory=list[Skills])


@dataclass(slots=True, kw_only=True)
class ResearchMaterial:
    result_id: int
    blueprint_id: int
    time: int
    materials: list[Materials] | None = field(default_factory=list[Materials])
    skills: list[Skills] | None = field(default_factory=list[Skills])


@dataclass(slots=True, kw_only=True)
class ResearchTime:
    result_id: int
    blueprint_id: int
    time: int
    materials: list[Materials] | None = field(default_factory=list[Materials])
    skills: list[Skills] | None = field(default_factory=list[Skills])


@dataclass(slots=True, kw_only=True)
class Manufacture:
    result_id: int
    portion_size: int
    blueprint_id: int
    time: int
    materials: list[Materials] | None = field(default_factory=list[Materials])
    skills: list[Skills] | None = field(default_factory=list[Skills])
