import { readdir, readFile } from "node:fs/promises";
import { fileURLToPath } from "node:url";
import path from "node:path";

const root = fileURLToPath(new URL("../src", import.meta.url));
async function check(directory) {
  for (const entry of await readdir(directory, { withFileTypes: true })) {
    const file = path.join(directory, entry.name);
    if (entry.isDirectory()) {
      await check(file);
      continue;
    }
    if (!file.endsWith(".tsx")) continue;
    const source = await readFile(file, "utf8");
    if (/<(?:button|input|select|textarea|option|progress)\b/.test(source))
      throw Error(`${file}: use the shared shadcn/Base UI controls`);
    if (/<video\b[^>]*\bcontrols[\s=>]/s.test(source))
      throw Error(`${file}: use the custom media controls`);
    if (
      /from\s+['"](?:@radix-ui|react-icons|@heroicons|@tabler\/icons)/.test(
        source,
      )
    )
      throw Error(`${file}: use Base UI and lucide-react`);
  }
}
await check(root);
console.log("Shared Base UI controls and Lucide-only icon imports verified.");
