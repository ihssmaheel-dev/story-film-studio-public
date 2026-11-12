# One branch per story

Clone the studio, paste the complete story in `story.md` or give it to Codex in chat/an attachment, and ask to start. Codex preserves the supplied text, reuses its title and initializes the project before writing story-specific work. A missing title belongs in the existing intake questions; branch creation itself needs no additional approval.

For a manual start, Git and standard Python are sufficient:

```powershell
git clone https://github.com/OWNER/story-film-studio.git
cd story-film-studio
# Paste the actual story into story.md, then start with its title:
python tools/studio.py init "The Last Train" --task film
```

This creates and switches to `story/the-last-train`, creates `stories/the-last-train/`, and saves the exact input bytes as `creative/original.md`. The initializer prints the branch and project path. `production/git.json` records the branch, project path, committed base, previous checkout, source hash and creation time. Audit/configuration records remain draft. The agent then reads the full story and continues the existing intake/review workflow, asking only the material choices still missing. The initializer does not write the story, call providers or generate a film by itself.

An attachment or another source file can be selected explicitly:

```powershell
python tools/studio.py init "The Last Train" --story-file C:/stories/the-last-train.txt --preset default
```

Unicode, punctuation, Windows reserved names and long titles receive stable safe slugs. The same slug identifies the Git branch and project folder. Empty sources and an unchanged blank intake template do not create a branch. Existing projects/branches are never overwritten; a new story with a colliding title needs a distinct title. A known remote story branch is also treated as existing. No implicit fetch, commit or push occurs.

## Independent stories and saved progress

New branches start from local `main`, then `master`, then the clone's known `origin/HEAD`, or the current non-story branch when no standard base exists. The chosen commit is recorded. There is no implicit remote update. Use `--base <committed-studio-ref>` when a different studio base is intentional; do not select another `story/` branch. Thus a second story does not inherit the first story's committed characters, approvals or project files.

Initialization permits edits/staging to the selected source file. It checks all other tracked/untracked changes first. Unrelated work must be committed or saved elsewhere before switching; it is never automatically stashed, reset, committed or discarded. During a base change, the selected source's actual working bytes and any distinct staged bytes are restored deliberately. A hash-named recovery copy is retained locally under `.runtime/story-init/sources/`. Other source/reference files outside the checkout are read without changing them. Invalid configuration/templates are prepared before switching; a failed final directory publication rolls back only the new empty branch.

Save completed progress on the current story branch with Git when appropriate, selecting the intended files. Credentials remain outside Git. Shared studio improvements/presets belong on the studio base when they should appear automatically in every subsequent story. The initializer can snapshot a selected preset before changing branches, preserving that story's selected preferences even when the preset lives on the departing branch.

Git tracks files, not empty folders or ignored media. Empty directories and ignored renders/caches may remain locally after a switch; they are not another story's canonical records. Keep their existing project paths. Branches do not upload media or replace delivery manifests/backups.

## Resume the same story

Commit its initialized project before leaving it, then resume by its project path:

```powershell
python tools/studio.py resume stories/the-last-train
```

The command validates the committed project record and switches to the existing local `story/the-last-train` branch. It also works when that folder is absent on the current branch. Resuming an already active story keeps its in-progress work. Switching from a different branch requires a clean working tree. A missing local branch must be fetched/checked out explicitly; `resume` never creates a replacement.

Configuration, production and review commands check the recorded branch before changing a new project's records or generating assets. Direct local production tools use the same stage guard. Ordinary read-only runtime diagnostics remain available. Older projects without `production/git.json` retain their existing behavior rather than being assigned a fabricated branch.

Install media dependencies when needed with `python tools/setup_studio.py`, then use the [Fast workflow](13-fast-workflow.md) and [speech provider guide](14-speech-providers.md). Creating a branch does not add creative or expense approvals, and it does not bypass the configured production scope or actual preview/playback checks.
