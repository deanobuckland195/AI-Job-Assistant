print("=== AI Job & Apprenticeship Assistant ===")

name = input("What is your name? ")

print(f"\nWelcome, {name}!")
print("Let's find out which skills you have.")

skills = input("\nEnter your current skills, separated by commas: ")
skill_list = skills.split(",")

print("\nYour current skills are:")

for skill in skill_list:
    print(f"- {skill.strip()}")

required_skills = ["python", "git", "sql", "apis", "machine learning"]

user_skills = []
for skill in skill_list:
    user_skills.append(skill.strip().lower())

matching_skills = []
missing_skills = []

for skill in required_skills:
    if skill in user_skills:
        matching_skills.append(skill)
    else:
        missing_skills.append(skill)

print("\n=== AI Developer Skill Check ===")

print("\nSkills you already have:")
for skill in matching_skills:
    print(f"✓ {skill}")

print("\nSkills you should learn:")
for skill in missing_skills:
    print(f"- {skill}")

match_percentage = (len(matching_skills) / len(required_skills)) * 100

print(f"\nAI Developer Match Score: {match_percentage:.0f}%")

if match_percentage >= 80:
    print("Excellent match! You are well prepared for this role.")
elif match_percentage >= 60:
    print("Good match! You have a strong foundation.")
elif match_percentage >= 40:
    print("You're making progress. Keep developing your missing skills.")
else:
    print("You're at the beginning. Focus on building the core skills first.")





