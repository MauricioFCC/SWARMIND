## Description

Please provide a summary of the changes and the motivation behind them.

## Type of change

- [ ] Bug fix (non-breaking change that fixes an issue)
- [ ] New feature (non-breaking change that adds functionality)
- [ ] Breaking change (fix or feature that would break existing functionality)
- [ ] Refactor (code changes that neither fix a bug nor add a feature)
- [ ] Performance improvement
- [ ] Documentation update
- [ ] CI / DevOps / Configuration change
- [ ] Test update

## Related issues

Closes #(issue)

## Checklist

### Code Quality
- [ ] Lint passes locally (`ruff check harness/`)
- [ ] Type check passes locally (`mypy harness/`)
- [ ] All tests pass locally (`pytest harness/tests/ -v`)
- [ ] New tests added for new functionality (if applicable)
- [ ] Code compiles without syntax errors

### Documentation
- [ ] Docstrings updated (Google-style, English)
- [ ] Relevant ADR updated or created (if architectural change)
- [ ] CHANGELOG updated
- [ ] mdbook docs updated (if user-facing or architectural change)

### Security
- [ ] No secrets, keys, or credentials hardcoded
- [ ] Input sanitization considered
- [ ] Dependencies are safe (no known vulnerabilities introduced)

### Git Hygiene
- [ ] Branch is up to date with base branch
- [ ] Commits are atomic with clear messages
- [ ] No merge commits in PR
