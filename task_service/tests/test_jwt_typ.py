from pathlib import Path


def test_token_services_require_access_typ_in_source():
    roots = Path(__file__).resolve().parents[2]
    files = [
        roots / "task_service/app/infrastructure/token_service/gateway.py",
        roots / "submission_service/app/infrastructure/token_service/gateway.py",
        roots / "agent_service/app/presentation/api/deps.py",
        roots / "user_service/app/infrastructure/authorization/token_service.py",
    ]
    for path in files:
        text = path.read_text(encoding="utf-8")
        assert "typ" in text
        assert '!= "access"' in text or "!= expected" in text or "typ != expected" in text
