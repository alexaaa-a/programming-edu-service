from dataclasses import dataclass


@dataclass
class TaskDTO:
    title: str
    description: str


@dataclass
class SprintOrderDTO:
    order: int
    title: str
    tasks: list[TaskDTO]


@dataclass
class ProjectTemplateDTO:
    project_template_id: int | None
    title: str
    description: str
    sprints: list[SprintOrderDTO]
    direction: str
    level: str
