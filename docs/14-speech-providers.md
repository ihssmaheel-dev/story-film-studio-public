# Choose a speech provider and voice cast

Users choose the provider. Keep a named choice, compare options when requested, and never switch to a paid service or a different voice silently. Kokoro remains the free CPU default for existing projects and unspecified new profiles; it is one option, not a mandatory engine. Speech-free films skip this configuration.

| Provider ID | Route | Setup and scope |
|---|---|---|
| `kokoro` | Local ONNX CPU | Existing verified model/voice files; no API key or usage fee |
| `chatterbox` | Local loopback server | Separate Chatterbox environment, reviewed local checkpoints and selected reference clips; CPU/GPU suitability must be tested |
| `elevenlabs` | Native cloud API | User's account, selected model/voice IDs and `ELEVENLABS_API_KEY` |
| `inworld` | Native cloud API | User's account, selected model/voice IDs and `INWORLD_API_KEY` |
| `cartesia` | Native cloud API | User's account, selected model/voice IDs and `CARTESIA_API_KEY` |
| `custom-http` | User-configured speech gateway | Documented JSON/audio contract below; supports other services through a gateway |
| `provided` | Imported voice recordings | Actual files from any provider or actor, exact transcripts, hashes and usage evidence |

Cloud services may offer account credits, but they are not assumed free. Set a verified current model/voice-specific `price_per_1000_characters`, currency, spending cap and upload scope before a call. No account signup, key creation, large model installation or paid synthesis is performed merely by listing/choosing a provider. Credentials stay in environment variables; project files contain the variable names only. A configured adapter is not proof of account access, voice availability, rights or artistic quality.

```powershell
.\.venv\Scripts\python.exe tools/studio.py providers
.\.venv\Scripts\python.exe tools/studio.py doctor --project stories/my-story
.\.venv\Scripts\python.exe tools/studio.py speech stories/my-story --part part_001
```

`studio run` uses this same speech layer. `tts_kokoro.py` remains a Kokoro-specific compatibility command; use `studio speech` for provider selection. There is no automatic provider fallback. Configure provider, model, narrator voice and any explicit cast preferences together, then record the normal scoped configuration authorization once. Unknown/delegated cast choices can be completed inside the allowed tools/budget without another authorization; an explicitly chosen voice/model/route stays bound.

## Narrator and character choices

`audio/narrator.json` is authoritative. `provider`, `model`, `voice`, `language`, `speed` and `pause` describe the narrator defaults. A null model uses the adapter's recorded default. `providers` holds provider-specific setup. `cast` maps `NARRATOR` and canonical `CHAR-###` IDs to their provider/model/voice/language/speed and optional `options`. Different characters may use different providers inside the authorized scope. A speaking character needs an explicit cast assignment; it never silently becomes the narrator's voice.

For example, this **configuration fragment** chooses Inworld. Replace voice placeholders with actual selected IDs and fill the verified price; the fragment alone is not permission to generate:

```json
{
  "narrator": {
    "provider": "inworld",
    "model": "inworld-tts-2",
    "voice": "YOUR_NARRATOR_VOICE_ID",
    "language": "en-us",
    "speed": 1.0,
    "providers": {
      "inworld": {
        "api_key_env": "INWORLD_API_KEY",
        "price_per_1000_characters": null,
        "currency": "USD"
      }
    },
    "cast": {
      "CHAR-001": {"provider": "inworld", "voice": "YOUR_CHARACTER_VOICE_ID"}
    }
  }
}
```

The full workflow configuration must also include the selected provider in `scope.tools`, cloud providers in `scope.external_upload`, and the actual total budget/currency. Inworld's environment value is the copied Base64 credential, used directly with Basic authentication; do not encode it again. ElevenLabs uses its `xi-api-key` header. Cartesia uses Bearer authentication and the pinned `2026-08-14` API contract. A different native API contract needs an adapter update or a separately configured custom gateway.

Choose voices for the role's age/design, personality, accent, relationships and emotional range. Inspect a representative narration/dialogue scene when a choice is uncertain. Keep those voice identities across all parts and the full cut. Provider names, rankings and marketing claims do not establish a suitable performance.

## Story-fit selection and later changes

The agent chooses an unset narrator from the entire story's point of view, tone, audience, emotional range, language and pacing. It records a performance brief and selection reasons in `audio/voice-plan.json`, reuses a suitable known audition or compares a small shortlist on actual story passages, and listens before claiming a successful selection. Characters receive distinct role-specific voices. Follow [the casting procedure](../instructions/voice-casting.md); there is no universally perfect voice or automatic quality score.

