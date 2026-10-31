import json
import os
import time
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from google import genai
from google.genai import types


MODELS = [
    "gemini-3.1-flash-lite",
    "gemini-3.5-flash-lite",
    "gemini-3.5-flash",
]

QUESTIONS = [
    {
        "name": "دردشة الوكالة",
        "text": "واحد جديد دخل الوكالة وقال: أنا مش فاهم الناس هنا بتهزر ولا بتتكلم جد! ترد عليه إزاي؟",
    },
    {
        "name": "رأي وموقف",
        "text": "صاحبك مصرّ يشتري جهاز غالي لمجرد إن شكله جامد، مع إن إمكانياته أقل من جهاز أرخص. تناقشه إزاي من غير ما توافقه لمجرد المجاملة؟",
    },
]

RESEARCH_INSTRUCTIONS = """
[RESEARCH AND FRESHNESS POLICY]
لا تفترض أن معلوماتك الداخلية حديثة دائمًا.
1. أجب مباشرةً عن المعلومات الثابتة والمفاهيم المعروفة.
2. استخدم web_search عند الحاجة لمعلومات حديثة أو متخصصة أو قابلة للتحقق خارجيًا.
3. لا تدّعِ أنك بحثت أو تحققت من معلومة ما لم تستخدم أداة البحث بالفعل.
4. لا تختلق مصادر أو روابط أو مراجع.
5. حافظ على شخصية فهيم وطريقته الطبيعية في الكلام.
[ملاحظة الاختبار]
لا توجد أداة بحث متصلة في هذا الاختبار؛ لا تدّعِ إجراء بحث.
""".strip()


def build_system_instruction(personality):
    now = datetime.now(ZoneInfo("Africa/Cairo"))
    days = [
        "الاثنين", "الثلاثاء", "الأربعاء", "الخميس",
        "الجمعة", "السبت", "الأحد",
    ]
    time_context = (
        "\n\n[CURRENT DATE AND TIME - AUTHORITATIVE]\n"
        f"اليوم: {days[now.weekday()]}\n"
        f"التاريخ: {now.strftime('%d-%m-%Y')}\n"
        f"الوقت: {now.strftime('%I:%M %p')}\n"
        "التوقيت: القاهرة، مصر."
    )
    return personality + time_context + "\n\n" + RESEARCH_INSTRUCTIONS


def main():
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise SystemExit("GEMINI_API_KEY is missing.")

    personality_path = Path("prompts/fahim_personality.txt")
    if not personality_path.exists():
        raise SystemExit("Personality file not found.")

    personality = personality_path.read_text(encoding="utf-8")
    system_instruction = build_system_instruction(personality)
    client = genai.Client(api_key=api_key)
    results = []

    print("Fahim Effendi — Gemini model comparison")
    print(f"System instruction: {len(system_instruction)} characters")
    print("Settings: thinking=minimal, max_output_tokens=1024")

    for model_name in MODELS:
        print(f"\n{'=' * 60}\nMODEL: {model_name}\n{'=' * 60}")

        for question in QUESTIONS:
            print(f"\n--- {question['name']} ---")
            started = time.perf_counter()

            entry = {
                "model": model_name,
                "question_name": question["name"],
                "question": question["text"],
            }

            try:
                response = client.models.generate_content(
                    model=model_name,
                    contents=question["text"],
                    config=types.GenerateContentConfig(
                        system_instruction=system_instruction,
                        thinking_config=types.ThinkingConfig(
                            thinking_level="minimal"
                        ),
                        max_output_tokens=1024,
                        automatic_function_calling=(
                            types.AutomaticFunctionCallingConfig(disable=True)
                        ),
                    ),
                )

                elapsed = time.perf_counter() - started
                usage = response.usage_metadata
                answer = response.text or "[EMPTY RESPONSE]"

                entry.update({
                    "seconds": round(elapsed, 2),
                    "answer": answer,
                    "finish_reason": (
                        str(response.candidates[0].finish_reason)
                        if response.candidates else None
                    ),
                    "prompt_tokens": getattr(usage, "prompt_token_count", None),
                    "output_tokens": getattr(usage, "candidates_token_count", None),
                    "total_tokens": getattr(usage, "total_token_count", None),
                    "error": None,
                })

                print(f"Time: {elapsed:.2f}s")
                print(
                    f"Tokens: input={entry['prompt_tokens']}, "
                    f"output={entry['output_tokens']}, "
                    f"total={entry['total_tokens']}"
                )
                print(f"Answer:\n{answer}")

            except Exception as error:
                elapsed = time.perf_counter() - started
                entry.update({
                    "seconds": round(elapsed, 2),
                    "error": f"{type(error).__name__}: {error}",
                })
                print(f"FAILED after {elapsed:.2f}s: {entry['error']}")

            results.append(entry)
            time.sleep(2)

    summary = {}

    for model_name in MODELS:
        successful = [
            item for item in results
            if item["model"] == model_name and not item.get("error")
        ]

        if successful:
            summary[model_name] = {
                "successful_runs": len(successful),
                "average_seconds": round(
                    sum(x["seconds"] for x in successful) / len(successful), 2
                ),
                "average_total_tokens": round(
                    sum(x["total_tokens"] or 0 for x in successful)
                    / len(successful), 1
                ),
            }

    output = {
        "created_at": datetime.now(
            ZoneInfo("Africa/Cairo")
        ).isoformat(),
        "settings": {
            "thinking_level": "minimal",
            "max_output_tokens": 1024,
            "personality_file": str(personality_path),
        },
        "summary": summary,
        "results": results,
    }

    output_path = Path("scripts/gemini_model_comparison_results.json")
    output_path.write_text(
        json.dumps(output, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    print("\nSUMMARY")
    for model_name, stats in summary.items():
        print(
            f"{model_name}: avg={stats['average_seconds']}s, "
            f"avg tokens={stats['average_total_tokens']}, "
            f"success={stats['successful_runs']}/{len(QUESTIONS)}"
        )

    print(f"\nFull results saved to: {output_path}")


if __name__ == "__main__":
    main()
