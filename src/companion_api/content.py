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
#
# Two kinds, one catalogue: colourways recolour Robert's original model, and
# outfits (`casual` onwards in the room's list) are modelled garments the room
# swaps in whole. Outfit ids follow the character package's skin folders, with
# `_` written `-` because cosmetic ids are letters, digits and hyphens.
COSMETICS = (
    {"id": "default", "name": "Robert Original",
     "description": "The appearance Robert arrives in.", "cost": 0},
    {"id": "sunset", "name": "Sunset Copper",
     "description": "Warm copper, the colour of the room at dusk.", "cost": 5},
    {"id": "casual", "name": "Casual",
     "description": "A comfy everyday outfit for easy learning days.", "cost": 10},
    {"id": "dune", "name": "Dune Walker",
     "description": "Pale desert sand that catches the low sun.", "cost": 15},
    {"id": "gardener", "name": "Gardener",
     "description": "A straw hat and garden green for growing new ideas.", "cost": 20},
    {"id": "arab-thobe", "name": "Arab Thobe",
     "description": "A crisp white thobe, smart and comfortable.", "cost": 20},
    {"id": "explorer", "name": "Explorer",
     "description": "A safari outfit for curious adventures across the dunes.", "cost": 25},
    {"id": "cowboy", "name": "Cowboy",
     "description": "A vest, jeans and boots for the desert trail.", "cost": 25},
    {"id": "midnight", "name": "Midnight Teal",
     "description": "Deep teal for the quiet end of a learning day.", "cost": 30},
    {"id": "astronaut", "name": "Astronaut",
     "description": "A space suit for learners who reach for the stars.", "cost": 35},
)

CATALOGUE = {item["id"]: item for item in COSMETICS}
