from pathlib import Path

PERSONALITY_FILE = (
    Path(__file__).resolve().parent.parent
    / "prompts"
    / "fahim_personality.txt"
)


def load_personality() -> str:
    if not PERSONALITY_FILE.exists():
        raise FileNotFoundError(
            f"Personality file not found: {PERSONALITY_FILE}"
        )

    personality = PERSONALITY_FILE.read_text(
        encoding="utf-8"
    ).strip()

    if not personality:
        raise ValueError("Personality file is empty.")

    return personality
