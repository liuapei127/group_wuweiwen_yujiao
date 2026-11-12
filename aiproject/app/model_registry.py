"""Import all implemented models into the shared metadata, without creating tables."""
from importlib import import_module

MODEL_MODULES = (
    "app.ai.assistant.models",
    "app.modules.auth.models",
    "app.modules.consultant.models",
    "app.modules.employee_report.models",
    "app.modules.student_admin.models",
    "app.modules.organization.models",
    "app.modules.onboarding.models",
    "app.modules.score.models",
    "app.modules.feedback.models",
    "app.modules.todo.models",
)


def register_models():
    for module in MODEL_MODULES:
        import_module(module)
