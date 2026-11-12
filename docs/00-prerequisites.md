# 00 — Prerequisites and verified setup

> **Workflow:** Fast is the new-project default; see [Fast workflow](13-fast-workflow.md). G1–G6 and separate reference/audition signoffs in this guide describe Strict mode. Fast uses scoped delegation and internal review; technical, continuity and genuine QA requirements still apply. Existing projects without a workflow record remain Strict.

Story intake, audit and written planning need filesystem access. Media production needs the verified runtime and the particular story approvals.

New story initialization also needs Git and a committed clone of the studio. Standard Python is sufficient for `studio init`: it creates the story's own branch before project work. Media setup can follow. Archives and folders inside an unrelated repository are not treated as studio clones. See [story branches](15-story-branches.md).

## This Windows workspace

Python 3.12.14 in `.venv`, FFmpeg/FFprobe 9.0.2, Kokoro-ONNX 0.6.1, ONNX Runtime 1.31.0, PocketSphinx 5.0.4, SoundFile 0.13.1, NumPy 2.3.5 and Pillow 12.3.0 are installed. Kokoro model/voice bytes match the upstream release digests. `.runtime/manifest.json` records actual versions, file hashes, sources, filters and license paths. Re-run doctor to inspect current readiness; this text is not a substitute for inspecting the machine.

```powershell
.\.venv\Scripts\python.exe tools/studio.py doctor
.\.venv\Scripts\python.exe tools/setup_studio.py --verify-only
```

A fresh Windows checkout uses a real Python 3.12 interpreter:

```powershell
python tools/setup_studio.py
```

Setup creates an isolated venv, installs exact versions from `requirements.lock.txt`, obtains the pinned FFmpeg archive and Kokoro files over HTTPS, verifies upstream SHA-256 values and preserves licenses/model card. It does not change global PATH or execution policy. `studio.ps1` is a convenience launcher; the direct interpreter works when PowerShell script execution is restricted. Runtime binaries, weights and caches are ignored by source control; setup downloads them when absent. Other platforms need explicit platform binary paths and a separately verified setup.

## Capabilities and limits

- CPU speech and procedural sound need no GPU or paid speech API. Plan sufficient disk for PCM audio, images, caches and exports.
- Speech provider selection is independent of the film renderer. [Kokoro, Chatterbox, cloud APIs, custom gateways and imported recordings](14-speech-providers.md) have different setup needs. `studio providers` lists routes; `studio doctor --project <path>` inspects the selected configuration without treating Kokoro as mandatory. Cloud credential presence is not a live audition. Optional Chatterbox packages/checkpoints belong in a separately prepared environment.
- The installed aligner is exercised with English. Other languages need a compatible aligner or manually inspected timing. Voice/language support must be checked before G5.
- Image generation uses an agent bridge to the available image tool. Queueing is not generation: the agent inspects references, follows the imagegen skill, executes an approved request, inspects the real result and imports it. Provider availability, capability, cost and upload scope are story decisions.
- Sound acquisition supports supplied files, HTTPS sources and limited wind/rain-like textures, hums and tones. Complex effects/music need suitable sources or an approved provider.
- `doctor` verifies local readiness; the full sample exercises actual CPU speech, alignment, mixing and rendering. Neither establishes aesthetic quality or permission authenticity.

## Cost, privacy and rights

G6 records final providers, expenses and privacy. Earlier reference/audition work needs its own explicit authorization. Never silently substitute a paid provider or upload private story/reference material. Queue estimates reserve the authorized provider budget, including cloud speech and images in Fast mode; unknown outcomes require actual reconciliation before retry. Record actual cost when reported, otherwise leave it unreported. Credential variables are resolved only at execution and never saved in story records.

Verify each exact asset's terms, creator/source, attribution and listening. Model/wrapper licenses are preserved under `models/kokoro/`; arbitrary generated/sourced media rights require their own evidence. Offline work uses local resources. Global example images remain optional inspiration.
