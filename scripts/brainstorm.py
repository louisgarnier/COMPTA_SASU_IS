#!/usr/bin/env python3
"""
Interactive Brainstorm Script — Stage 1 of project development.

Optional shortcut for filling 1-BRAINSTORM.md interactively.
You can also fill docs/project/config/brainstorm.md manually.

Usage:
    python scripts/brainstorm.py

What it does:
    1. Asks if you want to reset the project first (runs new_project.py)
    2. Guides you through brainstorm questions interactively (§0-6)
    3. Generates docs/project/config/brainstorm.md with your answers
"""

import os
import subprocess
import sys
from pathlib import Path
from datetime import datetime

# --- Constants ---

PROJECT_ROOT = Path(__file__).resolve().parent.parent
CONFIG_DIR = PROJECT_ROOT / "docs" / "project" / "config"
NEW_PROJECT_SCRIPT = PROJECT_ROOT / "scripts" / "new_project.py"

# --- Helper Functions ---

def clear_screen():
    os.system('clear' if os.name != 'nt' else 'cls')


def print_header(text: str):
    print("\n" + "=" * 60)
    print(f"  {text}")
    print("=" * 60 + "\n")


def ask_question(question: str, multiline: bool = False, optional: bool = False) -> str:
    suffix = " (optional, press Enter to skip)" if optional else ""
    print(f"📝 {question}{suffix}")

    if multiline:
        print("   (Type your answer, press Enter twice when done)")
        lines = []
        empty_count = 0
        while True:
            line = input("   ")
            if line == "":
                empty_count += 1
                if empty_count >= 2:
                    break
            else:
                empty_count = 0
                lines.append(line)
        return "\n".join(lines).strip()
    else:
        return input("   > ").strip()


def ask_yes_no(question: str, default: bool = True) -> bool:
    default_str = "Y/n" if default else "y/N"
    answer = input(f"❓ {question} ({default_str}): ").strip().lower()
    if answer == "":
        return default
    return answer in ["y", "yes"]


def ask_list(question: str, min_items: int = 1) -> list[str]:
    print(f"📝 {question}")
    print(f"   (Enter items one by one, press Enter on empty line when done, min: {min_items})")
    items = []
    while True:
        item = input(f"   {len(items) + 1}. ").strip()
        if item == "":
            if len(items) >= min_items:
                break
            else:
                print(f"   ⚠️  Need at least {min_items} item(s)")
        else:
            items.append(item)
    return items


def ask_table(headers: list[str], min_rows: int = 1) -> list[dict]:
    print(f"📝 Enter table data (columns: {', '.join(headers)})")
    print(f"   (Press Enter on first column to finish, min: {min_rows} row(s))")
    rows = []
    while True:
        row = {}
        first_col = input(f"\n   Row {len(rows) + 1} - {headers[0]}: ").strip()
        if first_col == "":
            if len(rows) >= min_rows:
                break
            else:
                print(f"   ⚠️  Need at least {min_rows} row(s)")
                continue
        row[headers[0]] = first_col
        for header in headers[1:]:
            row[header] = input(f"   {header}: ").strip()
        rows.append(row)
    return rows


# --- Main Brainstorm Flow ---

