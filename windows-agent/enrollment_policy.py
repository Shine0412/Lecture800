from datetime import datetime


DEFAULT_LOCATION_RULES = {
    "firstSite": True,
    "secondSite": True,
    "thirdSite": False,
    "nanjing": False,
    "wuhan": False,
    "other": True,
}

LOCATION_LABELS = {
    "firstSite": "一号院",
    "secondSite": "二号院",
    "thirdSite": "三号院",
    "nanjing": "南京校区",
    "wuhan": "武汉校区",
    "other": "其他地点",
}


def normalize_location_rules(rules):
    supplied = rules if isinstance(rules, dict) else {}
    return {
        key: supplied.get(key) if isinstance(supplied.get(key), bool) else default
        for key, default in DEFAULT_LOCATION_RULES.items()
    }


def location_category(lecture):
    title = str(lecture.get("title") or "").lstrip()
    location = str(lecture.get("location") or "")
    if title.startswith("南京校区"):
        return "nanjing"
    if title.startswith("武汉校区"):
        return "wuhan"
    if "三号院" in location:
        return "thirdSite"
    if "一号院" in location:
        return "firstSite"
    if "二号院" in location:
        return "secondSite"
    return "other"


def exclusion_reason(lecture, location_rules=None):
    rules = normalize_location_rules(location_rules)
    category = location_category(lecture)
    if not rules[category]:
        return f"{LOCATION_LABELS[category]}未在自动报名范围内"
    return None


def start_sort_key(lecture):
    try:
        return datetime.fromisoformat(lecture["startAt"])
    except (KeyError, TypeError, ValueError):
        return datetime.max.replace(tzinfo=datetime.now().astimezone().tzinfo)


def priority_sort_key(lecture):
    # 一号院优先，其余允许的地点按开始时间排列；不代表只报名一号院。
    return (0 if "一号院" in str(lecture.get("location") or "") else 1, start_sort_key(lecture))


def select_candidates(lectures, location_rules=None):
    return sorted(
        (
            lecture for lecture in lectures
            if lecture.get("level") == "800"
            and lecture.get("status") == "open"
            and not lecture.get("registration")
            and exclusion_reason(lecture, location_rules) is None
        ),
        key=priority_sort_key,
    )
