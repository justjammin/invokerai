#!/usr/bin/env python3
"""
Generate router.pkl from labeled examples.

Usage:
    python scripts/build_router.py          # Phase 1 (TF-IDF + kNN)
    python scripts/build_router.py --phase 2  # Phase 2 (mpnet + RandomForest)
    python -m agent_invoker.build           # same as above via module
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from agent_invoker.classifier import build

# fmt: off
EXAMPLES: list[tuple[str, str]] = [
    # direct|debugger
    ("fix the null check in auth middleware", "direct|debugger"),
    ("why is the login throwing a 500", "direct|debugger"),
    ("track down the memory leak in the worker", "direct|debugger"),
    ("the payment form is broken after the last deploy", "direct|debugger"),
    ("exception in user service on startup", "direct|debugger"),
    ("undefined is not a function in checkout component", "direct|debugger"),
    ("api returns 422 on valid input", "direct|debugger"),
    ("fix the race condition in the job queue", "direct|debugger"),

    # direct|code-reviewer
    ("review this PR for security issues", "direct|code-reviewer"),
    ("audit the auth module for vulnerabilities", "direct|code-reviewer"),
    ("give me a second opinion on this middleware", "direct|code-reviewer"),
    ("check this sql query for injection risks", "direct|code-reviewer"),
    ("review the payment handler before we ship", "direct|code-reviewer"),

    # direct|refactoring-specialist
    ("refactor the payment module into smaller functions", "direct|refactoring-specialist"),
    ("clean up the duplicated validation logic", "direct|refactoring-specialist"),
    ("extract the email sending into its own service", "direct|refactoring-specialist"),
    ("simplify the nested conditionals in the router", "direct|refactoring-specialist"),

    # direct|architect-reviewer
    ("explain how the auth middleware works", "direct|architect-reviewer"),
    ("what is the tradeoff between redis and memcached here", "direct|architect-reviewer"),
    ("how does the job queue connect to the worker pool", "direct|architect-reviewer"),
    ("should we use event sourcing for this feature", "direct|architect-reviewer"),
    ("describe the current payment flow architecture", "direct|architect-reviewer"),

    # direct|test-automator
    ("add unit tests for the cart service", "direct|test-automator"),
    ("write integration tests for the auth endpoints", "direct|test-automator"),
    ("set up e2e tests for the checkout flow", "direct|test-automator"),
    ("increase test coverage on the user model", "direct|test-automator"),

    # direct|database-optimizer
    ("this query is taking 4 seconds, optimize it", "direct|database-optimizer"),
    ("add an index to speed up the user lookup", "direct|database-optimizer"),
    ("the n+1 query in the order list is killing performance", "direct|database-optimizer"),
    ("write the migration to add the new column", "direct|database-optimizer"),
    ("analyze the slow query log from last night", "direct|database-optimizer"),

    # direct|backend-developer
    ("add a new endpoint to the user api", "direct|backend-developer"),
    ("implement rate limiting on the public api", "direct|backend-developer"),
    ("add pagination to the orders endpoint", "direct|backend-developer"),
    ("build the webhook handler for stripe events", "direct|backend-developer"),

    # direct|frontend-developer
    ("fix the alignment issue in the dashboard header", "direct|frontend-developer"),
    ("add a loading spinner to the data table", "direct|frontend-developer"),
    ("the modal is not closing on mobile", "direct|frontend-developer"),
    ("update the color scheme to match the new brand", "direct|frontend-developer"),

    # direct|cloud-architect
    ("set up the kubernetes deployment for the api", "direct|cloud-architect"),
    ("configure autoscaling for the worker nodes", "direct|cloud-architect"),
    ("write the terraform for the new rds instance", "direct|cloud-architect"),
    ("the pod is crashing on startup in prod", "direct|cloud-architect"),

    # direct|technical-writer
    ("write the api documentation for the user endpoints", "direct|technical-writer"),
    ("create a getting started guide for new developers", "direct|technical-writer"),
    ("document the authentication flow", "direct|technical-writer"),

    # direct|ml-engineer
    ("set up the training pipeline for the recommendation model", "direct|ml-engineer"),
    ("the model inference is too slow, optimize it", "direct|ml-engineer"),
    ("fine-tune the embedding model on our dataset", "direct|ml-engineer"),

    # orchestrate|null
    ("build a full auth system with tests and docs", "orchestrate|null"),
    ("design and implement the payment flow end to end", "orchestrate|null"),
    ("build a real-time dashboard with charts and alerts", "orchestrate|null"),
    ("migrate the monolith to microservices", "orchestrate|null"),
    ("set up the ci cd pipeline then add integration tests and deploy", "orchestrate|null"),
    ("add user authentication and then write tests and document the api", "orchestrate|null"),
    ("build the admin panel with search filtering and export functionality", "orchestrate|null"),
    ("create the data pipeline then build the dashboard and write the documentation", "orchestrate|null"),
    ("implement sso then add rbac then update all the api endpoints", "orchestrate|null"),
    ("redesign the onboarding flow implement it and add analytics", "orchestrate|null"),
]
# fmt: on


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--phase", type=int, choices=[1, 2], default=1)
    parser.add_argument("--output", type=Path, default=Path.home() / ".invokerai" / "router.pkl")
    args = parser.parse_args()

    if args.phase == 2:
        try:
            import sentence_transformers  # noqa: F401
        except ImportError:
            print("Phase 2 requires: pip install agent-invoker[embeddings]")
            sys.exit(1)

    print(f"Building Phase {args.phase} router from {len(EXAMPLES)} examples...")
    build(EXAMPLES, output_path=args.output, phase=args.phase)


if __name__ == "__main__":
    main()