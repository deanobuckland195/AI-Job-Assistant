"""Curated offline question bank; prompts/guidance are snapshotted per session."""

BANK_VERSION = "1.0"
STAR = {
    "situation": "Describe the real context, people involved and constraint. Keep it brief.",
    "task": "Explain your specific responsibility or goal, not only the team's objective.",
    "action": "Describe what you personally did, why, and how you checked your work.",
    "result": "State the actual outcome or learning. Quantify only with real evidence; qualitative results are valid.",
}
ROLES = {
    "ai-engineering-apprentice": "AI Engineering apprenticeship",
    "junior-software-engineer": "Junior software engineering",
    "data-analyst": "Data analysis",
    "general": "General early-career interview",
}
COACHING = {
    "ai-engineering-apprentice": ["Practise explaining a small AI/data project, your baseline and how you checked errors.",
                                  "Plan one manageable learning goal and a project artifact that could demonstrate progress."],
    "junior-software-engineer": ["Practise explaining one design decision and the tests that supported it.",
                                 "Identify one small improvement to a real project and how you would validate it."],
    "data-analyst": ["Practise explaining an analysis limitation to a non-technical audience.",
                     "Plan a small reproducible analysis with documented assumptions and checks."],
    "general": ["Choose a real example from study, work, volunteering or a personal project.",
                "Reflect on one learning goal and the evidence you would collect to review progress."],
}


def question(code, kind, prompt, topics=()):
    guidance = (list(STAR.values()) if kind == "behavioural" else
                ["Answer the question directly, explain your reasoning and use a truthful example where useful.",
                 "Acknowledge uncertainty and limitations. Do not invent experience to fill a gap."])
    return {"code": code, "kind": kind, "prompt": prompt, "guidance": guidance, "topics": list(topics)}


COMMON = [
    question("teamwork", "behavioural", "Describe a time you worked with others to solve a difficult problem. What was your own contribution?"),
    question("learning-plan", "reflection", "Which skill would you develop next, and what practical evidence would show progress?", ("goal", "practice", "evidence")),
]
BANK = {
    "ai-engineering-apprentice": [
        question("ai-project", "behavioural", "Tell me about a small software or data project. What did you do, how did you check it, and what happened?"),
        question("data-leakage", "technical", "How would you separate training, validation and test data, and avoid data leakage?", ("training", "validation", "test", "leakage")),
        question("ai-privacy", "technical", "Before using a CV or customer data with an AI service, what privacy and reliability checks would you make?", ("consent", "privacy", "limits", "validation")),
        question("apprentice-motivation", "motivation", "Why an AI Engineering apprenticeship, and how would you balance learning with practical delivery?", ("learning", "practice", "feedback")), *COMMON],
    "junior-software-engineer": [
        question("debugging", "behavioural", "Describe a real bug you investigated. How did you isolate it and check the fix?"),
        question("api-reliability", "technical", "How would you handle an unreliable external API in a small Python application?", ("timeout", "error", "test")),
        question("design-tradeoff", "technical", "Explain a design trade-off in a project and how you would evaluate a different approach.", ("trade-off", "test", "limitation")),
        question("software-motivation", "motivation", "Why this early-career software role, and what would you like to learn first?"), *COMMON],
    "data-analyst": [
        question("analysis-project", "behavioural", "Describe a real analysis you carried out. What question did it answer and what limitations remained?"),
        question("data-quality", "technical", "How would you check missing values, duplicates and inconsistent data before analysis?", ("missing", "duplicates", "validation")),
        question("communicating-data", "behavioural", "Describe a time you explained findings or uncertainty to someone unfamiliar with the topic."),
        question("analysis-motivation", "motivation", "What interests you about data analysis, and how would you develop your skills?"), *COMMON],
    "general": [
        question("general-example", "behavioural", "Describe a challenge from work, study, volunteering or a personal project and how you handled it."),
        question("general-motivation", "motivation", "Why does this type of role interest you? Link your interests to real examples."),
        question("general-reflection", "reflection", "What would you do differently in a recent project, and how would you check the improvement?"),
        question("general-explanation", "technical", "Explain a process or tool you know to someone new to it. What are its limitations?", ("example", "limitation")), *COMMON],
}


def questions_for(role_id, count=6):
    if not isinstance(role_id, str) or role_id not in BANK or type(count) is not int or not 1 <= count <= len(BANK[role_id]):
        raise ValueError("Choose a listed role and a question count from 1 to 6.")
    return [dict(item, guidance=list(item["guidance"]), topics=list(item["topics"])) for item in BANK[role_id][:count]]
