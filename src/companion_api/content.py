"""Synthetic orientation copy and the cosmetic catalogue. No religious sources are published."""


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


# Looks Robert can wear, cheapest first. `cost` is in the same learning stars
# the lesson ledger grants, so a look is earned by learning and never bought
# with real money, traded, or won by chance. Ids match the room's own fixed
# allowlist: the service never invents one, and the room installs nothing it
# was not built with.
COSMETICS = (
    {"id": "default", "name": "Robert Original",
     "description": "The appearance Robert arrives in.", "cost": 0},
    {"id": "sunset", "name": "Sunset Copper",
     "description": "Warm copper, the colour of the room at dusk.", "cost": 5},
    {"id": "dune", "name": "Dune Walker",
     "description": "Pale desert sand that catches the low sun.", "cost": 15},
    {"id": "midnight", "name": "Midnight Teal",
     "description": "Deep teal for the quiet end of a learning day.", "cost": 30},
)

CATALOGUE = {item["id"]: item for item in COSMETICS}