def run_brainstorm():
    clear_screen()
    print_header("🧠 PROJECT BRAINSTORM — Stage 1")
    print("This interactive session mirrors 1-BRAINSTORM.md.")
    print("Your answers will be saved to: docs/project/config/brainstorm.md")
    print()

    # Optional project reset
    if NEW_PROJECT_SCRIPT.exists():
        reset = ask_yes_no(
            "Do you want to reset the project first? (clears all config/workflow files)",
            default=False
        )
        if reset:
            print("\n🔄 Running new_project.py...")
            result = subprocess.run([sys.executable, str(NEW_PROJECT_SCRIPT)])
            if result.returncode != 0:
                if not ask_yes_no("Reset failed. Continue anyway?", default=True):
                    sys.exit(1)
            print("\n✅ Reset complete. Starting brainstorm...\n")
            input("Press Enter to continue...")

    clear_screen()
    print_header("🧠 PROJECT BRAINSTORM")

    answers = {}

    # Section 0: Freeform Input
    print_header("Section 0: Freeform Input")
    print("Start with completely unstructured thoughts. Write anything.")
    answers['freeform'] = ask_question(
        "Raw thoughts, requirements, ideas (any format):",
        multiline=True, optional=True
    )
    answers['notes'] = ask_question(
        "Background info, constraints, priorities, questions:",
        multiline=True, optional=True
    )

    # Section 1: The One-Liner
    clear_screen()
    print_header("Section 1: The One-Liner")
    print("What is this project in ONE sentence? No conjunctions.")

    while True:
        answers['project_name'] = ask_question("Project name:")
        if answers['project_name']:
            break
        print("   ⚠️  Project name cannot be empty.")

    print(f"\n   Example: \"{answers['project_name']} is a web app that tracks expenses for freelancers.\"")
    while True:
        answers['one_liner'] = ask_question(
            f"One-liner ({answers['project_name']} is a [type] that [does what] for [who]):"
        )
        if answers['one_liner']:
            break
        print("   ⚠️  One-liner cannot be empty.")

    # Section 2: The Problem
    clear_screen()
    print_header("Section 2: The Problem")
    answers['problem_who'] = ask_question("Who has this problem?")
    answers['problem_current'] = ask_question("How are they solving it today?")
    answers['problem_inadequate'] = ask_question("Why is the current solution inadequate?")
    answers['problem_frequency'] = ask_question("How often does this problem occur?")

    # Section 3: The Solution
    clear_screen()
    print_header("Section 3: The Solution")
    print("Describe from the USER's perspective. High-level only — details go in the PRD.")
    answers['solution_workflow'] = ask_list("Core workflow steps (user's journey):", min_items=2)
    answers['solution_differentiator'] = ask_question(
        "What makes this different from alternatives?", multiline=True
    )

    # Section 4: Assumptions & Risks
    clear_screen()
    print_header("Section 4: Assumptions & Risks")
    answers['assumptions'] = ask_table(
        ["Assumption", "Risk if Wrong", "Mitigation"], min_rows=1
    )

    # Section 5: Feasibility Check
    clear_screen()
    print_header("Section 5: Feasibility Check")
    answers['feasibility_complexity'] = ask_question("Technical complexity (Low/Medium/High):")
    answers['feasibility_time'] = ask_question("Time estimate for MVP (X days/weeks):")
    answers['feasibility_dependencies'] = ask_question("Dependencies / blockers:", optional=True)
    answers['feasibility_skills'] = ask_question("Skills gap:", optional=True)
    answers['feasibility_maintenance'] = ask_question("Maintenance burden (Low/Medium/High):")

    # Section 6: Go/No-Go (includes success definition)
    clear_screen()
    print_header("Section 6: Go / No-Go Decision")
    print("Define success first — that's your commit criteria.\n")
    answers['success_minimum'] = ask_question("Minimum success (MVP done):")
    answers['success_full'] = ask_question("Full success:")
    answers['success_failure'] = ask_question("Failure looks like:")

    print()
    print("1. GO    — The problem is real, the solution is scoped, I'm committing")
    print("2. NO-GO — Not worth building")
    print("3. PARK  — Good idea, wrong time")

    decision_map = {"1": "GO", "2": "NO-GO", "3": "PARK"}
    while True:
        choice = input("\nYour decision (1/2/3): ").strip()
        if choice in decision_map:
            answers['decision'] = decision_map[choice]
            break
        print("Invalid choice. Enter 1, 2, or 3.")

    answers['decision_rationale'] = ask_question("Decision rationale:", multiline=True)

    # Summary & confirmation
    clear_screen()
    print_header("📋 BRAINSTORM SUMMARY")
    print(f"Project:  {answers['project_name']}")
    print(f"One-liner: {answers['one_liner']}")
    print(f"Decision: {answers['decision']}")
    print()

    if not ask_yes_no("Generate brainstorm.md with these answers?", default=True):
        print("\n❌ Cancelled. No file generated.")
        sys.exit(0)

    generate_brainstorm_md(answers)

    print("\n" + "=" * 60)
    print("✅ BRAINSTORM COMPLETE")
    print("=" * 60)
    print(f"\n📄 Generated: docs/project/config/brainstorm.md")
    print(f"📍 Decision: {answers['decision']}")
    print()

    if answers['decision'] == "GO":
        print("🎯 Next step: docs/project/requirements/2-PRD.md")
    elif answers['decision'] == "PARK":
        print("⏸️  Project parked. Revisit when ready.")
    else:
        print("🛑 Project not proceeding.")


