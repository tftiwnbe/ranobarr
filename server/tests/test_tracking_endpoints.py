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
