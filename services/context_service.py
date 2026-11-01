def build_reply_context(question, referenced_content):
    """Attach the exact replied-to message to the current user question."""
    current_question = (question or "").strip()
    parent_message = (referenced_content or "").strip()

    if not parent_message:
        return current_question

    if not current_question:
        current_question = "كمّل كلامك عن الرسالة دي."

    return (
        "[REPLY CONTEXT - MESSAGE THE MEMBER IS REPLYING TO]\n"
        f"{parent_message}\n\n"
        "[CURRENT MEMBER MESSAGE]\n"
        f"{current_question}"
    )


def build_history_question(question, has_reference=False):
    """Return only the member-authored text suitable for persistent history."""
    current_question = (question or "").strip()
    if current_question:
        return current_question
    if has_reference:
        return "كمّل كلامك عن الرسالة دي."
    return ""
