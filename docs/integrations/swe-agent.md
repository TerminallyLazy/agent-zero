# Open-SWE Agent Profile (Agent Zero)

This profile adds a specialized SWE agent that supports:
- Repository analysis and planning
- Implementation with safe file operations
- Testing and coverage workflows
- Static review and refactoring suggestions
- Documentation generation (API, ADR, deployment/runbooks)

Activation
- Set AgentConfig.prompts_subdir = "swe-agent"
- Call tools by name (e.g., "swe_repo_analysis", "swe_code_gen", "swe_testing", "swe_code_review", "swe_docs")

Notes
- Prefer read-only analysis first
- After implementing changes, create and run a validation script
- Avoid unnecessary backwards compatibility unless required
