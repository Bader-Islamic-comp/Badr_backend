"""Synthetic orientation copy. No religious sources are published."""


def lessons():
    return {"items": [{"id": "demo-learning", "title": "Meet your learning companion",
                       "summary": "Practice using your learning space.", "kind": "orientation",
                       "steps": ["Choose a comfortable place to learn.",
                                 "Take your time. You can pause whenever you need.",
                                 "Ask a trusted adult when you need help."], "reward": 5}]}


def challenges(completed: bool):
    return {"items": [{"id": "demo-practice", "title": "Explore one learning activity",
                       "description": "Complete the orientation with Robert.", "completed": completed,
                       "verification": "lesson_completion"}]}