def generate_brainstorm_md(answers: dict):
    output_path = CONFIG_DIR / "brainstorm.md"
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)

    date_str = datetime.now().strftime("%Y-%m-%d")

    content = f"""# Brainstorm — {answers['project_name']}
> Generated by `scripts/brainstorm.py` on {date_str}
> Status: {answers['decision']}

---

## 0. Freeform Input

### Raw Thoughts
{answers.get('freeform', '[No input]')}

### Notes & Context
{answers.get('notes', '[No input]')}

---

## 1. The One-Liner

**{answers['project_name']}** {answers['one_liner']}

---

## 2. The Problem

- **Who has this problem?** {answers['problem_who']}
- **How are they solving it today?** {answers['problem_current']}
- **Why is the current solution inadequate?** {answers['problem_inadequate']}
- **How often does this problem occur?** {answers['problem_frequency']}

---

## 3. The Solution

### Core Workflow (User's Journey)
"""

    for i, step in enumerate(answers['solution_workflow'], 1):
        content += f"{i}. {step}\n"

    content += f"\n### What Makes This Different\n{answers['solution_differentiator']}\n\n---\n\n"

    content += "## 4. Assumptions & Risks\n\n"
    content += "| Assumption | Risk if Wrong | Mitigation |\n"
    content += "|---|---|---|\n"
    for row in answers['assumptions']:
        content += f"| {row['Assumption']} | {row['Risk if Wrong']} | {row['Mitigation']} |\n"

    content += "\n---\n\n## 5. Feasibility Check\n\n"
    content += f"- **Technical complexity:** {answers['feasibility_complexity']}\n"
    content += f"- **Time estimate (MVP):** {answers['feasibility_time']}\n"
    content += f"- **Dependencies / blockers:** {answers.get('feasibility_dependencies', 'None')}\n"
    content += f"- **Skills gap:** {answers.get('feasibility_skills', 'None')}\n"
    content += f"- **Maintenance burden:** {answers['feasibility_maintenance']}\n"

    content += f"\n---\n\n## 6. Go / No-Go Decision\n\n"
    content += f"**Success criteria:**\n"
    content += f"- Minimum (MVP done): {answers['success_minimum']}\n"
    content += f"- Full success: {answers['success_full']}\n"
    content += f"- Failure looks like: {answers['success_failure']}\n\n"
    content += f"**Decision:** {answers['decision']}\n\n"
    content += f"**Rationale:**\n{answers['decision_rationale']}\n"

    if answers['decision'] == "GO":
        content += "\n---\n\n## 📤 Next Steps\n\n"
        content += "✅ Brainstorm complete and approved.\n\n"
        content += "→ Proceed to `docs/project/requirements/2-PRD.md`\n"

    output_path.write_text(content)


def main():
    try:
        run_brainstorm()
    except KeyboardInterrupt:
        print("\n\n❌ Brainstorm cancelled by user.")
        sys.exit(1)
    except Exception as e:
        print(f"\n\n❌ Error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
