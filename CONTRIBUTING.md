# Contributing to Story Film Studio

Thanks for helping make image-led filmmaking more accessible. Contributions can include bug fixes, documentation, accessibility improvements, provider integrations, tests and examples.

## Before you start

- For a bug, check existing issues and open a new issue with clear reproduction steps, expected and actual behavior, your operating system and relevant tool versions. Remove keys, private stories, personal paths and other sensitive details from logs and screenshots.
- For a substantial feature or change to the workflow, open an issue first so the approach can be discussed before you spend time implementing it.
- For a security issue or a suspected leaked credential, do not post the secret in a public issue. Revoke or rotate an exposed credential and contact the repository owner privately through a channel listed on their GitHub profile.

## Develop a change

1. Fork the repository, clone your fork and create a branch for your change.
2. Follow [setup instructions](docs/00-prerequisites.md). Read [AGENTS.md](AGENTS.md) and the relevant stage guide before changing the studio workflow.
3. Keep your change focused. Preserve user stories, authorization records and prior assets; never include real API keys or private production materials in a pull request.
4. Add or update tests where they verify meaningful behavior. Run the checks relevant to your change. For example:

   ```powershell
   .\.venv\Scripts\python.exe -B -m unittest discover -s tests
   npm --prefix apps/monitor ci
   npm --prefix apps/monitor run check
   npm --prefix apps/monitor test
   npm --prefix apps/monitor run build
   ```

   Frontend commands apply when working on the monitor. Some media tests need additional local runtimes or assets; mention any checks you could not run.
5. Open a pull request describing the problem, your solution, the checks you ran and any remaining limitations. Include a screenshot for visible UI changes when useful.

## Assets and licensing

Contribute only material you have the right to share. The studio software is offered under the [MIT License](LICENSE). The Last Delivery sample, visual references, branding, models and third-party material are not automatically covered by that software license; check their own credits and terms. Do not add a model, image, sound, voice reference or other asset without recording its source and applicable usage rights.
