# Local Kokoro runtime

`tools/setup_studio.py` downloads checksum-verified `kokoro-v1.0.onnx` and `voices-v1.0.bin` from the official kokoro-onnx model-files-v1.1 release. They are installed in this workspace and ignored by source control. `manifest.json` stores upstream digests and sources; doctor verifies actual bytes.

The exact installed wrapper license, model card and Apache 2.0 license text are retained here. Inspect voice/language support and terms before production; runtime license files do not establish rights for arbitrary media. Future checkouts run setup rather than committing large weights.
