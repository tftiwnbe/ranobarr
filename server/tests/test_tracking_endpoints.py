from app.tracking.service import branch_id_of, chapter_key, select_chapters_for_rule


def test_chapter_key() -> None:
    assert chapter_key(1, 2) == "v1_ch2"
    assert chapter_key(None, None) == "v1_ch0"


def test_select_chapters_for_rule_default_branch() -> None:
    chapters = [
        {
            "volume": "1",
            "number": "1",
            "name": "Chapter 1",
            "index": 1,
            "branches": [{"branch_id": 5, "teams": [{"name": "A"}]}],
        },
        {
            "volume": "1",
            "number": "2",
            "name": "Chapter 2",
            "index": 2,
            "branches": [{"branch_id": 5, "teams": [{"name": "A"}]}],
        },
    ]
    selected = select_chapters_for_rule(chapters, branch_mode="default", selected_branch_id=None)
    assert [item.chapter_key for item in selected] == ["v1_ch1", "v1_ch2"]
    assert selected[0].branch_id == "5"


def test_branch_id_of() -> None:
    assert branch_id_of({"branch_id": 9}) == "9"
    assert branch_id_of(None) is None


async def test_healthcheck(client) -> None:
    response = await client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


async def test_jobs_endpoint_empty(client) -> None:
    response = await client.get("/api/v1/jobs")
    assert response.status_code == 200
    assert response.json() == []


async def test_artifacts_endpoint_empty(client) -> None:
    response = await client.get("/api/v1/artifacts")
    assert response.status_code == 200
    assert response.json() == []


async def test_source_auth_crud(client) -> None:
    response = await client.get("/api/v1/source-auth/ranobelib")
    assert response.status_code == 200
    assert response.json() is None

    response = await client.put(
        "/api/v1/source-auth/ranobelib",
        json={"access_token": "token-a", "refresh_token": "token-r"},
    )
    assert response.status_code == 200
    assert response.json()["has_access_token"] is True
    assert response.json()["has_refresh_token"] is True

    response = await client.delete("/api/v1/source-auth/ranobelib")
    assert response.status_code == 204
