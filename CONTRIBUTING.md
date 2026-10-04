# Contributing

Remixing is welcome (MIT). Before sending changes:

```bash
python3 -m unittest discover -s tests     # unit and GUI tests (the GUI ones need a display)
bash tests/static_checks.sh               # pyflakes, bandit, shellcheck
```

Tests run with an isolated config and never touch your real settings. Please do not commit cookies, logs, `settings.json`,
or built packages (`dist/`). Third-party code must be used as published and verified, not copied and rewritten (see SECURITY.md).
