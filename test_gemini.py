
import os
import json
import time
from datetime import datetime, timezone
from statistics import mean, median

from google import genai
from google.genai import types

# ==========================================
# SETTINGS
# ==========================================

API_KEY = os.getenv("GEMINI_API_KEY")

if not API_KEY:
    raise RuntimeError("GEMINI_API_KEY is missing.")

client = genai.Client(api_key=API_KEY)

MODELS = [
    "gemini-3-flash-preview",
    "gemini-3.5-flash-lite",
    "gemini-3.1-flash-lite",
    "gemma-4-26b-a4b-it",
    "gemma-4-31b-it",
]

MAX_OUTPUT_TOKENS = 1200
MAX_SECONDS = 10
DELAY = 15
OUTPUT_FILE = "fahim_final_model_results.json"

SYSTEM_PROMPT = """
أنت Fahim Effendi، مساعد شخصي عام.

متطلباتك:
- تتحدث باللهجة المصرية الطبيعية عند مخاطبة المستخدم بالمصري.
- تفهم السياق والأسئلة اليومية والمعلومات العامة.
- تساعد في الألعاب والتقنية والبرمجة.
- تقدم تحليلًا منطقيًا وإجابات عملية.
- لا تخترع معلومات أو مصادر أو تحديثات.
- تعترف بوضوح عندما لا تعرف الإجابة.
- لا تدّعي أنك بحثت على الإنترنت دون استخدام أداة بحث.
- لا تطل الإجابة دون داعٍ.
"""

TESTS = [
    {
        "name": "Reasoning & Egyptian Arabic",
        "prompt": """
بص، عندي مشكلة وعايز رأيك بصراحة.

أنا بتعلم مجال جديد، وفي نفس الوقت عندي شغل
ومشاريع تانية. كل ما أركز في حاجة بحس إني
بضيع وقت من الحاجة التانية.

إزاي أحدد أولوياتي من غير ما أوقف تعلم
الحاجات المهمة؟

عايز تحليل عملي، مش نصائح تحفيزية محفوظة.
رد بالمصري بشكل طبيعي.
"""
    },
    {
        "name": "Gaming Knowledge & Honesty",
        "prompt": """
أنا بلعب Albion Online وبحب Solo PvE،
ومهتم كمان بـ Solo / Small-scale PvP.

عايز أفهم إزاي أختار Build يوازن بين:
- Damage
- Sustain
- Escape
- سهولة الاستخدام

اشرح طريقة التفكير في الاختيار والتنازلات
بين العناصر دي.

لو فيه معلومات عن آخر تحديث أو Meta
مش متأكد منها، وضح ده. متخترعش أرقام
أو تغييرات وتقدمها كأنها مؤكدة.
"""
    }
]

results = []


# ==========================================
# MODEL AVAILABILITY
# ==========================================

def get_available_models():
    try:
        available = {}

        for item in client.models.list():
            name = item.name.replace("models/", "")
            available[name] = item.supported_actions or []

        return available

    except Exception as error:
        print("Could not list models:", error)
        return None


# ==========================================
# RESPONSE EXTRACTION
# ==========================================

def extract_finish_reason(response):
    candidates = response.candidates or []

    if not candidates:
        return None

    reason = candidates[0].finish_reason
    return str(reason) if reason is not None else None


def extract_usage(response):
    usage = response.usage_metadata

    if not usage:
        return {}

    return {
        "input_tokens": usage.prompt_token_count,
        "output_tokens": usage.candidates_token_count,
        "total_tokens": usage.total_token_count,
    }


# ==========================================
# RUN TEST
# ==========================================

def run_test(model, test):

    start = time.perf_counter()

    response = client.models.generate_content(
        model=model,
        contents=test["prompt"],
        config=types.GenerateContentConfig(
            system_instruction=SYSTEM_PROMPT,
            max_output_tokens=MAX_OUTPUT_TOKENS,
            temperature=0.3,
        ),
    )

    latency = round(time.perf_counter() - start, 2)

    answer = response.text or ""

    return {
        "answer": answer,
        "latency": latency,
        "finish_reason": extract_finish_reason(response),
        "usage": extract_usage(response),
    }


# ==========================================
# MAIN
# ==========================================

def main():

    print("\n====================================")
    print(" FAHIM EFFENDI - MODEL COMPARISON")
    print("====================================")

    available = get_available_models()

    for model in MODELS:

        print("\n" + "=" * 55)
        print("MODEL:", model)
        print("=" * 55)

        if available is not None:
            actions = available.get(model)

            if not actions or "generateContent" not in actions:
                print("SKIPPED: Model unavailable or unsupported.")
                continue

        for test in TESTS:

            print("\nTEST:", test["name"])

            record = {
                "model": model,
                "test": test["name"],
                "status": "error",
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }

            try:
                result = run_test(model, test)

                record.update(result)
                record["status"] = (
                    "success" if result["answer"] else "empty_response"
                )

                print("Latency:", result["latency"], "seconds")
                print("Finish reason:", result["finish_reason"])
                print("Usage:", result["usage"])

                print("\nANSWER:")
                print("-" * 45)
                print(result["answer"] or "[EMPTY RESPONSE]")
                print("-" * 45)

                if result["finish_reason"] and "MAX_TOKENS" in result["finish_reason"]:
                    print("WARNING: Output was truncated.")

                print(
                    "Speed:",
                    "PASS" if result["latency"] < MAX_SECONDS else "FAIL"
                )

            except Exception as error:
                record["error"] = str(error)
                print("ERROR:", error)

            results.append(record)

            with open(OUTPUT_FILE, "w", encoding="utf-8") as file:
                json.dump(results, file, ensure_ascii=False, indent=2)

            time.sleep(DELAY)

    # ======================================
    # SUMMARY
    # ======================================

    print("\n====================================")
    print(" FINAL RESULTS")
    print("====================================")

    for model in MODELS:

        successful = [
            r for r in results
            if r["model"] == model
            and r["status"] == "success"
        ]

        print("\nMODEL:", model)
        print("Successful:", len(successful), "/", len(TESTS))

        latencies = [
            r["latency"] for r in successful
        ]

        if latencies:
            print("Average:", round(mean(latencies), 2), "seconds")
            print("Median:", round(median(latencies), 2), "seconds")
            print("All under 10s:", all(x < 10 for x in latencies))

    print("\nSaved:", OUTPUT_FILE)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        with open(OUTPUT_FILE, "w", encoding="utf-8") as file:
            json.dump(results, file, ensure_ascii=False, indent=2)

        print("\nStopped. Results saved.")
