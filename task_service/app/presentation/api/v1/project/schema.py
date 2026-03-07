from pydantic import BaseModel


class StartProject(BaseModel):
    template_id: int


class Task(BaseModel):
    title: str
    description: str


class SprintOrder(BaseModel):
    order: int
    title: str
    tasks: list[Task]


class ProjectTemplate(BaseModel):
    project_template_id: int | None
    title: str
    description: str
    sprints: list[SprintOrder]
    direction: str
    level: str