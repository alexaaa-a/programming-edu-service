"""Ключи Redis для кеширования."""

ACTIVE_USER_PROJECT = "task:active_user_project:{user_id}"
CURRENT_SPRINT = "task:current_sprint:{user_id}"
SPRINT_TASKS = "task:sprint_tasks:{sprint_id}:{user_id}"
TEMPLATE = "task:template:{template_id}"
TEMPLATES_FOR_USER = "task:templates_for_user:{user_id}"
