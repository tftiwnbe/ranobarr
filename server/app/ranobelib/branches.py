import re
from collections import defaultdict
from typing import Any


def get_formatted_branches_with_teams(
    novel_info: dict[str, Any], chapters_data: list[dict[str, Any]]
) -> dict[str, dict[str, Any]]:
    base_branches = _get_base_branches_from_novel_info(novel_info)
    chapter_counts = _get_chapter_counts_by_branch(chapters_data)
    teams_by_branch = _get_teams_by_branch(chapters_data)

    formatted_branches: dict[str, dict[str, Any]] = {}
    all_branch_ids = set(base_branches.keys()) | set(chapter_counts.keys())

    for branch_id in all_branch_ids:
        if chapter_counts.get(branch_id, 0) == 0:
            continue

        branch_info = base_branches.get(branch_id, {"id": branch_id, "teams": [], "active_teams": []})
        all_team_names = teams_by_branch.get(branch_id, set())

        formatted_branches[branch_id] = {
            "id": branch_id,
            "name": _format_branch_name(branch_info),
            "chapter_count": chapter_counts.get(branch_id, 0),
            "team_names": sorted(list(all_team_names)),
        }

    return formatted_branches


def get_branch_info_for_display(branch_info: dict[str, Any]) -> str:
    branch_name = branch_info["name"]
    chapter_count = branch_info["chapter_count"]
    team_names = branch_info["team_names"]

    result = branch_name

    if team_names:
        name_parts = {part.strip() for part in branch_name.split(",")}
        if set(team_names) - name_parts:
            result += f" [{', '.join(team_names)}]"

    result += f" ({chapter_count} chapters)"
    return result


def get_default_branch_chapters(chapters_data: list[dict[str, Any]]) -> list[dict[str, Any]]:
    sorted_chapters = sorted(chapters_data, key=lambda x: x.get("index", 0))
    sorted_chapters.sort(key=lambda x: _parse_chapter_number_for_sort(x.get("number", "0")))

    chapter_branch_map: dict[tuple[str, str], dict[str, dict[str, Any]]] = defaultdict(dict)
    unique_keys: list[tuple[str, str]] = []
    seen_keys: set[tuple[str, str]] = set()

    for chapter in sorted_chapters:
        key = (str(chapter.get("volume", "0")), str(chapter.get("number", "0")))
        if key not in seen_keys:
            unique_keys.append(key)
            seen_keys.add(key)

        for branch in chapter.get("branches", []):
            branch_id = _branch_id(branch)
            if branch_id not in chapter_branch_map[key]:
                chapter_branch_map[key][branch_id] = {"chapter": chapter, "branch": branch}

    selected_keys: set[tuple[str, str]] = set()
    final_list: list[dict[str, Any]] = []

    while len(selected_keys) < len(unique_keys):
        prioritized_branch_id = None
        for key in unique_keys:
            if key not in selected_keys:
                available = chapter_branch_map.get(key, {})
                if available:
                    prioritized_branch_id = next(iter(available))
                    break

        if not prioritized_branch_id:
            break

        for key in unique_keys:
            if key not in selected_keys:
                available = chapter_branch_map.get(key, {})
                if prioritized_branch_id in available:
                    final_list.append(available[prioritized_branch_id])
                    selected_keys.add(key)

    final_list.sort(key=lambda x: x["chapter"].get("index", 0))
    final_list.sort(key=lambda x: _parse_chapter_number_for_sort(x["chapter"].get("number", "0")))
    return final_list


def _get_base_branches_from_novel_info(novel_info: dict[str, Any]) -> dict[str, dict[str, Any]]:
    branches: dict[str, dict[str, Any]] = {}
    for team in novel_info.get("teams", []):
        details = team.get("details", {}) or {}
        branch_id = str(details.get("branch_id") if details.get("branch_id") is not None else "0")

        if branch_id not in branches:
            branches[branch_id] = {"id": branch_id, "teams": [], "active_teams": []}

        team_info = {
            "id": team.get("id", 0),
            "name": team.get("name", "Unknown"),
            "is_active": details.get("is_active", False),
        }
        branches[branch_id]["teams"].append(team_info)
        if team_info["is_active"]:
            branches[branch_id]["active_teams"].append(team_info)

    if "0" not in branches:
        branches["0"] = {"id": "0", "teams": [], "active_teams": []}

    return branches


def _get_chapter_counts_by_branch(chapters_data: list[dict[str, Any]]) -> dict[str, int]:
    counts: dict[str, int] = defaultdict(int)
    for chapter in chapters_data:
        for branch in chapter.get("branches", []):
            counts[_branch_id(branch)] += 1
    return counts


def _get_teams_by_branch(chapters_data: list[dict[str, Any]]) -> dict[str, set[str]]:
    teams: dict[str, set[str]] = defaultdict(set)
    for chapter in chapters_data:
        for branch in chapter.get("branches", []):
            if not isinstance(branch, dict):
                continue

            branch_id = _branch_id(branch)
            teams_list = branch.get("teams", []) or []
            if teams_list:
                for team in teams_list:
                    teams[branch_id].add(team.get("name", "Unknown"))
            else:
                team_info = branch.get("team")
                if team_info and isinstance(team_info, dict) and team_info.get("name"):
                    teams[branch_id].add(team_info["name"])
    return teams


def _format_branch_name(branch_info: dict[str, Any]) -> str:
    if branch_info["active_teams"]:
        return ", ".join(team["name"] for team in branch_info["active_teams"])

    if branch_info["teams"]:
        min_id_team = min(branch_info["teams"], key=lambda t: t.get("id", 0))
        return min_id_team["name"]

    return "Unknown"


def _branch_id(branch: Any) -> str:
    if isinstance(branch, dict):
        branch_id = branch.get("branch_id")
        return str(branch_id if branch_id is not None else "0")
    if branch is None:
        return "0"
    return str(branch)


def _parse_chapter_number_for_sort(number_str: str) -> tuple:
    parts = re.split(r"[.\-_]", str(number_str))
    result: list[int | str] = []
    for part in parts:
        try:
            result.append(int(part))
        except ValueError:
            result.append(part)
    return tuple(result)