Ask naturally to change the narrator or a character whenever needed, including after a preview or delivery. The agent auditions the requested direction when necessary and records the actual change without restarting intake. Commands for inspecting and applying a choice are:

```powershell
.\.venv\Scripts\python.exe tools/studio.py voice status stories/my-story
.\.venv\Scripts\python.exe tools/studio.py voice set stories/my-story --speaker NARRATOR --voice ACTUAL_VOICE_ID --reason "Actual story-specific casting reason"
.\.venv\Scripts\python.exe tools/studio.py voice set stories/my-story --speaker CHAR-001 --voice ACTUAL_REPLACEMENT_ID --reason "Actual role and performance reason" --decision "ACTUAL USER VOICE CHANGE REQUEST" --decision-reference "actual chat/source reference"
.\.venv\Scripts\python.exe tools/studio.py speech stories/my-story --purpose audition --speaker CHAR-001 --text-file stories/my-story/audio/audition.txt --output stories/my-story/audio/auditions/character-candidate.wav
```

The first `set` form covers an unset/delegated voice; replacing a bound choice requires the actual user request/reference as shown in the second form. The command generates no speech. A user change within an existing current Fast scope amends the voice choice and retains the original authorization/history; it does not require approving the whole configuration again or invalidate already permitted story edits. New provider/upload/budget scope is handled separately. A changed choice does not silently become approved Strict G5/G6 work.

Exact old profiles are kept in `audio/voice-revisions/`; `audio/voice-decisions.json` records reasons, source identity, actual decisions and affected parts. A narrator change leaves character voices intact. Auditions support `--speaker`, `--provider`, `--voice` and `--model` overrides without modifying the selected cast. Presets save the actual current narrator even when it is a `NARRATOR` role override, without copying story-specific characters.

Rebuild changed speaker clips, measured timing, mix/subtitles, preview/master and any included full cut; reuse unaffected clips and source images. Inspect changed camera/reveal timing and perform real playback. Existing deliveries remain available; a changed delivery uses a new revision. Model availability, listening quality and any new synthesis cost must be verified rather than assumed.

## Written narration and dialogue

`parts/part_###/narration.txt` contains only the exact spoken text, matching written shots. `speech.json` assigns its turns to speakers and keeps acting directions outside that transcript:

```json
{
  "schema_version": 1,
  "utterances": [
    {"id": "UTT-001", "speaker": "NARRATOR", "text": "She recognized the familiar voice.", "pause_after": 0.3},
    {"id": "UTT-002", "speaker": "CHAR-001", "text": "You came home.", "direction": "gently", "pause_after": 0.5}
  ]
}
```

Turn text, in order, must match `narration.txt` exactly apart from whitespace. Dialogue/mixed films require actual written turns. Empty turns remain valid for ordinary single-narrator projects: the engine groups text at sentence boundaries for provider limits; legacy Kokoro keeps its existing sentence cache. An explicit `pause_after` includes intended silence, including an intentional tail on the last turn. `take: 2` requests an intentional new performance after a known completed take; it is not an automatic retry.

Supported delivery controls vary. Eleven v3/v4 accept inline acting tags generated from `direction`; Multilingual v2 does not. Inworld uses its supported instruction prefix. Cartesia passes direction to its emotion control; verify language/model support. Kokoro rejects unsupported acting tags rather than reading them aloud. Chatterbox Turbo/Nano accepts its supported nonverbal tags (`laugh`, `sigh`, `chuckle`, etc.); original/multilingual models use native generation controls. Unsupported controls fail clearly. Voice style alone does not provide character/object animation or sound effects.

Each turn is rendered with its fixed voice, measured and normalized to a mono 48 kHz PCM clip, then assembled with the written pauses. Legacy single-narrator Kokoro retains its native cached sample rate; the final mixer already produces 48 kHz audio. ElevenLabs requests include adjacent text where the selected endpoint supports it. The current implementation creates separate turn clips, including when using ElevenLabs' dialogue endpoint; it does not claim native joint-scene generation or verified word timing. Measured chunks remain inputs to the existing alignment/mix/subtitle workflow. The installed automatic aligner is English; other languages require a compatible aligner or actual inspected manual timing before dependent generation/production. A multilingual voice provider does not upgrade alignment automatically.

## Local Chatterbox

Install the official Chatterbox package and its suitable PyTorch dependencies in a separate environment. Prepare the exact official checkpoints and licenses there; the studio does not download weights during a speech request. Review the selected voice clips and their usage permission, then snapshot them inside the story project.

Run the bridge with that environment's Python (example paths must be replaced with actual prepared directories):

