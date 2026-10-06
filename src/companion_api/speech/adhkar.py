"""The four short adhkar of the speech preview (owner decision D-A, 2026-10-06; ADR 0006).

The texts are the speech service's reviewed allowlist (Dua-a_stt `src/dua_speech/tts/copy/adhkar-allowlist.yaml`,
status draft, committee decision required); the names and transliterations are display copy. Both are drafts
awaiting review. Nothing here claims a virtue or a reward: stars in the dhikr game are for practice.
"""
REVIEW_STATUS = "draft"

ADHKAR = (
    {"id": "takbeer", "nameAr": "التكبير", "nameEn": "Takbeer", "transliteration": "Allahu akbar",
     "text": "اللَّهُ أَكْبَرُ"},
    {"id": "tasbeeh", "nameAr": "التسبيح", "nameEn": "Tasbeeh", "transliteration": "Subhan Allah",
     "text": "سُبْحَانَ اللَّهِ"},
    {"id": "tahmeed", "nameAr": "التحميد", "nameEn": "Tahmeed", "transliteration": "Alhamdu lillah",
     "text": "الْحَمْدُ لِلَّهِ"},
    {"id": "istighfar", "nameAr": "الاستغفار", "nameEn": "Istighfar", "transliteration": "Astaghfirullah",
     "text": "أَسْتَغْفِرُ اللَّهَ"},
)
ADHKAR_IDS = tuple(item["id"] for item in ADHKAR)
BY_ID = {item["id"]: item for item in ADHKAR}


def dua_id(dhikr_id: str) -> str:
    """The speech service registers each allowlisted dhikr as a one-segment dua `dhikr-<id>`."""
    return f"dhikr-{dhikr_id}"