```powershell
& 'C:/voice-env/Scripts/python.exe' tools/chatterbox_server.py --checkpoints F:/voice-models/chatterbox-turbo --voice-root ./stories --model turbo --device cpu
```

The bridge binds to `127.0.0.1` only, loads the model once and reports its actual checkpoint/package fingerprint at `/info`. Supported variants are `original`, `turbo`, `nano`, `multilingual-v2` and `multilingual-v3`; do not assume each variant supports every language/control. Check actual CPU/GPU quality and speed. It keeps the upstream watermarking behavior. Set the profile's `provider: chatterbox`, selected variant in `model`, voice label, and `providers.chatterbox.reference_audio` to the reviewed project-relative clip. The default endpoint is `http://127.0.0.1:8090/speech`. An optional `model_fingerprint` locks the server's actual reported checkpoint identity.

Every Chatterbox turn supplies its reference again so one character cannot inherit the previous character's conditioning. Native speed is 1.0. Turns are limited to 500 characters; automatic grouping uses 450 for headroom. The server checks the selected language, actual reference path and supported controls. Starting it does not create a story audition or pass listening QA.

## Other providers and recorded performances

For `custom-http`, configure an explicit `model`, `voice`, and `providers.custom-http.endpoint`. The gateway accepts JSON fields `text`, `voice`, `model`, `language`, `speed`, `direction` plus configured non-secret `request_extra`. It returns playable audio bytes, or `response_format: base64-json` with `audio_json_key` naming the encoded field (default `audioContent`, dotted keys supported). Authentication is optional for loopback or uses `api_key_env` with `auth_header`/`auth_prefix`; never put keys in URLs, request-extra objects or project headers. Redirects are refused.

A custom gateway is metered/cloud by default, including a loopback proxy that might forward externally. Set `local_only: true` only for a genuinely local, free loopback implementation; remote URLs cannot use that flag. HTTPS is required outside loopback. This contract supports custom bridges, not every provider's native protocol without an adapter.

For `provided`, set a turn's `audio_file` to a snapshotted project-relative recording and `sha256` to its actual digest. Keep the exact performed words in `text`; directions must already have been acted. This route accepts output from other TTS tools or human actors, without inventing an API integration. Source/rights/listening evidence remains necessary. Imported audio stays at native performance speed 1.0 and is normalized for assembly without overwriting its source.

Presets save provider/model/default narrator choices and selected global Chatterbox voice snapshots. They do not copy another story's `CHAR-###` cast assignments. Map the new story's roles deliberately. Snapshots preserve exact hashes; copying them does not establish usage rights or carry another project's authorization.

## Caches, costs and recovery

Cache identity includes the actual provider/model/voice, text, supported delivery settings, context, take and selected reference/runtime hashes. Switching providers or cast voices cannot reuse the wrong speech. Retain each source clip and measured `.chunks.json`; a cache hit does not claim new generation. Local synthesis and sound/image caches remain reusable.

Cloud speech and image requests share the Fast total budget and one locked reservation ledger. Estimates include submitted text/directions/context conservatively; actual cost remains null unless reported/reconciled. These reservations are not provider invoices. Credential variables are resolved only when making a new request and are excluded from receipts. A received response is retained before decoding, allowing damaged derivative clips to be rebuilt without paying for the same request again.

Unknown/timeout outcomes stop automatic retries and intentional retakes of that turn. Reconcile the actual provider history before another call, retaining real evidence and billed cost:

```powershell
.\.venv\Scripts\python.exe tools/studio.py speech-resolve stories/my-story --request-id ACTUAL_REQUEST_HASH --outcome failed --actual-cost 0 --evidence "Actual provider failure/charge receipt reference"
```

Use `--outcome received --audio ACTUAL_RECOVERED_AUDIO` to import a known completed response. Do not use the example zero cost without real evidence. A confirmed failure permits a later retry while preserving prior charges/history; an unknown result never becomes an assumed free failure. Price/voice availability and provider terms must be checked for the selected account/model.

## Adapter sources

Contracts checked against official sources on 2026-10-29: [ElevenLabs dialogue](https://elevenlabs.io/docs/api-reference/text-to-dialogue/convert), [ElevenLabs speech](https://elevenlabs.io/docs/api-reference/text-to-speech/convert), [Inworld synthesis](https://docs.inworld.ai/api-reference/ttsAPI/texttospeech/synthesize-speech), [Cartesia bytes](https://docs.cartesia.ai/api-reference/tts/bytes), and [Chatterbox source](https://github.com/resemble-ai/chatterbox). Native cloud adapters require account-specific live auditions before production; mocked contract tests do not establish live-service quality or compatibility with every future API version.
